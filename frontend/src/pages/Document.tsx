import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import type { AssetMetadata, SlideMatch, SlideView } from "@contracts/ts/dso-contracts";
import { api } from "../api/client";
import { useAsync } from "../lib/useAsync";
import { formatBytes, shortHash, SOURCE_LABEL } from "../lib/format";
import { AssetPicker } from "../components/AssetPicker";
import { Downloads } from "../components/Downloads";
import { MediaImage } from "../components/MediaImage";
import { Badge, Callout, Empty, ErrorBox, Loading, PageHeader, SourceBadge, StatCard } from "../components/ui";

const META_FIELDS: [keyof AssetMetadata, string][] = [
  ["title", "Title"],
  ["author", "Author"],
  ["doc_number", "Document number"],
  ["revision", "Revision"],
  ["date", "Date"],
];

function MatchBadge({ m }: { m: SlideMatch }) {
  const shared = m.type === "shared";
  return (
    <Link to={`/document/${m.other_asset_id}?page=${m.other_page}`} className="badge-link">
      <Badge tone={shared ? "purple" : "amber"} title={`method: ${m.method} · score ${m.score}`}>
        {shared ? "Also in" : "Similar to"} {m.other_filename} p.{m.other_page} ({SOURCE_LABEL[m.other_source_system]})
        {!shared && " · review"}
      </Badge>
    </Link>
  );
}

