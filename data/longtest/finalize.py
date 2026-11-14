import json, httpx, pathlib
p = pathlib.Path(r"C:\Users\suhas\ericsson-dso\data\long-video-results.json")
r = json.loads(p.read_text(encoding="utf-8"))
a = httpx.get("http://127.0.0.1:8000/api/assets/a_0ac641df", timeout=30).json()
r["asset_detail"] = {k: a["asset"].get(k) for k in ("id","status","kind","bytes","derived_bytes","owner","source_system","sha256")}
r["asset_detail"]["metadata"] = a.get("metadata"); r["asset_detail"]["pipeline"] = a.get("pipeline")
fr = r["derived"]["frames"]; O = r["probe"]["original_bytes"]
nonframe = r["derived"]["derived_total_bytes_on_disk"] - r["derived"]["frame_bytes_total"]; I = r["storage_per_video"]["I_index_whole_db_bytes"]
wi = []
for th in (5, 10, 30):
    k = [f for f in fr if f["t_end"] - f["t_start"] >= th]; fb = sum(f["bytes"] for f in k)
    A = nonframe + fb + I
    wi.append({"keep_frames_held_at_least_s": th, "frames": len(k), "frame_bytes": fb, "A": A, "savings_pct": round((O-A)/O*100, 4)})
holds = [f["t_end"] - f["t_start"] for f in fr]
r["frames_quality"].update({
  "frames_held_le_1s": sum(h <= 1 for h in holds), "frames_held_le_2s": sum(h <= 2 for h in holds), "frames_held_ge_10s": sum(h >= 10 for h in holds),
  "frames_per_10min_bucket": {str(b): sum(1 for f in fr if int(f["t_start"]//600) == b) for b in range(6)},
  "frame_size": "1024x576 WebP (scaled from 2560x1440, frame_max_width_px=1024 per thresholds)",
  "observation": "Visually checked f300/f301: the talk embeds screen-recorded game demos (Factorio/Doom-style clips) plus a live webcam overlay. Those regions change every 1 s sample, so the pHash/pixel-change rule keeps nearly every sampled second during demos. 415 of 670 frames are on screen for only 1 s.",
  "what_if_not_measured_pipeline_output": {"note": "Offline what-if on the measured frame list: keep only frames that stay on screen >= N s. NOT what the pipeline produced; shows how sensitive savings are to frame selection.", "rows": wi},
})
r["first_attempt"] = {"job_id": "j_8d1ca20007", "status": "failed", "stage": "extracting key frames", "error": "WinError 5 PermissionError on os.replace(progress.json.tmp -> progress.json)", "fix": "Parent agent patched pipeline/dso_pipeline/common.py write_json_atomic (retries + in-place fallback, throttled progress writes) and restarted processing on the same asset as job j_9341b715e1."}
r["transcript"]["quality_notes"] = [
  "Language auto-detected en; 701 segments, 7370 words, all segments linked to a frame_id.",
  "Opening line names the speaker and talk topic (recursive decision models); ending mentions OSO at oso.computer. Topics (System 1/2, Danny Kahneman, Recursive Language Models/RLM, Doom demo, latency in milliseconds) are present and coherent.",
  "ASR errors: speaker name heard as 'Raymond Whitecamp' (Weitekamp); the product name is transcribed inconsistently as 'Jeff' and 'Jev'; 'OpenProse' never appears in the transcript (0 matches for 'prose'), so a search for OpenProse/Weitekamp will not hit spoken text. Filler words (um, uh) kept. No garbage/hallucination loops observed in the reviewed text.",
]
p.write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(wi)); print(r["asset_detail"]["metadata"])
