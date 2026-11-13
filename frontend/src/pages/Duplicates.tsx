import { Link, useSearchParams } from "react-router-dom";
import type { DuplicateGroup, DuplicateType } from "@contracts/ts/dso-contracts";
import { api } from "../api/client";
import { useAsync } from "../lib/useAsync";
import { formatBytes, shortHash } from "../lib/format";
import { MediaImage } from "../components/MediaImage";
import { Snippet } from "../components/Snippet";
import { Badge, Callout, Empty, ErrorBox, Loading, PageHeader, SourceBadge } from "../components/ui";

const TYPES: { key: DuplicateType; label: string; tone: "red" | "purple" | "amber"; explain: string }[] = [
  {
    key: "exact_file",
    label: "Exact file copy",
    tone: "red",
    explain: "Same file SHA-256 = the same bytes. The file name never decides. Only these can free storage, and only after approval.",
  },
  {
    key: "shared_slide",
    label: "Shared slide",
    tone: "purple",
    explain: "Same normalised-text SHA-256 and pHash distance within the threshold, in two different files. Frees nothing: the files differ.",
  },
  {
    key: "similar_slide",
    label: "Similar — needs review",
    tone: "amber",
    explain: "Close image hash or close text, but not the same. A person must review it. Never treated as exact.",
  },
];

function Evidence({ g }: { g: DuplicateGroup }) {
  const e = g.evidence;
  return (
    <dl className="evidence">
      <dt>Method</dt>
      <dd>
        <code>{e.method}</code>
      </dd>
      {e.sha256 && (
        <>
          <dt>File SHA-256</dt>
          <dd>
            <code title={e.sha256}>{shortHash(e.sha256, 20)}</code>
          </dd>
        </>
      )}
      {e.text_sha256 && (
        <>
          <dt>Text SHA-256</dt>
          <dd>
            <code title={e.text_sha256}>{shortHash(e.text_sha256, 20)}</code>
          </dd>
        </>
      )}
      {e.phash_distance !== null && e.phash_distance !== undefined && (
        <>
          <dt>pHash distance</dt>
          <dd>{e.phash_distance} / 64 bits</dd>
        </>
      )}
      {e.text_similarity !== null && e.text_similarity !== undefined && (
        <>
          <dt>Text similarity</dt>
          <dd>{Math.round(e.text_similarity * 100)} %</dd>
        </>
      )}
      <dt>Score</dt>
      <dd>{g.score}</dd>
    </dl>
  );
}

/** Words in `text` that are missing from `other` get <mark>, so reviewers see what differs. */
function diffMark(text: string, other: string) {
  const norm = (w: string) => w.toLowerCase().replace(/[^\p{L}\p{N}%]/gu, "");
  const have = new Set(other.split(/\s+/).map(norm));
  return text
    .split(/(\s+)/)
    .map((w) => (w.trim() && !have.has(norm(w)) ? `<mark>${w}</mark>` : w))
    .join("");
}

function GroupCard({ g, created, texts, testIds }: { g: DuplicateGroup; created: Record<string, string>; texts: Record<string, string>; testIds: Set<string> }) {
  const t = TYPES.find((x) => x.key === g.type)!;
  const isFile = g.type === "exact_file";
  // Scenario 2 keeps the earliest upload in each SHA-256 group (CONTRACTS.md §6).
  const keptId = isFile
    ? [...g.members].sort((a, b) => (created[a.asset_id] ?? "").localeCompare(created[b.asset_id] ?? ""))[0].asset_id
    : null;
  const extraBytes = isFile ? g.members.filter((m) => m.asset_id !== keptId).reduce((s, m) => s + m.bytes, 0) : 0;
  return (
    <article className="card group">
      <div className="card-head">
        <div>
          <Badge tone={t.tone}>{t.label}</Badge> <code className="muted">{g.id}</code>
          {g.needs_review && <Badge tone="amber">needs review</Badge>}
        </div>
        {isFile ? (
          <span className="muted small">
            extra copies: <b>{formatBytes(extraBytes)}</b> (could be freed only after approval)
          </span>
        ) : (
          <span className="muted small">frees 0 B (files differ)</span>
        )}
      </div>
      <div className="group-body">
        <div className={`members ${isFile ? "files" : "slides"}`}>
          {g.members.map((m) => {
            const text = m.slide_id ? texts[`${m.asset_id}:${m.slide_id}`] : undefined;
            const other = g.members.find((o) => o !== m);
            const otherText = other?.slide_id ? texts[`${other.asset_id}:${other.slide_id}`] : undefined;
            return (
            <Link
              key={`${m.asset_id}:${m.slide_id ?? ""}`}
              to={m.page ? `/document/${m.asset_id}?page=${m.page}` : `/document/${m.asset_id}`}
              className="member"
            >
              {!isFile && (
                <MediaImage url={m.image_url} kind="slide" title={text ?? `${m.filename} p.${m.page}`} sub={`${m.asset_id}:${m.slide_id}`} alt={`${m.filename} page ${m.page}`} />
              )}
              <div>
                <b>{m.filename}</b>
                {testIds.has(m.asset_id) && (
                  <Badge tone="amber" title="Generated test file (synthetic sample), not a real upload">test file</Badge>
                )}
                {m.page && <span> · page {m.page}</span>}
                {isFile && m.asset_id === keptId && <Badge tone="green" title="Earliest upload is the copy kept in scenario 2">kept copy</Badge>}
              </div>
              <div className="member-meta">
                <SourceBadge source={m.source_system} /> <span className="muted small">owner {m.owner}</span>
                <span className="muted small"> · file {formatBytes(m.bytes)}</span>
              </div>
              {text !== undefined && (
                <div className="member-text">
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
  // Slide text for each member (one GET /slides per involved document) so reviewers can compare wording.
  const slideAssets = Array.from(new Set((res.data?.groups ?? []).filter((g) => g.type !== "exact_file").flatMap((g) => g.members.map((m) => m.asset_id)))).sort();
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
    <section>
      <PageHeader title="Duplicates" lead="Three levels, kept strictly apart. Nothing here deletes anything." />
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={!filter} className={`tab ${!filter ? "on" : ""}`} onClick={() => setParams({})}>
          All {res.data && <span className="count">{res.data.groups.length}</span>}
        </button>
        {TYPES.map((t) => (
          <button key={t.key} role="tab" aria-selected={filter === t.key} className={`tab ${filter === t.key ? "on" : ""}`} onClick={() => setParams({ type: t.key })}>
            {t.label} {res.data && <span className="count">{res.data.counts[t.key]}</span>}
          </button>
        ))}
      </div>
      <div className="explain-row">
        {TYPES.filter((t) => !filter || t.key === filter).map((t) => (
          <Callout key={t.key} tone={t.key === "similar_slide" ? "warn" : "info"} title={`${t.label}:`}>
            {t.explain}
          </Callout>
        ))}
      </div>
      {res.loading ? (
        <Loading label="Finding duplicates…" />
      ) : res.error ? (
        <ErrorBox error={res.error} onRetry={res.reload} />
      ) : groups.length === 0 ? (
        <Empty>No groups of this type. Upload the same PDF twice (e.g. as “deck (1).pdf”) to see an exact copy.</Empty>
      ) : (
        groups.map((g) => <GroupCard key={g.id} g={g} created={created} texts={slideTexts.data ?? {}} testIds={testIds} />)
      )}
    </section>
  );
}
