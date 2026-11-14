import { Link, useSearchParams } from "react-router-dom";
import type { DuplicateGroup, DuplicateType } from "@contracts/ts/dso-contracts";
import { api } from "../api/client";
import { useAsync } from "../lib/useAsync";
import { formatBytes, shortHash } from "../lib/format";
import { MediaImage } from "../components/MediaImage";
import { Snippet } from "../components/Snippet";
import { Badge, Callout, Empty, ErrorBox, Loading, PageHeader, SourceBadge, type Tone } from "../components/ui";

const TYPES: { key: DuplicateType; label: string; tone: Tone; explain: string }[] = [
  {
    key: "exact_file",
    label: "Exact file copy",
    tone: "red",
    explain: "Same SHA-256 bytes across multiple files. Only exact file copies can ever reclaim storage—and only after explicit human approval.",
  },
  {
    key: "shared_slide",
    label: "Shared slide",
    tone: "purple",
    explain: "Same normalised text SHA-256 and close perceptual hash across two distinct files. Frees 0 B because surrounding files differ.",
  },
  {
    key: "similar_slide",
    label: "Similar — review",
    tone: "amber",
    explain: "Close perceptual image hash or text overlap with differences highlighted below. Never merged automatically.",
  },
];

function Evidence({ g }: { g: DuplicateGroup }) {
  const e = g.evidence;
  return (
    <dl className="evidence-panel">
      <div><dt>Detection method</dt><dd><code>{e.method}</code></dd></div>
      {e.sha256 && <div><dt>File SHA-256</dt><dd><code title={e.sha256}>{shortHash(e.sha256, 20)}</code></dd></div>}
      {e.text_sha256 && <div><dt>Text SHA-256</dt><dd><code title={e.text_sha256}>{shortHash(e.text_sha256, 20)}</code></dd></div>}
      {e.phash_distance != null && <div><dt>pHash distance</dt><dd>{e.phash_distance} / 64 bits</dd></div>}
      {e.text_similarity != null && <div><dt>Text similarity</dt><dd>{Math.round(e.text_similarity * 100)} %</dd></div>}
      <div><dt>Score</dt><dd><b>{g.score}</b></dd></div>
    </dl>
  );
}

function diffMark(text: string, other: string) {
  const norm = (w: string) => w.toLowerCase().replace(/[^\p{L}\p{N}%]/gu, "");
  const have = new Set(other.split(/\s+/).map(norm));
  return text
    .split(/(\s+)/)
    .map((w) => (w.trim() && !have.has(norm(w)) ? `<mark>${w}</mark>` : w))
    .join("");
}

function GroupCard({
  g,
  created,
  texts,
  testIds,
}: {
  g: DuplicateGroup;
  created: Record<string, string>;
  texts: Record<string, string>;
  testIds: Set<string>;
}) {
  const t = TYPES.find((x) => x.key === g.type)!;
  const isFile = g.type === "exact_file";
  const keptId = isFile
    ? [...g.members].sort((a, b) => (created[a.asset_id] ?? "").localeCompare(created[b.asset_id] ?? ""))[0].asset_id
    : null;
  const extraBytes = isFile ? g.members.filter((m) => m.asset_id !== keptId).reduce((s, m) => s + m.bytes, 0) : 0;

  return (
    <article className="card dup-card">
      <div className="card-head">
        <div className="row-actions">
          <Badge tone={t.tone}>{t.label}</Badge>
          <code className="muted small">{g.id}</code>
          {g.needs_review && <Badge tone="amber">Needs review</Badge>}
        </div>
        {isFile ? (
          <Badge tone="green">Extra copies: {formatBytes(extraBytes)} (after approval)</Badge>
        ) : (
          <span className="muted small">Frees 0 B (files differ)</span>
        )}
      </div>

      <div className="dup-body">
        <div className={`dup-members ${isFile ? "files" : "slides"}`}>
          {g.members.map((m) => {
            const text = m.slide_id ? texts[`${m.asset_id}:${m.slide_id}`] : undefined;
            const other = g.members.find((o) => o !== m);
            const otherText = other?.slide_id ? texts[`${other.asset_id}:${other.slide_id}`] : undefined;
            return (
              <Link
                key={`${m.asset_id}:${m.slide_id ?? ""}`}
                to={m.page ? `/document/${m.asset_id}?page=${m.page}` : `/document/${m.asset_id}`}
                className="dup-member"
              >
                {!isFile && (
                  <MediaImage
                    url={m.image_url}
                    kind="slide"
                    title={text ?? `${m.filename} p.${m.page}`}
                    sub={`${m.asset_id}:${m.slide_id}`}
                    alt={`${m.filename} page ${m.page}`}
                  />
                )}
                <div className="dup-member-title">
                  <strong>{m.filename}</strong>
                  {testIds.has(m.asset_id) && <Badge tone="amber">test file</Badge>}
                  {m.page && <span className="muted"> · page {m.page}</span>}
                  {isFile && m.asset_id === keptId && <Badge tone="green">Kept earliest copy</Badge>}
                </div>
                <div className="dup-member-meta">
                  <SourceBadge source={m.source_system} />
                  <span className="muted small">owner {m.owner} · {formatBytes(m.bytes)}</span>
                </div>
                {text !== undefined && (
                  <div className="dup-member-text">
                    “{g.type === "similar_slide" && otherText !== undefined ? <Snippet html={diffMark(text, otherText)} /> : text}”
                  </div>
                )}
              </Link>
            );
          })}
        </div>
        <Evidence g={g} />
      </div>
    </article>
  );
}

