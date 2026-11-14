import httpx
httpx_timeout = httpx.Timeout(3600.0)
import json, time, sys, urllib.request, pathlib
import httpx as requests
API = "http://127.0.0.1:8000"
VID = pathlib.Path(r"C:\Users\suhas\ericsson-dso\data\samples\Your Agent Doesnt Need an LLM for Every Decision - Raymond Weitekamp OpenProse.mp4")
OUT = pathlib.Path(r"C:\Users\suhas\ericsson-dso\data\longtest")
log = open(OUT / "run.log", "a", encoding="utf-8")
def L(*a):
    s = time.strftime("%H:%M:%S") + " " + " ".join(str(x) for x in a)
    print(s, flush=True); log.write(s + "\n"); log.flush()
L("health", requests.get(API + "/health", timeout=10).json())
t0 = time.perf_counter()
with open(VID, "rb") as f:
    r = requests.post(API + "/api/assets", files={"file": (VID.name, f, "video/mp4")},
                      data={"source_system": "ericsson_play", "owner": "erik"}, timeout=httpx_timeout)
upload_ms = (time.perf_counter() - t0) * 1000
L("upload", r.status_code, round(upload_ms), r.text[:500])
r.raise_for_status()
asset = r.json()
aid = asset["id"]
t1 = time.perf_counter(); t1wall = time.time()
r = requests.post(f"{API}/api/assets/{aid}/process", timeout=60)
L("process", r.status_code, r.text[:500])
r.raise_for_status()
job = r.json(); jid = job["id"]
state = {"asset": asset, "upload_ms": upload_ms, "job_start": job, "process_post_epoch": t1wall}
(OUT / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
last = None
while True:
    try:
        j = requests.get(f"{API}/api/jobs/{jid}", timeout=30).json()
    except Exception as e:
        L("poll error", e); time.sleep(30); continue
    key = (j.get("status"), j.get("stage"), round(float(j.get("progress") or 0), 2))
    if key != last:
        L("job", json.dumps(j)[:400]); last = key
    if j.get("status") in ("ready", "failed", "error", "done", "succeeded"):
        break
    time.sleep(15)
state["observed_process_s"] = time.perf_counter() - t1
state["job_end"] = j
(OUT / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
L("END", j.get("status"), round(state["observed_process_s"], 1))

