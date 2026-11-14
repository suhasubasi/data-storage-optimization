import hashlib, json, re
from pathlib import Path
import httpx

API = "http://127.0.0.1:8000"
AID = "a_0ac641df"
ROOT = Path(r"C:\Users\suhas\ericsson-dso")
ORIG = ROOT / "data" / "originals" / AID
DER = ROOT / "data" / "derived" / AID
ISSUES = []
OK = []

def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def issue(msg):
    ISSUES.append(msg)

def ok(msg):
    OK.append(msg)

# env
env = (ROOT / "frontend" / ".env.local").read_text(encoding="utf-8", errors="replace")
if "VITE_USE_MOCKS=false" in env.replace(" ", ""):
    ok("frontend .env.local has VITE_USE_MOCKS=false")
else:
    issue(f"frontend .env.local unexpected: {env!r}")

c = httpx.Client(timeout=30)
detail = c.get(f"{API}/api/assets/{AID}").json()
timeline = c.get(f"{API}/api/assets/{AID}/timeline").json()
slides = c.get(f"{API}/api/assets/{AID}/slides").json()
assets = c.get(f"{API}/api/assets").json()

asset = detail["asset"]
# SHA of the file the API says it is serving
orig_files = list(ORIG.glob("*.mp4"))
if len(orig_files) != 1:
    issue(f"expected 1 original mp4, found {orig_files}")
    disk_sha = None
    orig_path = None
else:
    orig_path = orig_files[0]
    disk_sha = sha256(orig_path)
    if disk_sha == asset["sha256"]:
        ok(f"original on disk matches API sha256 {disk_sha[:16]}… ({orig_path.name}, {orig_path.stat().st_size} bytes)")
    else:
        issue(f"SHA mismatch disk={disk_sha} api={asset['sha256']}")
    if orig_path.stat().st_size != asset["bytes"]:
        issue(f"size mismatch disk={orig_path.stat().st_size} api={asset['bytes']}")

sample = ROOT / "data" / "samples" / "Your Agent Doesnt Need an LLM for Every Decision - Raymond Weitekamp OpenProse.mp4"
if sample.exists() and disk_sha:
    if sha256(sample) == disk_sha:
        ok("uploaded original is the same bytes as the file in data/samples")
    else:
        issue("uploaded original differs from the samples folder file")

# identity
if asset["id"] != AID:
    issue(f"asset id mismatch {asset['id']}")
if "OpenProse" not in asset["filename"] and "Weitekamp" not in asset["filename"]:
    issue(f"unexpected filename {asset['filename']}")
else:
    ok(f"filename is the OpenProse talk: {asset['filename']}")
if asset["status"] != "ready":
    issue(f"status is {asset['status']}")
else:
    ok("status is ready")
if asset["kind"] != "video":
    issue(f"kind is {asset['kind']}")
meta = detail.get("metadata") or {}
if abs((meta.get("duration_seconds") or 0) - 3108.014) > 1:
    issue(f"duration unexpected: {meta.get('duration_seconds')}")
else:
    ok(f"duration is {meta.get('duration_seconds')} s (~51 min 48 s), matches the source file")
if meta.get("title") and "OpenProse" in meta["title"] and "Weitekamp" in meta["title"]:
    ok(f"metadata title is the real talk: {meta['title']}")
else:
    issue(f"metadata title unexpected: {meta.get('title')}")
model = (detail.get("pipeline") or {}).get("model") or ""
if "stub" in model.lower():
    issue(f"transcript model is a stub: {model}")
elif "faster-whisper" in model.lower():
    ok(f"model is real ASR: {model}")
else:
    issue(f"unexpected model: {model}")

# no other asset id mixed into this derived folder / urls
tl_id = timeline.get("asset_id")
if tl_id != AID:
    issue(f"timeline asset_id is {tl_id}, not {AID}")
else:
    ok("timeline belongs to a_0ac641df")

frames = timeline.get("frames") or []
segs = timeline.get("segments") or []
ok(f"timeline has {len(frames)} frames and {len(segs)} segments")
if len(frames) != (detail.get("derived") or {}).get("frame_count"):
    issue(f"frame count mismatch timeline={len(frames)} detail={detail['derived'].get('frame_count')}")
if len(segs) != (detail.get("derived") or {}).get("segment_count"):
    issue(f"segment count mismatch timeline={len(segs)} detail={detail['derived'].get('segment_count')}")

