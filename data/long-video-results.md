# Long real-video test: OpenProse talk (Raymond Weitekamp)

Source: real recording provided by the user (data/samples). Nothing generated.

- Video: 3108.0 s (51.8 min), 347,928,702 bytes, AV1 2560x1440 60 fps ~763 kb/s + AAC stereo 128 kb/s
- Asset `a_0ac641df`, job `j_9341b715e1`: status ready. First job `j_8d1ca20007` failed (Windows WinError 5 on progress.json rename) and was fixed in common.py before the retry.
- Upload: 1.14 s. Process: 594.7 s (9.9 min) per manifest; job 23:13:08 to 23:23:04 UTC (00:13 to 00:23 CET). That is about 5.2x real time.
- API: search 3.8 to 5.2 ms, storage report 7.6 ms, offboarding 3.8 ms

## Derived data
- transcript.json 145,930 B (701 segments, 7370 words, language en, faster-whisper small int8)
- frames: 670 WebP, 22,134,204 B (1280x720 WebP q75 (scaled from 2560x1440; frame_max_width_px=1280))
- manifest.json 350,520 B
- Total derived 22,630,654 B. Frames make up 97.8% of it.

## Storage, measured. Savings % = (O - A) / O x 100
Per video. O = 347,928,702. Index I = whole dso.sqlite 450,560 B (conservative).
- Scenario 0 (keep original): A = 371,009,916 -> **-6.63%**
- Scenario 1 (replace video with derived, after approval): A = 23,081,214 -> **93.37%**
- Corpus (/api/storage/report, 7 assets): S0 -6.7061%, S1 93.2897%, S3 93.2906%

Compared with Ericsson's example (~50 KB text + ~2 MB frames, ~99%): our text is 146 KB for 52 min. The gap is the frames: 22.1 MB, not ~2 MB.
The talk embeds screen-recorded game demos with a live webcam overlay, so the change detector keeps almost one frame per second during demos. 415 of 670 frames are on screen for only 1 s, and only 69 stay for 10 s or more.

What-if, not pipeline output: if we kept only frames that stay on screen for at least N seconds:
- N = 5 s: 99 frames, 3,115,076 B -> scenario 1 98.83%
- N = 10 s: 69 frames, 2,044,450 B -> scenario 1 99.14%
- N = 30 s: 25 frames, 709,322 B -> scenario 1 99.52%

## Projection to 2 h / 1 GB (not measured)
- Projection, not a measurement. 2-hour recording of ~1 GB (10^9 bytes) with the same speech density as this talk.
- transcript.json bytes scale linearly with duration (k = 7200 / measured duration).
- Frames: lower bound = same distinct slides as this talk (frame bytes unchanged); upper bound = frame count/bytes scale linearly with duration.
- manifest.json scales linearly (upper bound); index bytes = current measured dso.sqlite size scaled by k for this asset's share is not modelled; we add the current whole DB size + transcript-sized FTS growth (approx 2x transcript text) as a conservative add-on.
- Scenario 1: 94.69% (frames scale with duration) to 97.61% (same slides). Frame bytes 51,275,915 to 22,134,204; transcript ~338,060 B.
- With the current frame selection we do NOT reach 99% on this kind of video. (1 GB per 2 h is about 1.11 Mb/s; this file is 0.90 Mb/s, so the 1 GB baseline is slightly more generous than this file.) ~99% needs about 2 MB of frames, which needs stricter frame selection.

## Search (8/8 expected segments found; negative control 'kubernetes' returned 0)
- `Danny Kahneman`: total 2, expected s6 hit=True, top s6 @35.24s frame f3, 5.2 ms
- `recursivecodingagents`: total 1, expected s75 hit=True, top s75 @401.56s frame f17, 5.2 ms
- `Jeff plays doom`: total 1, expected s114 hit=True, top s114 @595.2s frame f46, 4.3 ms
- `zero shot`: total 1, expected s26 hit=True, top s26 @150.74s frame f5, 4.0 ms
- `compaction`: total 1, expected s100 hit=True, top s100 @528.28s frame f35, 4.3 ms
- `Recursive Language Models`: total 3, expected s41 hit=True, top s70 @386.96s frame f17, 4.6 ms
- `oso computer`: total 3, expected s700 hit=True, top s700 @3104.11s frame f670, 4.5 ms
- `45 milliseconds`: total 1, expected s605 hit=True, top s605 @2780.05s frame f585, 3.8 ms
- `kubernetes`: total 0, expected None hit=None, top none, 3.8 ms
- `OpenProse` / `Weitekamp`: 0 hits. The title is not indexed, and ASR heard 'Whitecamp'.

## Quality
- Language auto-detected en; 701 segments, 7370 words, all segments linked to a frame_id.
- Opening line names the speaker and talk topic (recursive decision models); ending mentions OSO at oso.computer. Topics (System 1/2, Danny Kahneman, Recursive Language Models/RLM, Doom demo, latency in milliseconds) are present and coherent.
- ASR errors: speaker name heard as 'Raymond Whitecamp' (Weitekamp); the product name is transcribed inconsistently as 'Jeff' and 'Jev'; 'OpenProse' never appears in the transcript (0 matches for 'prose'), so a search for OpenProse/Weitekamp will not hit spoken text. Filler words (um, uh) kept. No garbage/hallucination loops observed in the reviewed text.
- Frames: 670 over 52 min (12.934/min). Slide sections are sensible, but demo and webcam sections are over-sampled.
- Offboarding (owner erik): recommendation keep, deletes_performed false = True. Not an exact-copy candidate.
