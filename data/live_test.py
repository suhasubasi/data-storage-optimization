import json, time, sys
from pathlib import Path
import httpx

BASE = "http://127.0.0.1:8000"
SAMPLES = Path(r"C:\Users\suhas\ericsson-dso\data\samples")
FILES = [
    ("wifi-campus-plan.pdf", "sharepoint", "anna"),
    ("wifi-campus-plan (1).pdf", "onedrive", "carl"),
    ("wifi-campus-plan-revB.pdf", "sharepoint", "anna"),
    ("lab-safety-briefing.pdf", "sharepoint", "bjorn"),
    ("q3-procurement-notes.pdf", "onedrive", "dana"),
    ("lab-briefing.mp4", "ericsson_play", "bjorn"),
]

out = {"steps": []}

def log(name, ms, extra=None):
    row = {"name": name, "ms": round(ms, 1)}
    if extra:
        row.update(extra)
    out["steps"].append(row)
    print(f"{name}: {ms:.0f} ms", extra or "", flush=True)

client = httpx.Client(timeout=600.0)

t0 = time.perf_counter()
h = client.get(f"{BASE}/health")
h.raise_for_status()
log("health", (time.perf_counter() - t0) * 1000, {"body": h.json()})

ids = []
for name, source, owner in FILES:
    path = SAMPLES / name
    t = time.perf_counter()
    with path.open("rb") as f:
        r = client.post(
            f"{BASE}/api/assets",
            files={"file": (name, f, "application/octet-stream")},
            data={"source_system": source, "owner": owner},
        )
    ms = (time.perf_counter() - t) * 1000
    if r.status_code >= 400:
        log(f"upload {name}", ms, {"error": r.status_code, "text": r.text})
        continue
    asset = r.json()
    aid = asset["id"]
    ids.append((name, aid, source, owner))
    log(f"upload {name}", ms, {"id": aid, "bytes": asset.get("original_bytes") or asset.get("size") or path.stat().st_size})

    t = time.perf_counter()
    pr = client.post(f"{BASE}/api/assets/{aid}/process")
    if pr.status_code >= 400:
        log(f"process start {name}", (time.perf_counter() - t) * 1000, {"error": pr.status_code, "text": pr.text})
        continue
    job = pr.json()
    job_id = job["id"]
    while True:
        jr = client.get(f"{BASE}/api/jobs/{job_id}")
        jr.raise_for_status()
        job = jr.json()
        status = job.get("status")
        if status in ("done", "failed", "error"):
            break
        time.sleep(0.5)
    ms = (time.perf_counter() - t) * 1000
    log(f"process {name}", ms, {"status": status, "job": job})

# Queries
t = time.perf_counter()
assets = client.get(f"{BASE}/api/assets")
assets.raise_for_status()
log("list assets", (time.perf_counter() - t) * 1000, {"count": len(assets.json()) if isinstance(assets.json(), list) else assets.json()})

for q in ["goggles", "access points", "procurement", "yellow cabinet", "25,000", "handover"]:
    t = time.perf_counter()
    # try query param q
    r = client.get(f"{BASE}/api/search", params={"q": q})
    ms = (time.perf_counter() - t) * 1000
    if r.status_code >= 400:
        log(f"search {q!r}", ms, {"error": r.status_code, "text": r.text[:500]})
    else:
        body = r.json()
        hits = body if isinstance(body, list) else body.get("hits") or body.get("results") or body
        n = len(hits) if isinstance(hits, list) else "n/a"
        preview = []
        if isinstance(hits, list):
            for h in hits[:3]:
                preview.append({k: h.get(k) for k in ("asset_id", "text", "timestamp", "kind", "page", "frame_id", "slide_id") if k in h})
        log(f"search {q!r}", ms, {"n": n, "preview": preview})

t = time.perf_counter()
d = client.get(f"{BASE}/api/duplicates")
ms = (time.perf_counter() - t) * 1000
if d.status_code >= 400:
    log("duplicates", ms, {"error": d.status_code, "text": d.text[:800]})
else:
    body = d.json()
    log("duplicates", ms, {"body_keys": list(body) if isinstance(body, dict) else "list", "summary": body if not isinstance(body, list) or len(json.dumps(body)) < 4000 else {"n": len(body)}})

t = time.perf_counter()
s = client.get(f"{BASE}/api/storage-report")
ms = (time.perf_counter() - t) * 1000
if s.status_code >= 400:
    # maybe different path
    s2 = client.get(f"{BASE}/api/storage")
    log("storage report", ms, {"error": s.status_code, "text": s.text[:500], "alt": s2.status_code})
else:
    log("storage report", ms, {"report": s.json()})

t = time.perf_counter()
o = client.get(f"{BASE}/api/offboarding", params={"owner": "carl"})
ms = (time.perf_counter() - t) * 1000
log("offboarding carl", ms, {"status": o.status_code, "body": o.json() if o.status_code < 400 else o.text[:800]})

t = time.perf_counter()
o2 = client.get(f"{BASE}/api/offboarding", params={"owner": "anna"})
ms = (time.perf_counter() - t) * 1000
log("offboarding anna", ms, {"status": o2.status_code, "body": o2.json() if o2.status_code < 400 else o2.text[:800]})

t = time.perf_counter()
ex = client.get(f"{BASE}/api/export.jsonl")
ms = (time.perf_counter() - t) * 1000
text = ex.text if ex.status_code < 400 else ex.text[:400]
nlines = text.count("\n") + (1 if text and not text.endswith("\n") else 0) if ex.status_code < 400 else 0
log("export jsonl", ms, {"status": ex.status_code, "lines": nlines, "bytes": len(ex.content)})

out_path = Path(r"C:\Users\suhas\ericsson-dso\data\live-test-results.json")
out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
print("WROTE", out_path, flush=True)
