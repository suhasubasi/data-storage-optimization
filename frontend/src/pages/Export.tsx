import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { ExportChunk, SpeakerCategory } from "@contracts/ts/dso-contracts";
import { api } from "../api/client";
import { absUrl } from "../api/config";
import { useAsync } from "../lib/useAsync";
import { downloadText, formatTime } from "../lib/format";
import { AssetPicker } from "../components/AssetPicker";
import { Downloads } from "../components/Downloads";
import { Badge, Callout, Empty, ErrorBox, Loading, PageHeader, SIMULATED_SOURCE_HINT, SourceBadge, StatCard, type Tone } from "../components/ui";
import { IconDownload } from "../components/Icons";

function parseJsonl(text: string): { chunks: ExportChunk[]; bad: number } {
  const chunks: ExportChunk[] = [];
  let bad = 0;
  for (const line of text.split("\n")) {
    if (!line.trim()) continue;
    try {
      chunks.push(JSON.parse(line) as ExportChunk);
    } catch {
      bad++;
    }
  }
  return { chunks, bad };
}

function sourceLink(c: ExportChunk) {
  if (c.kind === "transcript_segment") return `/recording/${c.source.asset_id}?seg=${c.chunk_id.split(":")[1]}`;
  return `/document/${c.source.asset_id}?page=${c.page}`;
}

const ROLE_TONE: Record<SpeakerCategory, Tone> = {
  PRESENTER: "blue",
  DOCUMENTARY: "purple",
  UNKNOWN: "grey",
};

