import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import type { AssetDetail, ExportChunk, ExportSpeaker, FrameView, Segment, SpeakerCategory } from "@contracts/ts/dso-contracts";
import { api } from "../api/client";
import { absUrl } from "../api/config";
import { useAsync } from "../lib/useAsync";
import { formatBytes, formatTime, parseSpeakerLabel, SOURCE_LABEL } from "../lib/format";
import { AssetPicker } from "../components/AssetPicker";
import { MediaImage } from "../components/MediaImage";
import { Snippet } from "../components/Snippet";
import { Badge, Empty, ErrorBox, Loading, PageHeader, StatCard, type Tone } from "../components/ui";
import { Downloads } from "../components/Downloads";
import { ChatPanel } from "../components/ChatPanel";
import { IconMic } from "../components/Icons";

const frameAt = (frames: FrameView[], t: number) =>
  frames.find((f) => f.t_start <= t && t < f.t_end) ?? frames[frames.length - 1] ?? null;

function highlight(text: string, q: string) {
  if (!q.trim()) return text;
  const re = new RegExp(`(${q.trim().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi");
  return text.replace(re, "<mark>$1</mark>");
}

const ROLE_TONE: Record<SpeakerCategory, Tone> = {
  PRESENTER: "blue",
  DOCUMENTARY: "purple",
  UNKNOWN: "grey",
};

const ROLE_LABEL: Record<SpeakerCategory, string> = {
  PRESENTER: "Presenter",
  DOCUMENTARY: "Documentary",
  UNKNOWN: "Unknown / Q&A",
};

interface EnrichedSpeaker {
  key: string;
  label: string;
  category: SpeakerCategory | null;
  count: number;
  seconds: number;
  overlapCount: number;
  summary?: ExportSpeaker;
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
  // Best-effort fetch for rich diarization / speaker role / overlap / confidence metadata
  const exported = useAsync(() => api.exportAsset(id!), [id], !!id && detail.data?.asset.status === "ready");
  const chatMeta = useAsync(() => api.getChat(id!), [id], !!id);

  const [time, setTime] = useState(0);
  const [filter, setFilter] = useState("");
  const [speakerFilter, setSpeakerFilter] = useState<string | null>(null);
  const [roleFilter, setRoleFilter] = useState<SpeakerCategory | "OVERLAP" | "ALL">("ALL");
  const [sideTab, setSideTab] = useState<"transcript" | "speakers" | "chat">(params.get("chat") ? "chat" : "transcript");
  const [showAllSpeakers, setShowAllSpeakers] = useState(false);
  const [stripMode, setStripMode] = useState<"unique" | "ranges">("unique");

  const videoRef = useRef<HTMLVideoElement>(null);
  const segRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  useEffect(() => {
    setSpeakerFilter(null);
    setRoleFilter("ALL");
    setShowAllSpeakers(false);
    if (params.get("chat")) setSideTab("chat");
  }, [id, params]);

  const tl = timeline.data;
  const frames = tl?.frames ?? [];
  const segments = tl?.segments ?? [];
  const duration = tl?.duration_seconds || Math.max(1, ...frames.map((f) => f.t_end), ...segments.map((s) => s.end));
  const current = frameAt(frames, time);
  const activeSeg = segments.find((s) => s.start <= time && time < s.end) ?? null;

  const matchedDocIds = useMemo(
    () => Array.from(new Set(frames.map((f) => f.matched_slide?.split(":")[0]).filter((x): x is string => Boolean(x)))).sort(),
    [frames],
  );
  const matchedDocs = useAsync(
    () => Promise.all(matchedDocIds.map((did) => api.getAsset(did).catch(() => null))),
    [matchedDocIds.join(",")],
    matchedDocIds.length > 0,
  );
  const matchedDocById = useMemo(() => {
    const map = new Map<string, AssetDetail>();
    for (const d of matchedDocs.data ?? []) {
      if (d) map.set(d.asset.id, d);
    }
    return map;
  }, [matchedDocs.data]);

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
    if (videoRef.current) videoRef.current.currentTime = t;
    const s = segId ?? segments.find((x) => x.start <= t && t < x.end)?.id;
    if (s) setTimeout(() => segRefs.current[s]?.scrollIntoView({ block: "nearest", behavior: "smooth" }), 50);
  }

  const chunkBySegId = useMemo(() => {
    const map = new Map<string, ExportChunk>();
    for (const c of exported.data?.chunks ?? []) {
      if (c.kind === "transcript_segment") {
        const sid = c.chunk_id.split(":")[1];
        if (sid) map.set(sid, c);
      }
    }
    return map;
  }, [exported.data]);

  const speakerSummaryById = useMemo(() => {
    const map = new Map<string, ExportSpeaker>();
    for (const sp of exported.data?.speakers ?? []) {
      map.set(sp.speaker_id ?? sp.speaker, sp);
      map.set(sp.speaker, sp);
    }
    return map;
  }, [exported.data]);

  const speakers: EnrichedSpeaker[] = useMemo(() => {
    const map = new Map<string, EnrichedSpeaker>();
    for (const s of segments) {
      if (!s.speaker) continue;
      const chunk = chunkBySegId.get(s.id);
      const parsed = parseSpeakerLabel(s.speaker);
      const summary = (chunk?.speaker_id ? speakerSummaryById.get(chunk.speaker_id) : undefined) ?? speakerSummaryById.get(s.speaker);
      const key = chunk?.speaker_id ?? summary?.speaker_id ?? s.speaker;
      const category = chunk?.speaker_category ?? summary?.role ?? parsed.category;
      const isOverlap = chunk?.overlap ?? parsed.overlap;

      const cur = map.get(key) ?? {
        key,
        label: summary?.speaker ?? (category ? `${key} (${ROLE_LABEL[category]})` : key),
        category,
        count: 0,
        seconds: 0,
        overlapCount: 0,
        summary,
      };
      cur.count += 1;
      cur.seconds += Math.max(0, s.end - s.start);
      if (isOverlap) cur.overlapCount += 1;
      map.set(key, cur);
    }
    return Array.from(map.values()).sort((a, b) => b.seconds - a.seconds);
  }, [segments, chunkBySegId, speakerSummaryById]);

  const roleCounts = useMemo(() => {
    let presenter = 0;
    let doc = 0;
    let unknown = 0;
    let overlapSegs = 0;
    for (const sp of speakers) {
      if (sp.category === "PRESENTER") presenter++;
      else if (sp.category === "DOCUMENTARY") doc++;
      else if (sp.category === "UNKNOWN") unknown++;
    }
    for (const s of segments) {
      const ch = chunkBySegId.get(s.id);
      const parsed = parseSpeakerLabel(s.speaker);
      if (ch?.overlap || parsed.overlap) overlapSegs++;
    }
    return { presenter, doc, unknown, overlapSegs, hasRoles: presenter + doc + unknown > 0 };
  }, [speakers, segments, chunkBySegId]);

  const visibleSpeakers = useMemo(() => {
    const base = speakers.filter((sp) => {
      if (roleFilter === "ALL") return true;
      if (roleFilter === "OVERLAP") return sp.overlapCount > 0 || (sp.summary?.overlap_segment_count ?? 0) > 0;
      return sp.category === roleFilter;
    });
    return showAllSpeakers ? base : base.slice(0, 12);
  }, [speakers, roleFilter, showAllSpeakers]);

  const totalForActiveRole = useMemo(() => {
    return speakers.filter((sp) => {
      if (roleFilter === "ALL") return true;
      if (roleFilter === "OVERLAP") return sp.overlapCount > 0 || (sp.summary?.overlap_segment_count ?? 0) > 0;
      return sp.category === roleFilter;
    }).length;
  }, [speakers, roleFilter]);

  const shown: Segment[] = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return segments.filter((s) => {
      const ch = chunkBySegId.get(s.id);
      const parsed = parseSpeakerLabel(s.speaker);
      const cat = ch?.speaker_category ?? parsed.category;
      const isOv = ch?.overlap ?? parsed.overlap;
      if (roleFilter === "OVERLAP" && !isOv) return false;
      if (roleFilter !== "ALL" && roleFilter !== "OVERLAP" && cat !== roleFilter) return false;
      if (speakerFilter) {
        const spId = ch?.speaker_id ?? parsed.base;
        const matchesSp =
          s.speaker === speakerFilter ||
          spId === speakerFilter ||
          (ch?.overlap_speakers ?? []).includes(speakerFilter);
        if (!matchesSp) return false;
      }
      if (q && !s.text.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [segments, filter, speakerFilter, roleFilter, chunkBySegId]);

  const asset = detail.data?.asset;
  const saidOn = (f: FrameView) => segments.filter((s) => s.frame_id === f.id);
  const hasSlides = frames.some((f) => f.slide != null);
  const uniqueStrip: FrameView[] = useMemo(() => {
    if (!hasSlides) return frames;
    const seen = new Set<number>();
    return frames.filter((f) => f.slide != null && !seen.has(f.slide) && (seen.add(f.slide), true));
  }, [frames, hasSlides]);
  const shownFor = (f: FrameView) => frames.filter((x) => x.slide === f.slide).reduce((s, x) => s + (x.t_end - x.t_start), 0);
  const activeStrip = stripMode === "unique" ? uniqueStrip : frames;
  const uniqueCount = detail.data?.derived?.unique_slide_count ?? null;
  const chatCount = chatMeta.data?.messages.length ?? 0;

  return (
    <section className="page-stack page-recording">
      <PageHeader
        title="Recording studio"
        lead="Follow the conversation. Explore synchronized slides, transcripts, speakers, and the original recording."
        actions={
          assets.data && (
            <AssetPicker assets={assets.data.assets} kind="video" value={id} label="Recording" onChange={(v) => navigate(`/recording/${v}`)} />
          )
        }
      />

      {assets.error ? (
        <ErrorBox error={assets.error} onRetry={assets.reload} />
      ) : !id && assets.data ? (
        <Empty>No recordings yet. Upload an .mp4 in Library &amp; ingest.</Empty>
      ) : timeline.loading || assets.loading ? (
        <Loading label="Loading recording timeline…" />
      ) : timeline.error ? (
        <ErrorBox error={timeline.error} onRetry={timeline.reload} />
      ) : tl && segments.length === 0 && frames.length === 0 ? (
        <Empty>No transcript or key frames for this recording yet (status: {asset?.status ?? "unknown"}).</Empty>
      ) : tl ? (
        <>
          {detail.data && <Downloads detail={detail.data} compact />}

          <div className="stats-grid-4">
            <StatCard label="Original (kept)" value={formatBytes(asset?.bytes)} sub={asset ? `${SOURCE_LABEL[asset.source_system]} · ${asset.owner}` : undefined} />
            <StatCard
              label="Derived (added)"
              value={formatBytes(detail.data?.derived?.derived_bytes)}
              sub={
                uniqueCount !== null
                  ? `${uniqueCount} unique slides (from ${detail.data?.derived?.source_frame_count} frames) · ${segments.length} segs`
                  : `${frames.length} key frames · ${segments.length} segments`
              }
            />
            <StatCard label="Length & language" value={formatTime(duration)} sub={`language: ${tl.language ?? "unknown"} · ${speakers.length} speaker IDs`} tone="accent" />
            <StatCard
              label="ASR / Threshold"
              value={<span className="mono-sm">{detail.data?.pipeline?.model ?? "—"}</span>}
              sub={detail.data?.pipeline ? `frame diff pHash >= ${detail.data.pipeline.frame_threshold}` : undefined}
            />
          </div>

          <div className="studio-layout">
            {/* LEFT STAGE: FRAME + PLAYER + RULER + UNIQUE SLIDES STRIP */}
            <div className="studio-stage card">
              <div className="stage-viewport">
                {current ? (
                  <MediaImage
                    url={current.image_url}
                    kind="frame"
                    title={saidOn(current)[0]?.text ?? `Key frame ${current.id}`}
                    sub={`${current.id} · ${formatTime(current.t_start)}–${formatTime(current.t_end)}`}
                    alt={`Key frame ${current.id}`}
                  />
                ) : (
                  <Empty>No frame at this timestamp.</Empty>
                )}

                <div className="stage-caption">
                  <div className="stage-caption-main">
                    <Badge tone="blue">{formatTime(time)}</Badge>
                    {current?.slide != null && <Badge tone="purple">Slide {current.slide}</Badge>}
                    <code>{current?.id ?? "—"}</code>
                    <span className="muted small">
                      ({formatTime(current?.t_start)}–{formatTime(current?.t_end)}) · {formatBytes(current?.bytes)} WebP
                    </span>
                    {current?.matched_slide && (() => {
                      const [docId, slideId] = current.matched_slide.split(":");
                      const pageNum = slideId?.replace(/^p/i, "") ?? "1";
                      const docDetail = matchedDocById.get(docId);
                      const docName = docDetail?.asset.filename ?? (assets.data?.assets ?? []).find((a) => a.id === docId)?.filename;
                      const docNum = docDetail?.metadata?.doc_number;
                      const rev = docDetail?.metadata?.revision;
                      const metaTag =
                        docNum && rev
                          ? ` · Doc ${docNum} (Rev ${rev})`
                          : docNum
                            ? ` · Doc ${docNum}`
                            : rev
                              ? ` · Rev ${rev}`
                              : "";
                      return (
                        <Link to={`/document/${docId}?page=${pageNum}`} className="badge-link">
                          <Badge tone="green">
                            Matches {docName ?? docId}{metaTag} · Slide {pageNum} ↗
                          </Badge>
                        </Link>
                      );
                    })()}
                  </div>
                  {activeSeg && <div className="stage-subtitle">“{activeSeg.text}”</div>}
                </div>
              </div>

              <div className="scrubber-wrap">
                <div className="ruler" aria-label="Interactive recording timeline">
                  {frames.map((f) => (
                    <button
                      key={f.id}
                      type="button"
                      className={`ruler-frame ${current?.id === f.id ? "on" : ""}`}
                      style={{ left: `${(f.t_start / duration) * 100}%`, width: `${((f.t_end - f.t_start) / duration) * 100}%` }}
                      onClick={() => jump(f.t_start)}
                      title={`${f.id}: ${formatTime(f.t_start)}–${formatTime(f.t_end)}`}
                    />
                  ))}
                  {segments.map((s) => (
                    <span
                      key={s.id}
                      className={`ruler-tick ${activeSeg?.id === s.id ? "on" : ""}`}
                      style={{ left: `${(s.start / duration) * 100}%` }}
                    />
                  ))}
                  <span className="ruler-head" style={{ left: `${(time / duration) * 100}%` }} />
                </div>
                <div className="ruler-labels muted small">
                  <span>0:00</span>
                  <span>Current {formatTime(time)}</span>
                  <span>{formatTime(duration)}</span>
                </div>
              </div>

              <div className="strip-header">
                <h4>
                  {hasSlides
                    ? `Unique slides (${uniqueStrip.length}) across ${frames.length} time ranges`
                    : `Key frames (${frames.length})`}
                </h4>
                {hasSlides && (
                  <div className="segmented small-seg">
                    <button type="button" className={`seg-btn ${stripMode === "unique" ? "on" : ""}`} onClick={() => setStripMode("unique")}>
                      Unique slides ({uniqueStrip.length})
                    </button>
                    <button type="button" className={`seg-btn ${stripMode === "ranges" ? "on" : ""}`} onClick={() => setStripMode("ranges")}>
                      All time ranges ({frames.length})
                    </button>
                  </div>
                )}
              </div>

              <div className="strip">
                {activeStrip.map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    className={`strip-card ${(hasSlides && stripMode === "unique" ? current?.slide === f.slide : current?.id === f.id) ? "on" : ""}`}
                    onClick={() => jump(f.t_start)}
                  >
                    <MediaImage url={f.image_url} kind="frame" title={saidOn(f)[0]?.text ?? f.id} sub={f.id} alt={`Frame ${f.id}`} />
                    <span className="strip-label">
                      {hasSlides ? (
                        <>
                          <b>Slide {f.slide}</b> · {formatTime(f.t_start)}
                          {f.matched_slide && ` · p.${f.matched_slide.split(":")[1]?.replace(/^p/i, "") ?? "1"}`}
                          <br />
                          <span className="muted">on screen {formatTime(shownFor(f))}</span>
                        </>
                      ) : (
                        <>
                          <b>{f.id}</b> · {formatTime(f.t_start)}
                          <br />
                          <span className="muted">{formatBytes(f.bytes)}</span>
                        </>
                      )}
                    </span>
                  </button>
                ))}
              </div>

              <details className="video-expander">
                <summary>Stream original video (kept on disk, range-seekable)</summary>
                <video ref={videoRef} controls preload="metadata" src={absUrl(tl.original_url)} onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)} />
              </details>
            </div>

            {/* RIGHT INTELLIGENCE PANEL: TRANSCRIPT / SPEAKERS / CHAT */}
            <div className="studio-side card">
              <div className="side-tabs" role="tablist">
                <button type="button" role="tab" aria-selected={sideTab === "transcript"} className={`side-tab ${sideTab === "transcript" ? "on" : ""}`} onClick={() => setSideTab("transcript")}>
                  Transcript ({segments.length})
                </button>
                <button type="button" role="tab" aria-selected={sideTab === "speakers"} className={`side-tab ${sideTab === "speakers" ? "on" : ""}`} onClick={() => setSideTab("speakers")}>
                  Speakers ({speakers.length})
                </button>
                <button type="button" role="tab" aria-selected={sideTab === "chat"} className={`side-tab ${sideTab === "chat" ? "on" : ""}`} onClick={() => setSideTab("chat")}>
                  Meeting chat ({chatCount})
                </button>
              </div>

              {sideTab === "transcript" ? (
                <>
                  {speakers.length > 0 && (
                    <div className="speaker-filter-box">
                      {roleCounts.hasRoles && (
                        <div className="role-pills">
                          <button type="button" className={`chip ${roleFilter === "ALL" ? "on" : ""}`} onClick={() => { setRoleFilter("ALL"); setSpeakerFilter(null); }}>
                            All roles ({speakers.length})
                          </button>
                          {roleCounts.presenter > 0 && (
                            <button type="button" className={`chip chip-blue ${roleFilter === "PRESENTER" ? "on" : ""}`} onClick={() => { setRoleFilter("PRESENTER"); setSpeakerFilter(null); }}>
                              Presenters ({roleCounts.presenter})
                            </button>
                          )}
                          {roleCounts.doc > 0 && (
                            <button type="button" className={`chip chip-purple ${roleFilter === "DOCUMENTARY" ? "on" : ""}`} onClick={() => { setRoleFilter("DOCUMENTARY"); setSpeakerFilter(null); }}>
                              Documentary ({roleCounts.doc})
                            </button>
                          )}
                          {roleCounts.unknown > 0 && (
                            <button type="button" className={`chip ${roleFilter === "UNKNOWN" ? "on" : ""}`} onClick={() => { setRoleFilter("UNKNOWN"); setSpeakerFilter(null); }}>
                              Other / Q&amp;A ({roleCounts.unknown})
                            </button>
                          )}
                          {roleCounts.overlapSegs > 0 && (
                            <button type="button" className={`chip chip-amber ${roleFilter === "OVERLAP" ? "on" : ""}`} onClick={() => { setRoleFilter("OVERLAP"); setSpeakerFilter(null); }}>
                              Overlaps ({roleCounts.overlapSegs})
                            </button>
                          )}
                        </div>
                      )}

                      <div className="speaker-chips">
                        <button type="button" className={`chip ${speakerFilter === null ? "on" : ""}`} onClick={() => setSpeakerFilter(null)}>
                          Any speaker
                        </button>
                        {visibleSpeakers.map((sp) => (
                          <button
                            key={sp.key}
                            type="button"
                            className={`chip ${speakerFilter === sp.key ? "on" : ""}`}
                            title={`${sp.label}: ${sp.count} segments · ${formatTime(sp.seconds)}`}
                            onClick={() => setSpeakerFilter(speakerFilter === sp.key ? null : sp.key)}
                          >
                            {sp.key}
                            {sp.category && <span className="chip-sub">· {sp.category.slice(0, 4)}</span>} ({sp.count})
                          </button>
                        ))}
                        {totalForActiveRole > 12 && (
                          <button type="button" className="chip chip-ghost" onClick={() => setShowAllSpeakers((v) => !v)}>
                            {showAllSpeakers ? "Collapse" : `+${totalForActiveRole - 12} more`}
                          </button>
                        )}
                      </div>
                    </div>
                  )}

                  <input
                    className="input-search-side"
                    type="search"
                    placeholder="Filter spoken sentences…"
                    value={filter}
                    onChange={(e) => setFilter(e.target.value)}
                    aria-label="Filter transcript"
                  />

                  {shown.length === 0 ? (
                    <Empty>No transcript sentences match the current filter.</Empty>
                  ) : (
                    <ol className="transcript-feed">
                      {shown.map((s) => {
                        const ch = chunkBySegId.get(s.id);
                        const parsed = parseSpeakerLabel(s.speaker);
                        const cat = ch?.speaker_category ?? parsed.category;
                        const isOv = ch?.overlap ?? parsed.overlap;
                        const conf = ch?.speaker_confidence ?? null;
                        return (
                          <li key={s.id}>
                            <button
                              ref={(el) => (segRefs.current[s.id] = el)}
                              type="button"
                              className={`seg-row ${activeSeg?.id === s.id ? "on" : ""}`}
                              onClick={() => jump(s.start, s.id)}
                            >
                              <span className="seg-ts">{formatTime(s.start)}</span>
                              <span className="seg-body">
                                <span className="seg-badges">
                                  {s.speaker && (
                                    <Badge tone={cat ? ROLE_TONE[cat] : "grey"}>{ch?.speaker_id ?? parsed.base}</Badge>
                                  )}
                                  {cat && <Badge tone={ROLE_TONE[cat]}>{ROLE_LABEL[cat]}</Badge>}
                                  {isOv && <Badge tone="amber">Overlap</Badge>}
                                  {conf !== null && <span className="muted small">{Math.round(conf * 100)}%</span>}
                                </span>
                                <span className="seg-copy">
                                  <Snippet html={highlight(s.text, filter)} />
                                </span>
                              </span>
                              <span className="seg-frame-id">{s.frame_id ?? "—"}</span>
                            </button>
                          </li>
                        );
                      })}
                    </ol>
                  )}
                </>
              ) : sideTab === "speakers" ? (
                speakers.length === 0 ? (
                  <Empty>
                    <IconMic /> No speaker tags on this recording yet. Run speaker diarization or inspect a processed recording.
                  </Empty>
                ) : (
                  <div className="speakers-table-wrap">
                    <table className="data-table compact">
                      <thead>
                        <tr>
                          <th>Speaker</th>
                          <th>Role</th>
                          <th className="num">Segs</th>
                          <th className="num">Spoken</th>
                          <th className="num">Overlaps</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {speakers.map((sp) => (
                          <tr key={sp.key}>
                            <td>
                              <strong>{sp.key}</strong>
                              {sp.summary?.video_churn_ratio != null && (
                                <div className="muted small">video churn {Math.round(sp.summary.video_churn_ratio * 100)}%</div>
                              )}
                            </td>
                            <td>
                              {sp.category ? <Badge tone={ROLE_TONE[sp.category]}>{ROLE_LABEL[sp.category]}</Badge> : <Badge>Acoustic cluster</Badge>}
                            </td>
                            <td className="num">{sp.count}</td>
                            <td className="num">{formatTime(sp.seconds)}</td>
                            <td className="num">{sp.summary?.overlap_segment_count ?? sp.overlapCount}</td>
                            <td>
                              <button
                                type="button"
                                className="btn btn-ghost btn-xs"
                                onClick={() => {
                                  setRoleFilter("ALL");
                                  setSpeakerFilter(sp.key);
                                  setSideTab("transcript");
                                }}
                              >
                                Filter
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )
              ) : (
                id && <ChatPanel assetId={id} focusId={params.get("chat")} onJump={(t) => jump(t)} embedded />
              )}
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}
