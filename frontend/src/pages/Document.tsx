import { useEffect, useRef } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import type { AssetMetadata, SlideMatch } from "@contracts/ts/dso-contracts";
import { api } from "../api/client";
import { USE_MOCKS } from "../api/config";
import { useAsync } from "../lib/useAsync";
import { formatBytes, SOURCE_LABEL, shortHash } from "../lib/format";
import { AssetPicker } from "../components/AssetPicker";
import { MediaImage } from "../components/MediaImage";
import { Badge, Callout, Empty, ErrorBox, Loading, PageHeader, SourceBadge, Stat } from "../components/ui";

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
    <Link to={`/document/${m.other_asset_id}?page=${m.other_page}`} className="match-link">
      <Badge tone={shared ? "purple" : "amber"} title={`method: ${m.method} · score ${m.score}`}>
        {shared ? "Also in" : "Similar to"} {m.other_filename} p.{m.other_page} ({SOURCE_LABEL[m.other_source_system]})
        {!shared && " · needs review"}
      </Badge>
    </Link>
  );
}

export default function DocumentView() {
  const { assetId } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const assets = useAsync(() => api.listAssets(), []);
  const docs = (assets.data?.assets ?? []).filter((a) => a.kind === "document");
  const id = assetId ?? docs.find((a) => a.status === "ready")?.id ?? docs[0]?.id;

  const slides = useAsync(() => api.getSlides(id!), [id], !!id);
  const detail = useAsync(() => api.getAsset(id!), [id], !!id);
  const dups = useAsync(() => api.getDuplicates("exact_file"), []);
  const focusPage = Number(params.get("page") ?? 0);
  const refs = useRef<Record<number, HTMLElement | null>>({});

  useEffect(() => {
    if (focusPage && slides.data) setTimeout(() => refs.current[focusPage]?.scrollIntoView({ behavior: "smooth", block: "center" }), 80);
  }, [focusPage, slides.data]);

  const asset = detail.data?.asset;
  const exactGroup = dups.data?.groups.find((g) => g.members.some((m) => m.asset_id === id));
  const copies = exactGroup?.members.filter((m) => m.asset_id !== id) ?? [];
  const meta = slides.data?.metadata ?? detail.data?.metadata ?? null;
  const list = slides.data?.slides ?? [];
  const sharedCount = list.filter((s) => s.matches.some((m) => m.type === "shared")).length;
  const similarCount = list.filter((s) => s.matches.some((m) => m.type === "similar")).length;
  const isDeck = /\.pptx$/i.test(asset?.filename ?? "");
  const unit = isDeck ? "Slide" : "Page";
  const warnings = detail.data?.pipeline?.warnings ?? [];

  return (
    <section>
      <PageHeader title="Document / slide view" lead="Each PDF page or PowerPoint slide with its text and three hashes: file SHA-256, normalised-text SHA-256 and perceptual image hash (pHash).">
        {assets.data && <AssetPicker assets={assets.data.assets} kind="document" value={id} label="Document" onChange={(v) => navigate(`/document/${v}`)} />}
      </PageHeader>

      {assets.error ? (
        <ErrorBox error={assets.error} onRetry={assets.reload} />
      ) : !id && assets.data ? (
        <Empty>No documents yet. Upload a .pdf or .pptx in Library & ingest.</Empty>
      ) : slides.loading || assets.loading ? (
        <Loading label="Loading pages…" />
      ) : slides.error ? (
        <ErrorBox error={slides.error} onRetry={slides.reload} />
      ) : (
        <>
          {copies.length > 0 && (
            <Callout tone="warn" title="Exact copy found.">
              This whole file has the same SHA-256 as{" "}
              {copies.map((c, i) => (
                <span key={c.asset_id}>
                  {i > 0 && ", "}
                  <Link to={`/document/${c.asset_id}`}>{c.filename}</Link> ({SOURCE_LABEL[c.source_system]}, owner {c.owner})
                </span>
              ))}
              . The file name does not decide this; the bytes do. See <Link to="/duplicates">Duplicates</Link>.
            </Callout>
          )}

          <div className="stats-row">
            <Stat label="Original (kept)" value={formatBytes(asset?.bytes)} sub={asset && <SourceBadge source={asset.source_system} />} />
            <Stat label="Derived (added)" value={formatBytes(detail.data?.derived?.derived_bytes)} sub={`${list.length} ${unit.toLowerCase()} images + text`} />
            <Stat label="Shared slides" value={sharedCount} sub="same text hash + close pHash in another file" />
            <Stat label="Similar slides" value={similarCount} sub="needs human review, never exact" />
          </div>

          <div className="card">
            <h3>Metadata (only what the file really contains)</h3>
            <dl className="meta">
              {META_FIELDS.map(([k, label]) => (
                <div key={k}>
                  <dt>{label}</dt>
                  <dd>{meta?.[k] ? String(meta[k]) : <span className="muted">not found in file</span>}</dd>
                </div>
              ))}
              <div>
                <dt>File SHA-256</dt>
                <dd>
                  <code className="wrap">{asset?.sha256 ?? "—"}</code>
                </dd>
              </div>
            </dl>
          </div>

          {warnings.length > 0 && (
            <Callout tone="info">
              Processing notes: {warnings.join(" · ")}
            </Callout>
          )}

          {list.length === 0 ? (
            <Empty>
              No pages for this file yet. Process it first (status: {asset?.status ?? "unknown"}).
              {USE_MOCKS && " In mock mode, only the fixture PDFs have pages."}
            </Empty>
          ) : (
            <div className="slide-grid">
              {list.map((s) => (
                <article key={s.id} ref={(el) => (refs.current[s.page] = el)} className={`card slide-card ${focusPage === s.page ? "focus" : ""}`}>
                  <MediaImage url={s.image_url} kind="slide" title={s.text} sub={`${asset?.filename ?? id} · ${unit.toLowerCase()} ${s.page}`} alt={`${unit} ${s.page}: ${s.text}`} />
                  <div className="slide-body">
                    <div className="slide-head">
                      <b>{unit} {s.page}</b>
                      <span className="muted small">{formatBytes(s.bytes)} image</span>
                    </div>
                    <p className="slide-text">{s.text || <span className="muted">{isDeck ? "No text on this slide." : "No text layer on this page."}</span>}</p>
                    <div className="badges">
                      {s.matches.length === 0 ? <Badge tone="green">Unique in library</Badge> : s.matches.map((m, i) => <MatchBadge key={i} m={m} />)}
                    </div>
                    <dl className="hashes">
                      <dt>text SHA-256</dt>
                      <dd>
                        <code title={s.hashes.text_sha256}>{shortHash(s.hashes.text_sha256, 16)}</code>
                      </dd>
                      <dt>pHash</dt>
                      <dd>
                        <code>{s.hashes.phash}</code>
                      </dd>
                      <dt>file SHA-256</dt>
                      <dd>
                        <code title={s.hashes.file_sha256}>{shortHash(s.hashes.file_sha256, 16)}</code>
                      </dd>
                    </dl>
                  </div>
                </article>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
