import json, time
from pathlib import Path
import httpx

BASE = "http://127.0.0.1:8000"
client = httpx.Client(timeout=600.0)
out = {"steps": []}

def log(name, ms, extra=None):
    row = {"name": name, "ms": round(ms, 1)}
    if extra:
        row.update(extra)
    out["steps"].append(row)
    print(f"{name}: {ms:.0f} ms", extra or "", flush=True)

h = client.get(f"{BASE}/health")
h.raise_for_status()
assets = client.get(f"{BASE}/api/assets").json()["assets"]
print("assets", [(a["id"], a["filename"], a["status"]) for a in assets], flush=True)

for a in assets:
    aid, name = a["id"], a["filename"]
    t = time.perf_counter()
    pr = client.post(f"{BASE}/api/assets/{aid}/process")
    if pr.status_code >= 400:
        log(f"process start {name}", (time.perf_counter()-t)*1000, {"error": pr.status_code, "text": pr.text})
        continue
    job = pr.json()
    job_id = job["id"]
    while True:
        job = client.get(f"{BASE}/api/jobs/{job_id}").json()
        status = job.get("status")
        if status in ("done", "failed", "error"):
            break
        time.sleep(0.5)
    log(f"process {name}", (time.perf_counter()-t)*1000, {"status": status, "stage": job.get("stage"), "error": job.get("error"), "progress": job.get("progress")})

assets = client.get(f"{BASE}/api/assets").json()["assets"]
log("list assets", 0, {"items": [{"id": a["id"], "filename": a["filename"], "status": a["status"], "derived_bytes": a.get("derived_bytes")} for a in assets]})

for q in ["goggles", "access points", "procurement", "yellow cabinet", "25,000", "handover", "wifi"]:
    t = time.perf_counter()
    r = client.get(f"{BASE}/api/search", params={"q": q})
    ms = (time.perf_counter()-t)*1000
    if r.status_code >= 400:
        log(f"search {q!r}", ms, {"error": r.status_code, "text": r.text[:400]})
        continue
    body = r.json()
    hits = body if isinstance(body, list) else body.get("hits") or body.get("results") or []
    preview = []
    if isinstance(hits, list):
        for h in hits[:4]:
            preview.append({k: h.get(k) for k in ("filename", "text", "snippet", "start_s", "timestamp", "kind", "page", "slide_id", "frame_id") if k in h or True})
            preview[-1] = {k: h.get(k) for k in h if k in ("asset_id","filename","text","snippet","start_s","end_s","timestamp","kind","page","slide_id","frame_id","image_url")}
    log(f"search {q!r}", ms, {"n": len(hits) if isinstance(hits, list) else body, "preview": preview})

t = time.perf_counter()
d = client.get(f"{BASE}/api/duplicates").json()
log("duplicates", (time.perf_counter()-t)*1000, {
    "counts": d.get("counts"),
    "groups": [{
        "id": g.get("id"), "type": g.get("type"), "needs_review": g.get("needs_review"),
        "members": [m.get("filename") or m.get("asset_id") for m in g.get("members", [])]
    } for g in d.get("groups", [])]
})

t = time.perf_counter()
s = client.get(f"{BASE}/api/storage/report")
log("storage report", (time.perf_counter()-t)*1000, {"status": s.status_code, "report": s.json() if s.status_code < 400 else s.text[:500]})

for owner in ("carl", "anna", "bjorn", "dana"):
    t = time.perf_counter()
    o = client.get(f"{BASE}/api/offboarding", params={"owner": owner})
    log(f"offboarding {owner}", (time.perf_counter()-t)*1000, {"status": o.status_code, "body": o.json() if o.status_code < 400 else o.text[:500]})

t = time.perf_counter()
ex = client.get(f"{BASE}/api/export.jsonl")
nlines = 0
if ex.status_code < 400 and ex.content:
    nlines = ex.text.count("\n") + (0 if ex.text.endswith("\n") else 1)
log("export jsonl", (time.perf_counter()-t)*1000, {"status": ex.status_code, "lines": nlines, "bytes": len(ex.content)})

path = Path(r"C:\Users\suhas\ericsson-dso\data\live-test-results.json")
path.write_text(json.dumps(out, indent=2), encoding="utf-8")
print("WROTE", path, flush=True)
