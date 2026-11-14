import json, time, pathlib, httpx
API = "http://127.0.0.1:8000"; JID = "j_9341b715e1"
OUT = pathlib.Path(r"C:\Users\suhas\ericsson-dso\data\longtest")
log = open(OUT / "run2.log", "a", encoding="utf-8")
def L(*a):
    s = time.strftime("%H:%M:%S") + " " + " ".join(str(x) for x in a); log.write(s + "\n"); log.flush()
t0 = time.time(); last = None
while True:
    try: j = httpx.get(f"{API}/api/jobs/{JID}", timeout=30).json()
    except Exception as e: L("poll error", e); time.sleep(30); continue
    key = (j.get("status"), j.get("stage"), round(float(j.get("progress") or 0), 2))
    if key != last: L("job", json.dumps(j)); last = key
    if j.get("status") in ("ready", "failed"): break
    time.sleep(15)
(OUT / "job2_end.json").write_text(json.dumps({"job": j, "poll_seconds_from_my_start": time.time() - t0}, indent=2), encoding="utf-8")
L("END", j.get("status"))