# frame files and URLs
id_pat = re.compile(r"/a_[0-9a-f]+/")
frame_by_id = {}
url_foreign = []
missing = []
overlap_issues = 0
prev_end = None
for i, f in enumerate(frames):
    frame_by_id[f["id"]] = f
    url = f.get("image_url") or f.get("url") or f.get("path") or ""
    ids_in_url = id_pat.findall(str(url))
    if any(x.strip("/") != AID for x in ids_in_url):
        url_foreign.append((f["id"], url))
    # file on disk
    fid = f["id"]
    dest = DER / "frames" / f"{fid}.webp"
    # also path field
    rel = f.get("path")
    if rel:
        dest2 = DER / rel
        dest = dest2 if dest2.exists() else dest
    if not dest.exists():
        missing.append(fid)
    if prev_end is not None and abs(f["t_start"] - prev_end) > 0.05 and f["t_start"] < prev_end:
        overlap_issues += 1
        if overlap_issues <= 5:
            issue(f"frame overlap/out-of-order {frames[i-1]['id']} t_end={prev_end} vs {fid} t_start={f['t_start']}")
    if f["t_end"] <= f["t_start"]:
        issue(f"frame {fid} has t_end <= t_start ({f['t_start']}–{f['t_end']})")
    prev_end = f["t_end"]

if not url_foreign:
    ok("every frame URL points only at a_0ac641df, none at another asset")
else:
    issue(f"frame URLs point at other assets: {url_foreign[:5]}")
if not missing:
    ok(f"all {len(frames)} frame files exist on disk under derived/{AID}/frames")
else:
    issue(f"missing frame files: {missing[:10]}")

# last frame should reach duration
dur = timeline.get("duration_seconds") or meta.get("duration_seconds")
if frames and abs(frames[-1]["t_end"] - dur) > 1.5:
    issue(f"last frame t_end={frames[-1]['t_end']} vs duration={dur}")
else:
    ok(f"last frame ends at {frames[-1]['t_end']} s, matching the {dur} s duration")
if frames and frames[0]["t_start"] != 0:
    issue(f"first frame starts at {frames[0]['t_start']}, not 0")
else:
    ok("first key frame starts at 0:00")

# segments vs frames
bad_link = 0
bad_time = 0
examples = []
for s in segs:
    urlish = json.dumps(s)
    if AID not in str(timeline.get("asset_id")):
        pass
    fid = s.get("frame_id")
    if fid not in frame_by_id:
        bad_link += 1
        if len(examples) < 5:
            examples.append(f"segment {s.get('id')} frame_id={fid} not in frame list")
        continue
    fr = frame_by_id[fid]
    t = s.get("start")
    # official rule: frame on screen when segment STARTS
    if not (fr["t_start"] <= t < fr["t_end"] or (t >= frames[-1]["t_start"] and fid == frames[-1]["id"])):
        # allow tiny float issues
        if not (fr["t_start"] - 0.05 <= t < fr["t_end"] + 0.05):
            bad_time += 1
            if len(examples) < 8:
                examples.append(
                    f"{s.get('id')} start={t} linked to {fid} ({fr['t_start']}–{fr['t_end']})"
                )

if bad_link:
    issue(f"{bad_link} segments point at a missing frame_id; e.g. {examples}")
else:
    ok("every transcript segment's frame_id exists in this recording's frame list")
if bad_time:
    issue(f"{bad_time} segments are linked to a frame that was not on screen when the sentence starts; e.g. {examples}")
else:
    ok("every segment is linked to the key frame that was on screen when that sentence starts")

# time order of segments
backwards = 0
for a, b in zip(segs, segs[1:]):
    if b["start"] + 0.01 < a["start"]:
        backwards += 1
if backwards:
    issue(f"{backwards} segments go backwards in time")
else:
    ok("transcript timestamps are in order")

# contamination: words from the OTHER test corpus should not appear here
foreign_words = [
    "goggles",
    "yellow cabinet",
    "room B12",
    "B twelve",
    "spill kit",
    "access points",
    "wifi-campus",
    "procurement",
    "25,000",
    "handover",
    "lab safety",
]
joined = " ".join((s.get("text") or "") for s in segs).lower()
found_foreign = [w for w in foreign_words if w.lower() in joined]
if found_foreign:
    issue(f"transcript contains text from earlier test files: {found_foreign}")
else:
    ok("transcript has none of the earlier test-file phrases (goggles, yellow cabinet, wifi, handover, etc.)")

# this talk should be present
needles = ["Raymond", "Recursive Decision", "Operating System"]
missing_needles = [n for n in needles if n.lower() not in joined.lower()]
if missing_needles:
    issue(f"expected talk phrases missing from transcript: {missing_needles}")