export default function Export() {
  const [tab, setTab] = useState<"jsonl" | "asset" | "files">("jsonl");
  const [kindFilter, setKindFilter] = useState<"all" | "transcript_segment" | "slide_text">("all");
  const [catFilter, setCatFilter] = useState<"ALL" | SpeakerCategory | "OVERLAP">("ALL");
  const [q, setQ] = useState("");
  const [pageLimit, setPageLimit] = useState(100);
  const [inspectChunk, setInspectChunk] = useState<ExportChunk | null>(null);

  const assets = useAsync(() => api.listAssets(), []);
  const ready = (assets.data?.assets ?? []).filter((a) => a.status === "ready");
  const [assetId, setAssetId] = useState<string | undefined>();
  const id = assetId ?? ready.find((a) => a.kind === "video")?.id ?? ready[0]?.id;

  const jsonl = useAsync(() => api.exportJsonl(), [], tab === "jsonl");
  const one = useAsync(() => api.exportAsset(id!), [id], tab === "asset" && !!id);
  const detail = useAsync(() => api.getAsset(id!), [id], tab === "files" && !!id);
  const parsed = useMemo(() => parseJsonl(jsonl.data ?? ""), [jsonl.data]);

  const filteredChunks = useMemo(() => {
    const query = q.trim().toLowerCase();
    return parsed.chunks.filter((c) => {
      if (kindFilter !== "all" && c.kind !== kindFilter) return false;
      if (catFilter === "OVERLAP" && !c.overlap) return false;
      if (catFilter !== "ALL" && catFilter !== "OVERLAP" && c.speaker_category !== catFilter) return false;
      if (query) {
        const hit =
          c.text.toLowerCase().includes(query) ||
          c.chunk_id.toLowerCase().includes(query) ||
          (c.speaker ?? "").toLowerCase().includes(query) ||
          c.source.filename.toLowerCase().includes(query);
        if (!hit) return false;
      }
      return true;
    });
  }, [parsed.chunks, kindFilter, catFilter, q]);

  const hasRichSpeakers = useMemo(() => parsed.chunks.some((c) => c.speaker_category != null), [parsed.chunks]);

  return (
    <section className="page-stack page-export">
      <PageHeader
        title="AI-ready data & file exports"
        lead="Put your knowledge to work. Explore structured data and download transcripts, slides, or AI-ready exports."
      />

      <div className="pill-tabs" role="tablist">
        <button type="button" role="tab" aria-selected={tab === "jsonl"} className={`pill-tab ${tab === "jsonl" ? "on" : ""}`} onClick={() => setTab("jsonl")}>
          JSONL corpus ({parsed.chunks.length})
        </button>
        <button type="button" role="tab" aria-selected={tab === "asset"} className={`pill-tab ${tab === "asset" ? "on" : ""}`} onClick={() => setTab("asset")}>
          Single-asset JSON
        </button>
        <button type="button" role="tab" aria-selected={tab === "files"} className={`pill-tab ${tab === "files" ? "on" : ""}`} onClick={() => setTab("files")}>
          Transcripts &amp; slide decks (.txt / .pptx / .pdf)
        </button>
      </div>

      <Callout tone="info" title="Provenance guarantee:">
        {SIMULATED_SOURCE_HINT} Every chunk links back to its original read-only asset and keeps unmeasured confidence as <code>null</code>.
      </Callout>

      {tab === "jsonl" ? (
        jsonl.loading ? (
          <Loading label="Streaming JSONL export from backend…" />
        ) : jsonl.error ? (
          <ErrorBox error={jsonl.error} onRetry={jsonl.reload} />
        ) : parsed.chunks.length === 0 ? (
          <Empty>No processed chunks available yet. Process a recording or document first.</Empty>
        ) : (
          <div className="card">
            <div className="card-head">
              <div>
                <h3>{parsed.chunks.length} total chunks (<code>GET /api/export.jsonl</code>)</h3>
                {parsed.bad > 0 && <span className="err-inline small">{parsed.bad} unparseable lines</span>}
              </div>
              <button type="button" className="btn btn-primary btn-sm" onClick={() => downloadText("dso-export.jsonl", jsonl.data!, "application/x-ndjson")}>
                <IconDownload /> Download dso-export.jsonl
              </button>
            </div>

            <div className="table-toolbar">
              <div className="pill-tabs">
                <button type="button" className={`pill-tab ${kindFilter === "all" ? "on" : ""}`} onClick={() => setKindFilter("all")}>All</button>
                <button type="button" className={`pill-tab ${kindFilter === "transcript_segment" ? "on" : ""}`} onClick={() => setKindFilter("transcript_segment")}>Transcripts</button>
                <button type="button" className={`pill-tab ${kindFilter === "slide_text" ? "on" : ""}`} onClick={() => setKindFilter("slide_text")}>Slide text</button>
                {hasRichSpeakers && (
                  <>
                    <button type="button" className={`pill-tab ${catFilter === "PRESENTER" ? "on" : ""}`} onClick={() => setCatFilter(catFilter === "PRESENTER" ? "ALL" : "PRESENTER")}>Presenter</button>
                    <button type="button" className={`pill-tab ${catFilter === "DOCUMENTARY" ? "on" : ""}`} onClick={() => setCatFilter(catFilter === "DOCUMENTARY" ? "ALL" : "DOCUMENTARY")}>Documentary</button>
                    <button type="button" className={`pill-tab ${catFilter === "OVERLAP" ? "on" : ""}`} onClick={() => setCatFilter(catFilter === "OVERLAP" ? "ALL" : "OVERLAP")}>Overlaps</button>
                  </>
                )}
              </div>
              <input type="search" className="input-compact" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search chunks or speakers…" aria-label="Filter export chunks" />
            </div>

            <div className="table-wrap">
              <table className="data-table compact">
                <thead>
                  <tr>
                    <th>chunk_id</th>
                    <th>Kind &amp; speaker metadata</th>
                    <th>Text</th>
                    <th>Location</th>
                    <th>Source</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {filteredChunks.slice(0, pageLimit).map((c) => (
                    <tr key={c.chunk_id}>
                      <td><code>{c.chunk_id}</code></td>
                      <td>
                        <div className="seg-badges">
                          <Badge tone={c.kind === "transcript_segment" ? "blue" : "purple"}>{c.kind}</Badge>
                          {c.speaker && <Badge tone={c.speaker_category ? ROLE_TONE[c.speaker_category] : "grey"}>{c.speaker_id ?? c.speaker}</Badge>}
                          {c.speaker_category && <Badge tone={ROLE_TONE[c.speaker_category]}>{c.speaker_category}</Badge>}
                          {c.overlap && <Badge tone="amber">OVERLAP</Badge>}
                          {c.speaker_confidence != null && <span className="muted small">{Math.round(c.speaker_confidence * 100)}%</span>}
                        </div>
                      </td>
                      <td className="export-text">{c.text}</td>
                      <td>
                        <Link to={sourceLink(c)}>
                          {c.kind === "transcript_segment" ? `${formatTime(c.start)}–${formatTime(c.end)}` : `page ${c.page}`}
                        </Link>
                      </td>
                      <td>
                        <a href={absUrl(c.source.original_url)} target="_blank" rel="noreferrer">{c.source.filename}</a>
                        <div><SourceBadge source={c.source.source_system} /></div>
                      </td>
                      <td>
                        <button type="button" className="btn btn-ghost btn-xs" onClick={() => setInspectChunk(inspectChunk?.chunk_id === c.chunk_id ? null : c)}>
                          JSON
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {filteredChunks.length > pageLimit && (
              <div className="row-actions" style={{ marginTop: 12 }}>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => setPageLimit((n) => n + 200)}>
                  Show 200 more ({filteredChunks.length - pageLimit} remaining)
                </button>
              </div>
            )}

            {inspectChunk && (
              <div className="json-drawer">
                <div className="card-head">
                  <strong>Chunk payload: <code>{inspectChunk.chunk_id}</code></strong>
                  <button type="button" className="btn btn-ghost btn-xs" onClick={() => setInspectChunk(null)}>Close</button>
                </div>
                <pre className="code-block">{JSON.stringify(inspectChunk, null, 2)}</pre>
              </div>
            )}
          </div>
        )
      ) : tab === "files" ? (
        <div className="card">
          {assets.data && <AssetPicker assets={ready} kind="any" value={id} label="Processed asset" onChange={setAssetId} />}
          {assets.error ? (
            <ErrorBox error={assets.error} onRetry={assets.reload} />
          ) : !id ? (
            <Empty>No ready assets yet.</Empty>
          ) : detail.loading ? (
            <Loading />
          ) : detail.error ? (
            <ErrorBox error={detail.error} onRetry={detail.reload} />
          ) : detail.data ? (
            <div className="page-stack" style={{ marginTop: 16 }}>
              <h3>{detail.data.asset.filename}</h3>
              <Downloads detail={detail.data} />
              <p className="muted small">
                Exports are generated dynamically on request from indexed text and deduplicated WebP images—zero redundant office files stored on disk.
              </p>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="page-stack">
          <div className="card">
            {assets.data && <AssetPicker assets={ready} kind="any" value={id} label="Processed asset" onChange={setAssetId} />}
          </div>
          {one.loading ? (
            <Loading label="Building structured ExportAsset JSON…" />
          ) : one.error ? (
            <ErrorBox error={one.error} onRetry={one.reload} />
          ) : one.data ? (
            <>
              <div className="stats-grid-4">
                <StatCard label="Chunks" value={one.data.chunks.length} />
                <StatCard label="Frames" value={one.data.frames.length} />
                <StatCard label="Slides" value={one.data.slides.length} />
                <StatCard label="Speakers" value={one.data.speakers?.length ?? "legacy"} sub={one.data.speakers ? "Role-classified summary attached" : "Re-run speakers to populate"} />
              </div>

              {one.data.speakers && one.data.speakers.length > 0 && (
                <div className="card">
                  <h3>Structured Speakers Summary (<code>ExportAsset.speakers[]</code>)</h3>
                  <div className="table-wrap">
                    <table className="data-table compact">
                      <thead>
                        <tr>
                          <th>Speaker</th>
                          <th>Role</th>
                          <th className="num">Segments</th>
                          <th className="num">Spoken</th>
                          <th className="num">Video churn</th>
                          <th className="num">Overlap s</th>
                        </tr>
                      </thead>
                      <tbody>
                        {one.data.speakers.map((sp) => (
                          <tr key={sp.speaker}>
                            <td><code>{sp.speaker_id ?? sp.speaker}</code></td>
                            <td>{sp.role ? <Badge tone={ROLE_TONE[sp.role]}>{sp.role}</Badge> : "—"}</td>
                            <td className="num">{sp.segment_count}</td>
                            <td className="num">{formatTime(sp.seconds_spoken)}</td>
                            <td className="num">{sp.video_churn_ratio != null ? `${Math.round(sp.video_churn_ratio * 100)}%` : "—"}</td>
                            <td className="num">{sp.overlap_seconds != null ? `${sp.overlap_seconds.toFixed(1)} s` : "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              <div className="card">
                <div className="card-head">
                  <h3>Full <code>GET /api/assets/{one.data.source.asset_id}/export</code> JSON</h3>
                  <button type="button" className="btn btn-primary btn-sm" onClick={() => downloadText(`${one.data!.source.asset_id}.export.json`, JSON.stringify(one.data, null, 2))}>
                    <IconDownload /> Download JSON
                  </button>
                </div>
                <pre className="code-block tall">{JSON.stringify(one.data, null, 2)}</pre>
              </div>
            </>
          ) : null}
        </div>
      )}
    </section>
  );
}
