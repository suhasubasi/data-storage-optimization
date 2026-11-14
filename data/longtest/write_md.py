import json, pathlib
p = pathlib.Path(r"C:\Users\suhas\ericsson-dso\data\long-video-results.json")
r = json.loads(p.read_text(encoding="utf-8"))
r["frames_quality"]["frame_size"] = "1280x720 WebP q75 (scaled from 2560x1440; frame_max_width_px=1280)"
r["search_extra"] = {"OpenProse": 0, "Weitekamp": 0, "note": "Title tag contains 'Raymond Weitekamp, OpenProse' (stored in asset metadata) but search returns 0 hits: metadata title is not indexed, and ASR misspelled the name."}
p.write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
s = r["storage_per_video"]; d = r["derived"]; pr = r["projection_2h_1GB"]; fq = r["frames_quality"]; t = r["transcript"]
corp = {x["id"]: x for x in r["storage_report_corpus"]["scenarios"]}
hits = [x for x in r["search"] if not x["negative"]]; ok = sum(1 for x in hits if x["expected_segment_hit"])
wi = fq["what_if_not_measured_pipeline_output"]["rows"]
L = []
L.append("# Long real-video test: OpenProse talk (Raymond Weitekamp)\n")
L.append("Source: real recording provided by the user (data/samples). Nothing generated.\n")
L.append(f"- Video: {r['probe']['duration_seconds']:.1f} s ({r['probe']['duration_seconds']/60:.1f} min), {r['probe']['original_bytes']:,} bytes, AV1 2560x1440 60 fps ~{r['probe']['video']['bitrate_bps']//1000} kb/s + AAC stereo 128 kb/s")
L.append(f"- Asset `a_0ac641df`, job `j_9341b715e1`: status ready. First job `j_8d1ca20007` failed (Windows WinError 5 on progress.json rename) and was fixed in common.py before the retry.")
L.append(f"- Upload: {r['timings']['upload_ms']/1000:.2f} s. Process: {r['timings']['manifest_pipeline']['seconds']:.1f} s ({r['timings']['manifest_pipeline']['seconds']/60:.1f} min) per manifest; job 23:13:08 to 23:23:04 UTC (00:13 to 00:23 CET). That is about {r['probe']['duration_seconds']/r['timings']['manifest_pipeline']['seconds']:.1f}x real time.")
L.append(f"- API: search 3.8 to 5.2 ms, storage report {r['timings']['storage_report_ms']} ms, offboarding {r['timings']['offboarding_ms']} ms\n")
L.append("## Derived data")
L.append(f"- transcript.json {d['transcript_bytes']:,} B ({t['segment_count']} segments, {t['words']} words, language {t['language']}, {t['model']})")
L.append(f"- frames: {d['frame_count']} WebP, {d['frame_bytes_total']:,} B ({fq['frame_size']})")
L.append(f"- manifest.json {d['manifest_bytes']:,} B")
L.append(f"- Total derived {d['derived_total_bytes_on_disk']:,} B. Frames make up {d['frame_bytes_total']/d['derived_total_bytes_on_disk']*100:.1f}% of it.\n")
L.append("## Storage, measured. Savings % = (O - A) / O x 100")
L.append(f"Per video. O = {s['O']:,}. Index I = whole dso.sqlite {s['I_index_whole_db_bytes']:,} B (conservative).")
L.append(f"- Scenario 0 (keep original): A = {s['scenario0']['A']:,} -> **{s['scenario0']['savings_pct']:.2f}%**")
L.append(f"- Scenario 1 (replace video with derived, after approval): A = {s['scenario1']['A']:,} -> **{s['scenario1']['savings_pct']:.2f}%**")
L.append(f"- Corpus (/api/storage/report, 7 assets): S0 {corp[0]['savings_pct']}%, S1 {corp[1]['savings_pct']}%, S3 {corp[3]['savings_pct']}%\n")
L.append("Compared with Ericsson's example (~50 KB text + ~2 MB frames, ~99%): our text is 146 KB for 52 min. The gap is the frames: 22.1 MB, not ~2 MB.")
L.append(f"The talk embeds screen-recorded game demos with a live webcam overlay, so the change detector keeps almost one frame per second during demos. {fq['frames_held_le_1s']} of {fq['count']} frames are on screen for only 1 s, and only {fq['frames_held_ge_10s']} stay for 10 s or more.\n")
L.append("What-if, not pipeline output: if we kept only frames that stay on screen for at least N seconds:")
for w in wi:
    L.append(f"- N = {w['keep_frames_held_at_least_s']} s: {w['frames']} frames, {w['frame_bytes']:,} B -> scenario 1 {w['savings_pct']:.2f}%")
L.append("\n## Projection to 2 h / 1 GB (not measured)")
for a in pr["assumptions"]: L.append(f"- {a}")
L.append(f"- Scenario 1: {pr['savings_pct_high_A']:.2f}% (frames scale with duration) to {pr['savings_pct_low_A']:.2f}% (same slides). Frame bytes {pr['frame_bytes_high']:,} to {pr['frame_bytes_low']:,}; transcript ~{pr['transcript_bytes']:,} B.")
L.append("- With the current frame selection we do NOT reach 99% on this kind of video. The 1 GB claim also assumes a lower bitrate (1.1 kb/s per second of video) than this file has. ~99% needs about 2 MB of frames, which needs stricter frame selection.\n")
L.append(f"## Search ({ok}/{len(hits)} expected segments found; negative control 'kubernetes' returned 0)")
for x in r["search"]:
    th = x["top_hit"]
    L.append(f"- `{x['q']}`: total {x['total']}, expected {x['expected_segment']} hit={x['expected_segment_hit']}, top {th['item_id']+' @'+str(th['start'])+'s frame '+th['frame_id'] if th else 'none'}, {x['ms']} ms")
L.append("- `OpenProse` / `Weitekamp`: 0 hits. The title is not indexed, and ASR heard 'Whitecamp'.\n")
L.append("## Quality")
for q in t["quality_notes"]: L.append(f"- {q}")
L.append(f"- Frames: {fq['count']} over {fq['duration_seconds']/60:.0f} min ({fq['frames_per_minute']}/min). Slide sections are sensible, but demo and webcam sections are over-sampled.")
L.append(f"- Offboarding (owner erik): recommendation keep, deletes_performed false = {r['offboarding']['deletes_performed_false_present']}. Not an exact-copy candidate.")
pathlib.Path(r"C:\Users\suhas\ericsson-dso\data\long-video-results.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