else:
    ok("transcript is clearly this talk (Raymond, Recursive Decision, Operating System)")

# other videos' derived frames must not be these files (compare sha of f1 vs lab briefing f1)
other = ROOT / "data" / "derived" / "a_e34668e5" / "frames" / "f1.webp"
this_f1 = DER / "frames" / "f1.webp"
if other.exists() and this_f1.exists():
    if sha256(other) == sha256(this_f1):
        issue("OpenProse f1.webp is identical to lab-briefing.mp4 f1.webp — frames are mixed up")
    else:
        ok("OpenProse key frames are not the same files as the lab-briefing video frames")

# slides endpoint should be empty or not document slides from another asset
slide_list = slides.get("slides") or slides.get("items") or (slides if isinstance(slides, list) else [])
if slides.get("asset_id") and slides.get("asset_id") != AID:
    issue(f"slides endpoint is for {slides.get('asset_id')}")
if slide_list:
    issue(f"unexpected slides on a video asset: {len(slide_list)}")
else:
    ok("slides endpoint is empty for this video (slides belong to PDFs, not mixed in)")

# library list: this id is unique, filename not reused by another id
same_name = [a for a in assets["assets"] if a["filename"] == asset["filename"] and a["id"] != AID]
if same_name:
    issue(f"another asset shares this filename: {same_name}")
else:
    ok("this filename is unique in the library (no second copy mixed under another id)")

# original_url and derived urls
if asset.get("original_url") and AID not in asset["original_url"]:
    issue(f"original_url points elsewhere: {asset.get('original_url')}")
else:
    ok(f"original_url is /files/originals/{AID}/…")

# manifest asset_id
man = json.loads((DER / "manifest.json").read_text(encoding="utf-8"))
if man.get("asset_id") != AID:
    issue(f"manifest asset_id is {man.get('asset_id')}")
else:
    ok("manifest.json on disk is for a_0ac641df")
if "lab-briefing" in json.dumps(man).lower() or "wifi-campus" in json.dumps(man).lower():
    issue("manifest mentions another sample file")
orig_path_in_man = (man.get("original") or {}).get("path") or ""
if "OpenProse" not in orig_path_in_man and "Weitekamp" not in orig_path_in_man:
    # may be relative like originals/a_0ac641df/filename
    if AID not in orig_path_in_man:
        issue(f"manifest original path unexpected: {orig_path_in_man}")
    else:
        ok(f"manifest original path: {orig_path_in_man}")
else:
    ok(f"manifest original path: {orig_path_in_man}")

# pickup a few segment texts around start/middle/end
picks = []
if segs:
    mid = segs[len(segs)//2]
    late = segs[int(len(segs)*0.8)]
    picks = [
        {"where": "start", **{k: segs[0].get(k) for k in ("id","start","end","frame_id","text")}},
        {"where": "middle", **{k: mid.get(k) for k in ("id","start","end","frame_id","text")}},
        {"where": "late", **{k: late.get(k) for k in ("id","start","end","frame_id","text")}},
        {"where": "end", **{k: segs[-1].get(k) for k in ("id","start","end","frame_id","text")}},
    ]

out = {
    "ok": OK,
    "issues": ISSUES,
    "counts": {"frames": len(frames), "segments": len(segs), "issues": len(ISSUES)},
    "identity": {
        "id": asset["id"],
        "filename": asset["filename"],
        "sha256": asset["sha256"],
        "bytes": asset["bytes"],
        "owner": asset["owner"],
        "source_system": asset["source_system"],
        "title": meta.get("title"),
        "duration_seconds": meta.get("duration_seconds"),
        "model": model,
        "original_url": asset.get("original_url"),
    },
    "samples": picks,
    "first_last_frames": {
        "first": {k: frames[0].get(k) for k in ("id","t_start","t_end","image_url","path") if k in frames[0] or True},
        "last": {k: frames[-1].get(k) for k in ("id","t_start","t_end","image_url","path") if True},
    },
}
Path(r"C:\Users\suhas\ericsson-dso\data\longtest\audit-recording.json").write_text(
    json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
)
print(f"ISSUES={len(ISSUES)} OK={len(OK)}")
for m in ISSUES:
    print("ISSUE:", m)
for m in OK:
    print("OK:", m)
print("---SAMPLES---")
for p in picks:
    print(p["where"], p.get("id"), p.get("start"), p.get("frame_id"), (p.get("text") or "")[:200])
