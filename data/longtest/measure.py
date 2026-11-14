import json, time, pathlib, sys, httpx, subprocess
API = "http://127.0.0.1:8000"; AID = "a_0ac641df"; JID = "j_9341b715e1"
ROOT = pathlib.Path(r"C:\Users\suhas\ericsson-dso"); DATA = ROOT / "data"; OUT = DATA / "longtest"
VID = DATA / "samples" / "Your Agent Doesnt Need an LLM for Every Decision - Raymond Weitekamp OpenProse.mp4"
queries = json.loads((OUT / "queries.json").read_text(encoding="utf-8-sig"))
c = httpx.Client(timeout=120)
def timed(url):
    t = time.perf_counter(); r = c.get(API + url); ms = (time.perf_counter() - t) * 1000; r.raise_for_status(); return r.json(), round(ms, 1)
probe = json.loads(subprocess.run(["ffprobe","-v","error","-print_format","json","-show_format","-show_streams",str(VID)],capture_output=True,text=True).stdout)
vs = next(s for s in probe["streams"] if s["codec_type"]=="video"); au = next(s for s in probe["streams"] if s["codec_type"]=="audio")
state1 = json.loads((OUT/"state.json").read_text(encoding="utf-8-sig"))
job2 = json.loads((OUT/"job2_end.json").read_text(encoding="utf-8-sig"))["job"]
asset, asset_ms = timed(f"/api/assets/{AID}")
d = DATA / "derived" / AID
manifest = json.loads((d/"manifest.json").read_text(encoding="utf-8-sig"))
tr = json.loads((d/"transcript.json").read_text(encoding="utf-8-sig"))
files = [{"path": str(p.relative_to(d)).replace("\\","/"), "bytes": p.stat().st_size} for p in sorted(d.rglob("*")) if p.is_file()]
frames = manifest.get("frames", [])
frame_bytes = sum(f["bytes"] for f in frames)
transcript_bytes = (d/"transcript.json").stat().st_size
manifest_bytes = (d/"manifest.json").stat().st_size
status_files = [f for f in files if f["path"] in ("progress.json","error.json","progress.json.tmp")]
derived_all = sum(f["bytes"] for f in files if f not in status_files)
listed_derived = sum(x["bytes"] for x in manifest.get("derived_files", []))
O = int(probe["format"]["size"]); dur = float(probe["format"]["duration"])
index_bytes = (DATA/"dso.sqlite").stat().st_size
storage, storage_ms = timed("/api/storage/report")
def pct(o,a): return round((o-a)/o*100, 4)
# per-video: index counted as the whole DB (conservative; DB is shared with 6 small earlier assets)
s0_A = O + derived_all + index_bytes
s1_A = derived_all + index_bytes
s1_A_noindex = derived_all
segs = tr["segments"]; speech_s = sum(s["end"]-s["start"] for s in segs)
text_chars = sum(len(s["text"]) for s in segs)
# projection to 2h / 1 GB
O2 = 1_000_000_000; dur2 = 7200.0; k = dur2/dur
proj_tr = transcript_bytes * k
proj_frames_same = frame_bytes          # assumption A: same set of distinct slides
proj_frames_lin = frame_bytes * k       # assumption B (upper bound): frame count scales with time
proj = {
  "assumptions": [
    "Projection, not a measurement. 2-hour recording of ~1 GB (10^9 bytes) with the same speech density as this talk.",
    "transcript.json bytes scale linearly with duration (k = 7200 / measured duration).",
    "Frames: lower bound = same distinct slides as this talk (frame bytes unchanged); upper bound = frame count/bytes scale linearly with duration.",
    "manifest.json scales linearly (upper bound); index bytes = current measured dso.sqlite size scaled by k for this asset's share is not modelled; we add the current whole DB size + transcript-sized FTS growth (approx 2x transcript text) as a conservative add-on.",
  ],
  "k": round(k,4),
  "transcript_bytes": round(proj_tr), "manifest_bytes": round(manifest_bytes*k),
  "frame_bytes_low": proj_frames_same, "frame_bytes_high": round(proj_frames_lin),
}
idx_add = index_bytes + 2*text_chars*k
proj["A_low"] = round(proj_tr + proj["manifest_bytes"] + proj_frames_same + idx_add)
proj["A_high"] = round(proj_tr + proj["manifest_bytes"] + proj_frames_lin + idx_add)
proj["savings_pct_low_A"] = pct(O2, proj["A_low"]); proj["savings_pct_high_A"] = pct(O2, proj["A_high"])
# search
search = []
for q in queries["positive"] + [queries["negative"]]:
    res, ms = timed("/api/search?" + httpx.QueryParams({"q": q["q"]}).__str__())
    hits = [h for h in res["hits"] if h["asset_id"] == AID]
    top = res["hits"][0] if res["hits"] else None
    exp = q.get("expect_segment")
    seg_hit = any(h["item_id"] == exp for h in hits) if exp else None
    search.append({"q": q["q"], "expected_segment": exp, "negative": q is queries["negative"], "ms": ms, "total": res["total"],
                   "hits_this_asset": len(hits), "top_is_this_asset": bool(top and top["asset_id"]==AID),
                   "expected_segment_hit": seg_hit, "top_hit": {k2: top.get(k2) for k2 in ("asset_id","item_id","frame_id","start","end","snippet")} if top else None})