export default function Duplicates() {
  const [params, setParams] = useSearchParams();
  const filter = (params.get("type") as DuplicateType | null) ?? null;
  const res = useAsync(() => api.getDuplicates(), []);
  const assets = useAsync(() => api.listAssets(), []);

  const slideAssets = Array.from(
    new Set((res.data?.groups ?? []).filter((g) => g.type !== "exact_file").flatMap((g) => g.members.map((m) => m.asset_id))),
  ).sort();
  const slideTexts = useAsync(
    async () => {
      const lists = await Promise.all(slideAssets.map((id) => api.getSlides(id).catch(() => null)));
      const out: Record<string, string> = {};
      for (const l of lists) if (l) for (const sl of l.slides) out[`${l.asset_id}:${sl.id}`] = sl.text;
      return out;
    },
    [slideAssets.join(",")],
    slideAssets.length > 0,
  );

  const created = Object.fromEntries((assets.data?.assets ?? []).map((a) => [a.id, a.created_at]));
  const testIds = new Set((assets.data?.assets ?? []).filter((a) => a.test_data).map((a) => a.id));
  const groups = (res.data?.groups ?? []).filter((g) => !filter || g.type === filter);

  return (
    <section className="page-stack page-duplicates">
      <PageHeader
        title="Duplicate & similarity analyzer"
        lead="See what overlaps. Compare identical files, reused slides, and similar content side by side."
      />

      <div className="pill-tabs" role="tablist">
        <button type="button" role="tab" aria-selected={!filter} className={`pill-tab ${!filter ? "on" : ""}`} onClick={() => setParams({})}>
          All groups {res.data && `(${res.data.groups.length})`}
        </button>
        {TYPES.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={filter === t.key}
            className={`pill-tab ${filter === t.key ? "on" : ""}`}
            onClick={() => setParams({ type: t.key })}
          >
            {t.label} {res.data && `(${res.data.counts[t.key]})`}
          </button>
        ))}
      </div>

      <div className="explain-grid">
        {TYPES.filter((t) => !filter || t.key === filter).map((t) => (
          <Callout key={t.key} tone={t.key === "similar_slide" ? "warn" : "info"} title={`${t.label}:`}>
            {t.explain}
          </Callout>
        ))}
      </div>

      {res.loading ? (
        <Loading label="Inspecting hashes & overlaps…" />
      ) : res.error ? (
        <ErrorBox error={res.error} onRetry={res.reload} />
      ) : groups.length === 0 ? (
        <Empty>No duplicate groups of this category found.</Empty>
      ) : (
        groups.map((g) => <GroupCard key={g.id} g={g} created={created} texts={slideTexts.data ?? {}} testIds={testIds} />)
      )}
    </section>
  );
}
