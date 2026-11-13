import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import type { FrameView, Segment } from "@contracts/ts/dso-contracts";
import { api } from "../api/client";
import { USE_MOCKS, absUrl } from "../api/config";
import { useAsync } from "../lib/useAsync";
import { formatBytes, formatTime, SOURCE_LABEL } from "../lib/format";
import { AssetPicker } from "../components/AssetPicker";
import { MediaImage } from "../components/MediaImage";
import { Snippet } from "../components/Snippet";
import { Badge, Callout, Empty, ErrorBox, Loading, PageHeader, Stat } from "../components/ui";
import { Downloads } from "../components/Downloads";

const frameAt = (frames: FrameView[], t: number) =>
  frames.find((f) => f.t_start <= t && t < f.t_end) ?? frames[frames.length - 1] ?? null;

function highlight(text: string, q: string) {
  if (!q.trim()) return text;
  const re = new RegExp(`(${q.trim().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi");
  return text.replace(re, "<mark>$1</mark>");
}

export default function Recording() {
  const { assetId } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const assets = useAsync(() => api.listAssets(), []);
  const videos = (assets.data?.assets ?? []).filter((a) => a.kind === "video");
  const id = assetId ?? videos.find((a) => a.status === "ready")?.id ?? videos[0]?.id;

  const timeline = useAsync(() => api.getTimeline(id!), [id], !!id);
  const detail = useAsync(() => api.getAsset(id!), [id], !!id);

  const [time, setTime] = useState(0);
  const [filter, setFilter] = useState("");
  const videoRef = useRef<HTMLVideoElement>(null);
  const segRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const tl = timeline.data;
  const frames = tl?.frames ?? [];
  const segments = tl?.segments ?? [];
  const duration = tl?.duration_seconds || Math.max(1, ...frames.map((f) => f.t_end), ...segments.map((s) => s.end));
  const current = frameAt(frames, time);
  const activeSeg = segments.find((s) => s.start <= time && time < s.end) ?? null;

  // Deep link from Search: ?t=96.2 or ?seg=s2
  useEffect(() => {
    if (!tl) return;
    const seg = params.get("seg");
    const t = params.get("t");
    const target = seg ? tl.segments.find((s) => s.id === seg)?.start : t ? Number(t) : undefined;
    if (target !== undefined && !Number.isNaN(target)) jump(target, seg ?? undefined);
    else setTime(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tl]);

  function jump(t: number, segId?: string) {
    setTime(t);
    if (videoRef.current) {
      videoRef.current.currentTime = t;
    }
    const s = segId ?? segments.find((x) => x.start <= t && t < x.end)?.id;
    if (s) setTimeout(() => segRefs.current[s]?.scrollIntoView({ block: "nearest", behavior: "smooth" }), 50);
  }

  const shown: Segment[] = useMemo(
    () => (filter.trim() ? segments.filter((s) => s.text.toLowerCase().includes(filter.trim().toLowerCase())) : segments),
    [segments, filter],
  );

  const asset = detail.data?.asset;
  const saidOn = (f: FrameView) => segments.filter((s) => s.frame_id === f.id);
  // After the unique-slide pass several time ranges share one picture: show each slide once in the strip.
  const hasSlides = frames.some((f) => f.slide != null);
  const strip: FrameView[] = useMemo(() => {
    if (!hasSlides) return frames;
    const seen = new Set<number>();
    return frames.filter((f) => f.slide != null && !seen.has(f.slide) && (seen.add(f.slide), true));
  }, [frames, hasSlides]);
  const shownFor = (f: FrameView) => frames.filter((x) => x.slide === f.slide).reduce((s, x) => s + (x.t_end - x.t_start), 0);
  const uniqueCount = detail.data?.derived?.unique_slide_count ?? null;

  return (
    <section>
      <PageHeader
        title="Recording timeline"
        lead="Timed transcript and compressed key frames, linked by time. Click a sentence to jump to the frame that was on screen."
      >
        {assets.data && (
          <AssetPicker assets={assets.data.assets} kind="video" value={id} label="Recording" onChange={(v) => navigate(`/recording/${v}`)} />
        )}
      </PageHeader>

      {assets.error ? (
        <ErrorBox error={assets.error} onRetry={assets.reload} />
      ) : !id && assets.data ? (
        <Empty>No recordings yet. Upload an .mp4 in Library & ingest.</Empty>
      ) : timeline.loading || assets.loading ? (
        <Loading label="Loading timeline…" />
      ) : timeline.error ? (
        <ErrorBox error={timeline.error} onRetry={timeline.reload} />
      ) : tl && segments.length === 0 && frames.length === 0 ? (
        <Empty>
          No transcript or key frames for this file yet. Process it first (status: {asset?.status ?? "unknown"}).
          {USE_MOCKS && " In mock mode only the fixture recording has data."}
        </Empty>
      ) : tl ? (
        <>
          {detail.data && <Downloads detail={detail.data} compact />}
          <div className="stats-row">
            <Stat label="Original (kept)" value={formatBytes(asset?.bytes)} sub={asset ? `${SOURCE_LABEL[asset.source_system]} · ${asset.owner}` : undefined} />
            <Stat
              label="Derived (added)"
              value={formatBytes(detail.data?.derived?.derived_bytes)}
              sub={
                uniqueCount !== null
                  ? `${uniqueCount} unique slides (from ${detail.data?.derived?.source_frame_count} key frames) · ${segments.length} segments`
                  : `${frames.length} key frames · ${segments.length} segments`
              }
            />
            <Stat label="Length" value={formatTime(duration)} sub={`language: ${tl.language ?? "unknown"}`} />
            <Stat label="Model" value={<span className="small-val">{detail.data?.pipeline?.model ?? "—"}</span>} sub={detail.data?.pipeline ? `frame threshold: pHash ≥ ${detail.data.pipeline.frame_threshold}` : undefined} />
          </div>

          <div className="rec-layout">
            <div className="card rec-main">
              <div className="frame-view">
                {current ? (
                  <MediaImage
                    url={current.image_url}
                    kind="frame"
                    title={saidOn(current)[0]?.text ?? `Key frame ${current.id}`}
                    sub={`${current.id} · ${formatTime(current.t_start)}–${formatTime(current.t_end)}`}
                    alt={`Key frame ${current.id} shown from ${formatTime(current.t_start)} to ${formatTime(current.t_end)}`}
                  />
                ) : (
                  <Empty>No key frame for this time.</Empty>
                )}
                <div className="frame-caption">
                  <span>
                    <b>{formatTime(time)}</b> · {current?.slide != null && <>slide <b>{current.slide}</b> · </>}frame <code>{current?.id ?? "—"}</code> ({formatTime(current?.t_start)}–{formatTime(current?.t_end)}) ·{" "}
                    {formatBytes(current?.bytes)} WebP
                  </span>
                  {activeSeg && <span className="muted">“{activeSeg.text}”</span>}
                </div>
              </div>

              {/* Time ruler: frame blocks proportional to their time range, segment ticks on top */}
              <div className="ruler" aria-label="Timeline">
                {frames.map((f) => (
                  <button
                    key={f.id}
                    className={`ruler-frame ${current?.id === f.id ? "on" : ""}`}
                    style={{ left: `${(f.t_start / duration) * 100}%`, width: `${((f.t_end - f.t_start) / duration) * 100}%` }}
                    onClick={() => jump(f.t_start)}
                    title={`${f.id}: ${formatTime(f.t_start)}–${formatTime(f.t_end)}`}
                  >
                    {f.id}
                  </button>
                ))}
                {segments.map((s) => (
                  <span key={s.id} className={`ruler-tick ${activeSeg?.id === s.id ? "on" : ""}`} style={{ left: `${(s.start / duration) * 100}%` }} />
                ))}
                <span className="ruler-head" style={{ left: `${(time / duration) * 100}%` }} />
              </div>
              <div className="ruler-labels muted small">
                <span>0:00</span>
                <span>{formatTime(duration)}</span>
              </div>

              <h4>
                {hasSlides ? `Unique slides (${strip.length}) · shown in ${frames.length} time ranges` : `Key frames (${frames.length})`}
              </h4>
              <div className="strip">
                {strip.map((f) => (
                  <button
                    key={f.id}
                    className={`strip-item ${(hasSlides ? current?.slide === f.slide : current?.id === f.id) ? "on" : ""}`}
                    onClick={() => jump(f.t_start)}
                  >
                    <MediaImage url={f.image_url} kind="frame" title={saidOn(f)[0]?.text ?? f.id} sub={f.id} alt={hasSlides ? `Slide ${f.slide}` : `Key frame ${f.id}`} />
                    <span>
                      {hasSlides ? (
                        <>
                          slide {f.slide} · first {formatTime(f.t_start)} · on screen {formatTime(shownFor(f))} · {formatBytes(f.bytes)}
                        </>
                      ) : (
                        <>
                          {f.id} · {formatTime(f.t_start)} · {formatBytes(f.bytes)}
                        </>
                      )}
                    </span>
                  </button>
                ))}
              </div>

              {USE_MOCKS ? (
                <Callout tone="info">Mock mode: frames are drawn placeholders. With the backend, real WebP key frames and the original video load here.</Callout>
              ) : (
                <details className="video-details">
                  <summary>Play the original video (kept, never deleted)</summary>
                  <video ref={videoRef} controls preload="metadata" src={absUrl(tl.original_url)} onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)} />
                </details>
              )}
            </div>

            <div className="card rec-side">
              <div className="card-head">
                <h3>Transcript</h3>
                <Badge tone="grey" title="Speaker ID is out of scope">no speaker ID</Badge>
              </div>
              <input
                className="search-input small"
                placeholder="Find a phrase in this transcript…"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                aria-label="Filter transcript"
              />
              {shown.length === 0 ? (
                <Empty>No sentence contains “{filter}”.</Empty>
              ) : (
                <ol className="transcript">
                  {shown.map((s) => (
                    <li key={s.id}>
                      <button
                        ref={(el) => (segRefs.current[s.id] = el)}
                        className={`seg ${activeSeg?.id === s.id ? "on" : ""}`}
                        onClick={() => jump(s.start, s.id)}
                      >
                        <span className="seg-time">{formatTime(s.start)}</span>
                        <span className="seg-text">
                          <Snippet html={highlight(s.text, filter)} />
                        </span>
                        <span className="seg-frame">→ {s.frame_id ?? "no frame"}</span>
                      </button>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}