off, off_ms = timed("/api/offboarding?owner=erik")
dup, dup_ms = timed("/api/duplicates")
exp_, exp_ms = timed(f"/api/assets/{AID}/export")
off_s = json.dumps(off)
res = {
  "source": {"how": "Real recording provided by the user (downloaded by them), placed in data/samples. Not generated.", "path": str(VID),
             "title_tag": probe["format"].get("tags",{}).get("title"), "artist_tag": probe["format"].get("tags",{}).get("artist")},
  "probe": {"duration_seconds": dur, "original_bytes": O, "container_bitrate_bps": int(probe["format"]["bit_rate"]),
            "video": {"codec": vs["codec_name"], "width": vs["width"], "height": vs["height"], "fps": vs["avg_frame_rate"], "bitrate_bps": int(vs.get("bit_rate",0))},
            "audio": {"codec": au["codec_name"], "sample_rate": au["sample_rate"], "channels": au["channels"], "bitrate_bps": int(au.get("bit_rate",0))}},
  "ids": {"asset_id": AID, "job_id": JID, "first_failed_job": state1["job_start"]["id"], "first_failed_job_error": state1.get("job_end",{}).get("error")},
  "timings": {"upload_ms": round(state1["upload_ms"],1), "job": job2, "manifest_pipeline": manifest.get("pipeline"),
              "storage_report_ms": storage_ms, "asset_detail_ms": asset_ms, "offboarding_ms": off_ms, "duplicates_ms": dup_ms, "export_ms": exp_ms},
  "asset_detail": {k2: asset.get(k2) for k2 in ("id","status","kind","bytes","derived_bytes","owner","source_system","sha256")},
  "derived": {"transcript_bytes": transcript_bytes, "manifest_bytes": manifest_bytes, "frame_count": len(frames), "frame_bytes_total": frame_bytes,
              "frames": [{k2: f[k2] for k2 in ("id","t_start","t_end","bytes")} for f in frames],
              "all_files_on_disk": files, "status_files_excluded": status_files, "derived_total_bytes_on_disk": derived_all,
              "manifest_listed_derived_bytes": listed_derived},
  "transcript": {"language": tr.get("language"), "model": tr.get("model"), "segment_count": len(segs), "speech_seconds": round(speech_s,1),
                 "text_chars": text_chars, "words": sum(len(s["text"].split()) for s in segs),
                 "segments_with_frame_id": sum(1 for s in segs if s.get("frame_id"))},
  "frames_quality": {"count": len(frames), "duration_seconds": dur, "frames_per_minute": round(len(frames)/(dur/60),3),
                     "median_hold_s": sorted(f["t_end"]-f["t_start"] for f in frames)[len(frames)//2] if frames else None,
                     "min_hold_s": min((f["t_end"]-f["t_start"] for f in frames), default=None)},
  "storage_per_video": {
     "formula": "Savings % = (O - A) / O x 100", "O": O, "D_derived": derived_all,
     "I_index_whole_db_bytes": index_bytes, "I_note": "whole dso.sqlite counted (shared with 6 earlier small assets) -> conservative",
     "scenario0": {"A": s0_A, "savings_pct": pct(O, s0_A)},
     "scenario1": {"A": s1_A, "savings_pct": pct(O, s1_A), "A_without_index": s1_A_noindex, "savings_pct_without_index": pct(O, s1_A_noindex)},
  },
  "storage_report_corpus": storage,
  "projection_2h_1GB": proj,
  "search": search,
  "offboarding": {"raw": off, "deletes_performed_false_present": '"deletes_performed": false' in off_s},
  "duplicates_mentions_this_asset": AID in json.dumps(dup),
}
(DATA/"long-video-results.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps({k2: res[k2] for k2 in ("timings","derived","transcript","frames_quality","storage_per_video","projection_2h_1GB")}, indent=1, ensure_ascii=False)[:9000])
print(json.dumps(res["search"], indent=1, ensure_ascii=False))
print("OFF", json.dumps(off, ensure_ascii=False)[:2500])
