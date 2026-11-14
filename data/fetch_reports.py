import json, time
from pathlib import Path
import httpx
BASE = "http://127.0.0.1:8000"
c = httpx.Client(timeout=60.0)
out = {}
t = time.perf_counter()
s = c.get(f"{BASE}/api/storage/report")
out["storage_ms"] = round((time.perf_counter()-t)*1000,1)
out["storage_status"] = s.status_code
out["storage"] = s.json() if s.status_code < 400 else s.text
for owner in ("carl", "anna", "bjorn", "dana"):
    t = time.perf_counter()
    o = c.get(f"{BASE}/api/offboarding", params={"owner": owner})
    out[f"offboarding_{owner}"] = {"ms": round((time.perf_counter()-t)*1000,1), "status": o.status_code, "body": o.json() if o.status_code < 400 else o.text}
t = time.perf_counter()
ex = c.get(f"{BASE}/api/export.jsonl")
nlines = 0
if ex.status_code < 400 and ex.content:
    nlines = ex.text.count("\n") + (0 if ex.text.endswith("\n") else 1)
out["export"] = {"ms": round((time.perf_counter()-t)*1000,1), "status": ex.status_code, "lines": nlines, "bytes": len(ex.content)}
Path(r"C:\Users\suhas\ericsson-dso\data\live-reports.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print("WROTE reports")
