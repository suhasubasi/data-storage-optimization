import json, time
from pathlib import Path
import httpx

API = "http://127.0.0.1:8000"
AID = "a_0ac641df"
T = Path(r"C:\Users\suhas\ericsson-dso\data\derived") / AID / "transcript.json"
M = Path(r"C:\Users\suhas\ericsson-dso\data\derived") / AID / "manifest.json"

client = httpx.Client(timeout=30)
asset = client.get(f"{API}/api/assets/{AID}").json()
storage = client.get(f"{API}/api/storage/report").json()
off = client.get(f"{API}/api/offboarding", params={"owner": "erik"}).json()

queries = [
    "OpenProse",
    "Weitekamp",
    "LLM",
    "handover",
    "yellow cabinet",
    "deterministic",
    "workflow",
    "agent",
]
searches = {}
for q in queries:
    t0 = time.perf_counter()
    r = client.get(f"{API}/api/search", params={"q": q}).json()
    ms = (time.perf_counter() - t0) * 1000
    hits = r.get("hits") or []
    ours = [h for h in hits if h.get("asset_id") == AID]
    searches[q] = {
        "total": r.get("total"),
        "ours": len(ours),
        "ms": round(ms, 2),
        "samples": [
            {
                "asset_id": h.get("asset_id"),
                "filename": h.get("filename"),
                "item_id": h.get("item_id"),
                "frame_id": h.get("frame_id"),
                "start": h.get("start"),
                "text": (h.get("text") or "")[:240],
            }
            for h in (ours or hits)[:3]
        ],
    }

tr = json.loads(T.read_text(encoding="utf-8"))
segs = tr.get("segments") or []
texts = [s.get("text") or "" for s in segs]
joined = " ".join(texts)
# unique frame ids used
fids = sorted({s.get("frame_id") for s in segs if s.get("frame_id")})

# pick 8 distinctive mid/late phrases
picks = []
for s in segs:
    t = (s.get("text") or "").strip()
    if len(t) >= 60 and any(k in t.lower() for k in ("openprose", "llm", "agent", "decision", "workflow", "prose", "model", "tool")):
        picks.append({"id": s.get("id"), "start": s.get("start"), "end": s.get("end"), "frame_id": s.get("frame_id"), "text": t})
        if len(picks) >= 10:
            break
if len(picks) < 6:
    for s in segs[10:80]:
        t = (s.get("text") or "").strip()
        if len(t) >= 50:
            picks.append({"id": s.get("id"), "start": s.get("start"), "end": s.get("end"), "frame_id": s.get("frame_id"), "text": t})
        if len(picks) >= 8:
            break

man = json.loads(M.read_text(encoding="utf-8"))
frames = man.get("frames") or man.get("pipeline") and man.get("frames") or []
# frames may be in manifest
if not frames:
    frames = man.get("frames") or []

orig = asset["asset"]["bytes"]
der = asset["derived"]["derived_bytes"]
kinds = asset["derived"]["bytes_by_kind"]
index = storage["totals"]["index_bytes"]
duration = asset["metadata"]["duration_seconds"]

# per-video scenario math (this asset only, plus full index — labeled)
s0_after = orig + der + index
s0_pct = (orig - s0_after) / orig * 100
s1_after = der + index
s1_pct = (orig - s1_after) / orig * 100

# projection to 2h / 1GB
# transcript scales with duration; frames scale with unique visual changes, not linearly
scale = 7200 / duration if duration else None
proj = {
    "assumed_2h_original_bytes": 1_000_000_000,
    "measured_duration_s": duration,
    "transcript_if_scaled_linearly_bytes": round(kinds["transcript"] * (7200 / duration)),
    "frames_if_same_change_rate_bytes": round(kinds["frame"] * (7200 / duration)),
    "frames_if_same_unique_slides_only_bytes": kinds["frame"],  # conservative: same talk structure
    "manifest_measured_bytes": kinds["manifest"],
    "scenario1_if_1GB_and_scaled_frames_pct": None,
    "scenario1_if_1GB_and_same_frame_count_pct": None,
}
# A = derived + index (use current index as approx)
if scale:
    der_scaled = kinds["transcript"] * scale + kinds["frame"] * scale + kinds["manifest"]
    der_same_slides = kinds["transcript"] * scale + kinds["frame"] + kinds["manifest"]
    o = 1_000_000_000
    proj["scenario1_if_1GB_and_scaled_frames_pct"] = round((o - (der_scaled + index)) / o * 100, 2)
    proj["scenario1_if_1GB_and_same_frame_count_pct"] = round((o - (der_same_slides + index)) / o * 100, 2)
    proj["derived_scaled_plus_index"] = round(der_scaled + index)
    proj["derived_same_slides_plus_index"] = round(der_same_slides + index)

out = {
    "ready": asset["asset"]["status"],
    "filename": asset["asset"]["filename"],
    "sha256": asset["asset"]["sha256"],
    "model": asset["pipeline"]["model"],
    "pipeline_seconds": asset["pipeline"]["seconds"],
    "job": asset["latest_job"],
    "duration_seconds": duration,
    "original_bytes": orig,
    "derived_bytes": der,
    "bytes_by_kind": kinds,
    "segment_count": asset["derived"]["segment_count"],
    "frame_count": asset["derived"]["frame_count"],
    "file_count": asset["derived"]["file_count"],
    "language": asset["metadata"]["language"],
    "title": asset["metadata"]["title"],
    "author": asset["metadata"]["author"],
    "transcript_language": tr.get("language"),
    "transcript_model": tr.get("model"),
    "transcript_duration": tr.get("duration_seconds"),
    "first_3_segments": segs[:3],
    "last_2_segments": segs[-2:],
    "sample_phrases": picks,
    "frames_linked_in_transcript": len(fids),
    "index_bytes": index,
    "per_video_scenario_0_pct": round(s0_pct, 2),
    "per_video_scenario_1_pct": round(s1_pct, 2),
    "per_video_s0_after": s0_after,
    "per_video_s1_after": s1_after,
    "corpus_totals": storage["totals"],
    "corpus_scenarios": [
        {
            "id": s["id"],
            "key": s["key"],
            "label": s["label"],
            "savings_pct": s["savings_pct"],
            "before_bytes": s["before_bytes"],
            "after_bytes": s["after_bytes"],
            "saved_bytes": s["saved_bytes"],
            "removed": s.get("removed"),
        }
        for s in storage["scenarios"]
    ],
    "projection_2h": proj,
    "searches": searches,
    "offboarding": {
        "owner": off.get("owner"),
        "deletes_performed": off.get("deletes_performed"),
        "eligible": off.get("eligible") or off.get("recommendations") or off.get("items"),
        "keys": list(off.keys()),
    },
}
Path(r"C:\Users\suhas\ericsson-dso\data\longtest\verify-summary.json").write_text(
    json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
)
print("wrote verify-summary.json")
print("status", out["ready"], "model", out["model"], "seconds", out["pipeline_seconds"])
print("orig", orig, "derived", der, "frames", out["frame_count"], "segs", out["segment_count"])
print("s0", out["per_video_scenario_0_pct"], "s1", out["per_video_scenario_1_pct"])
print("corpus scenarios", [(s["id"], s["savings_pct"]) for s in out["corpus_scenarios"]])
print("searches", {k: (v["total"], v["ours"], v["ms"]) for k, v in searches.items()})
print("first segs:")
for s in segs[:4]:
    print(" ", s.get("id"), s.get("start"), s.get("frame_id"), (s.get("text") or "")[:200])
print("deletes_performed", off.get("deletes_performed"))