export default function DocumentView() {
  const { assetId } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();

  const assets = useAsync(() => api.listAssets(), []);
  const docs = (assets.data?.assets ?? []).filter((a) => a.kind === "document");
  const id = assetId ?? docs.find((a) => a.status === "ready")?.id ?? docs[0]?.id;

  const slides = useAsync(() => api.getSlides(id!), [id], !!id);
  const detail = useAsync(() => api.getAsset(id!), [id], !!id);
  const dups = useAsync(() => api.getDuplicates("exact_file"), []);

  const list = slides.data?.slides ?? [];
  const requestedPage = Number(params.get("page") ?? 0);
  const [selectedPage, setSelectedPage] = useState<number>(1);
  const [viewMode, setViewMode] = useState<"inspector" | "grid">("inspector");

  useEffect(() => {
    if (requestedPage > 0) setSelectedPage(requestedPage);
    else if (list.length > 0) setSelectedPage(list[0].page);
  }, [requestedPage, id, list.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const activeSlide: SlideView | null = list.find((s) => s.page === selectedPage) ?? list[0] ?? null;
  const asset = detail.data?.asset;
  const exactGroup = dups.data?.groups.find((g) => g.members.some((m) => m.asset_id === id));
  const copies = exactGroup?.members.filter((m) => m.asset_id !== id) ?? [];
  const meta = slides.data?.metadata ?? detail.data?.metadata ?? null;
  const sharedCount = list.filter((s) => s.matches.some((m) => m.type === "shared")).length;
  const similarCount = list.filter((s) => s.matches.some((m) => m.type === "similar")).length;
  const isDeck = /\.pptx$/i.test(asset?.filename ?? "");
  const unit = isDeck ? "Slide" : "Page";
  const warnings = detail.data?.pipeline?.warnings ?? [];

  function selectPage(page: number) {
    setSelectedPage(page);
    setParams({ page: String(page) }, { replace: true });
  }

  return (
    <section className="page-stack page-document">
      <PageHeader
        title="Document & slide inspector"
        lead="A clearer view of every page. Read extracted text and discover where content is shared across files."
        actions={
          assets.data && (
            <AssetPicker assets={assets.data.assets} kind="document" value={id} label="Document" onChange={(v) => navigate(`/document/${v}`)} />
          )
        }
      />

      {assets.error ? (
        <ErrorBox error={assets.error} onRetry={assets.reload} />
      ) : !id && assets.data ? (
        <Empty>No documents yet. Upload a .pdf or .pptx in Library &amp; ingest.</Empty>
      ) : slides.loading || assets.loading ? (
        <Loading label="Loading pages…" />
      ) : slides.error ? (
        <ErrorBox error={slides.error} onRetry={slides.reload} />
      ) : (
        <>
          {detail.data && <Downloads detail={detail.data} compact />}

          {copies.length > 0 && (
            <Callout tone="warn" title="Exact file copy detected elsewhere.">
              Identical SHA-256 bytes also appear in{" "}
              {copies.map((c, i) => (
                <span key={c.asset_id}>
                  {i > 0 && ", "}
                  <Link to={`/document/${c.asset_id}`}>{c.filename}</Link> ({SOURCE_LABEL[c.source_system]}, owner {c.owner})
                </span>
              ))}
              . See <Link to="/duplicates">Duplicates</Link>.
            </Callout>
          )}

          {warnings.length > 0 && <Callout tone="info">Processing notes: {warnings.join(" · ")}</Callout>}

          <div className="stats-grid-4">
            <StatCard label="Original (kept)" value={formatBytes(asset?.bytes)} sub={asset && <SourceBadge source={asset.source_system} />} />
            <StatCard label="Derived (added)" value={formatBytes(detail.data?.derived?.derived_bytes)} sub={`${list.length} ${unit.toLowerCase()}s indexed`} />
            <StatCard label={`Shared ${unit.toLowerCase()}s`} value={sharedCount} sub="Identical text hash + close pHash" tone="accent" />
            <StatCard label={`Similar ${unit.toLowerCase()}s`} value={similarCount} sub="Needs human review" />
          </div>

          <details className="card">
            <summary className="summary-strong">Embedded file metadata &amp; SHA-256 fingerprint</summary>
            <dl className="meta-grid">
              {META_FIELDS.map(([k, label]) => (
                <div key={k}>
                  <dt>{label}</dt>
                  <dd>{meta?.[k] ? String(meta[k]) : <span className="muted">not found in file</span>}</dd>
                </div>
              ))}
              <div>
                <dt>File SHA-256</dt>
                <dd><code className="wrap">{asset?.sha256 ?? "—"}</code></dd>
              </div>
            </dl>
          </details>

          {list.length === 0 ? (
            <Empty>No extracted {unit.toLowerCase()}s yet (status: {asset?.status ?? "unknown"}).</Empty>
          ) : (
            <div className="card">
              <div className="card-head">
                <h3>{list.length} {unit.toLowerCase()}s extracted</h3>
                <div className="segmented small-seg">
                  <button type="button" className={`seg-btn ${viewMode === "inspector" ? "on" : ""}`} onClick={() => setViewMode("inspector")}>
                    Reader view
                  </button>
                  <button type="button" className={`seg-btn ${viewMode === "grid" ? "on" : ""}`} onClick={() => setViewMode("grid")}>
                    All {unit.toLowerCase()}s grid
                  </button>
                </div>
              </div>

              {viewMode === "inspector" && activeSlide ? (
                <div className="doc-inspector-layout">
                  <div className="doc-rail" aria-label={`${unit} list`}>
                    {list.map((s) => (
                      <button
                        key={s.id}
                        type="button"
                        className={`doc-rail-item ${s.page === activeSlide.page ? "on" : ""}`}
                        onClick={() => selectPage(s.page)}
                      >
                        <MediaImage url={s.image_url} kind="slide" title={s.text} sub={`${unit} ${s.page}`} alt={`${unit} ${s.page}`} />
                        <div className="doc-rail-meta">
                          <strong>{unit} {s.page}</strong>
                          {s.matches.length > 0 && <Badge tone={s.matches.some((m) => m.type === "shared") ? "purple" : "amber"}>{s.matches.length} match</Badge>}
                        </div>
                      </button>
                    ))}
                  </div>

                  <div className="doc-detail-pane">
                    <div className="doc-preview">
                      <MediaImage url={activeSlide.image_url} kind="slide" title={activeSlide.text} sub={`${unit} ${activeSlide.page}`} alt={`${unit} ${activeSlide.page}`} />
                    </div>
                    <div className="doc-detail-body">
                      <div className="doc-detail-head">
                        <h3>{unit} {activeSlide.page} of {list.length}</h3>
                        <div className="row-actions">
                          <button type="button" className="btn btn-secondary btn-xs" disabled={activeSlide.page <= 1} onClick={() => selectPage(activeSlide.page - 1)}>
                            ← Prev
                          </button>
                          <button type="button" className="btn btn-secondary btn-xs" disabled={activeSlide.page >= list.length} onClick={() => selectPage(activeSlide.page + 1)}>
                            Next →
                          </button>
                        </div>
                      </div>

                      {activeSlide.matches.length > 0 && (
                        <div className="match-list">
                          {activeSlide.matches.map((m) => (
                            <MatchBadge key={`${m.other_asset_id}:${m.other_page}`} m={m} />
                          ))}
                        </div>
                      )}

                      <div className="extracted-text-box">
                        <div className="small muted">Extracted text ({formatBytes(activeSlide.bytes)} slide preview)</div>
                        <pre className="slide-text-pre">{activeSlide.text || "(no selectable text on this page)"}</pre>
                      </div>

                      <dl className="evidence-inline">
                        <div><dt>Text SHA-256</dt><dd><code>{shortHash(activeSlide.hashes.text_sha256, 16)}</code></dd></div>
                        <div><dt>pHash</dt><dd><code>{activeSlide.hashes.phash}</code></dd></div>
                        <div><dt>Image SHA-256</dt><dd><code>{shortHash(activeSlide.hashes.file_sha256, 16)}</code></dd></div>
                      </dl>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="slide-grid">
                  {list.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      className="slide-grid-card"
                      onClick={() => {
                        selectPage(s.page);
                        setViewMode("inspector");
                      }}
                    >
                      <MediaImage url={s.image_url} kind="slide" title={s.text} sub={`${unit} ${s.page}`} alt={`${unit} ${s.page}`} />
                      <div className="slide-grid-foot">
                        <strong>{unit} {s.page}</strong>
                        {s.matches.length > 0 && <Badge tone="purple">{s.matches.length}</Badge>}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
