import { useState } from "react";
import type { StorageReport, StorageScenario } from "@contracts/ts/dso-contracts";
import { api } from "../api/client";
import { USE_MOCKS } from "../api/config";
import { useAsync } from "../lib/useAsync";
import { exactBytes, formatBytes, formatDate, formatPct } from "../lib/format";
import { Badge, Callout, ErrorBox, Loading, PageHeader, Stat } from "../components/ui";

const pctOf = (v: number, max: number) => `max(${v > 0 ? 2 : 0}px, ${(v / max) * 100}%)`;

/** Re-check the backend's numbers with the frozen formula so the demo can show the maths adds up. */
function check(s: StorageScenario) {
  const A = s.kept_original_bytes + s.derived_bytes + s.index_bytes;
  const pct = s.before_bytes ? ((s.before_bytes - A) / s.before_bytes) * 100 : null;
  const ok = A === s.after_bytes && s.before_bytes - A === s.saved_bytes && (pct === null ? s.savings_pct === null : Math.abs(pct - (s.savings_pct ?? NaN)) < 0.01);
  return { A, pct, ok };
}

function Bars({ s, max }: { s: StorageScenario; max: number }) {
  return (
    <div className="bars" aria-hidden>
      <div className="bar-row">
        <span className="bar-label">Before (O)</span>
        <div className="bar-track">
          <div className="bar orig" style={{ width: pctOf(s.before_bytes, max) }} />
        </div>
        <span className="bar-val">{formatBytes(s.before_bytes)}</span>
      </div>
      <div className="bar-row">
        <span className="bar-label">After (A)</span>
        <div className="bar-track">
          <div className="bar orig" style={{ width: pctOf(s.kept_original_bytes, max) }} title="kept originals" />
          <div className="bar derived" style={{ width: pctOf(s.derived_bytes, max) }} title="derived files" />
          <div className="bar index" style={{ width: pctOf(s.index_bytes, max) }} title="index" />
        </div>
        <span className="bar-val">{formatBytes(s.after_bytes)}</span>
      </div>
    </div>
  );
}

function ScenarioCard({ s, max, open, onToggle }: { s: StorageScenario; max: number; open: boolean; onToggle: () => void }) {
  const c = check(s);
  const negative = s.saved_bytes <= 0;
  return (
    <article className={`card scenario ${s.hypothetical ? "hypo" : "real"}`}>
      <div className="card-head">
        <h3>{s.label}</h3>
        {s.hypothetical ? <Badge tone="amber">Hypothetical · needs approval</Badge> : <Badge tone="blue">Real · today</Badge>}
      </div>
      <p className="muted">{s.description}</p>
      <div className={`big-pct ${negative ? "neg" : "pos"}`}>
        {formatPct(s.savings_pct)}
        <span className="small"> {negative ? "added" : "saved"}: {formatBytes(Math.abs(s.saved_bytes))}</span>
      </div>
      <Bars s={s} max={max} />
      <div className="formula">
        <code>{s.formula}</code>
        <div className="small">
          A = {exactBytes(s.kept_original_bytes)} kept + {exactBytes(s.derived_bytes)} D + {exactBytes(s.index_bytes)} I = <b>{exactBytes(c.A)}</b>
        </div>
        <div className="small">
          ({exactBytes(s.before_bytes)} − {exactBytes(c.A)}) / {exactBytes(s.before_bytes)} × 100 = <b>{formatPct(c.pct, 4)}</b>{" "}
          {c.ok ? <span className="ok">✓ matches report</span> : <span className="err-text">✗ does not match the report: check backend</span>}
        </div>
      </div>
      <button className="btn small ghost" onClick={onToggle} aria-expanded={open}>
        {open ? "Hide" : "Show"} what would be removed ({s.removed.length})
      </button>
      {open &&
        (s.removed.length === 0 ? (
          <p className="muted small">Nothing. The tool never deletes; this is the real situation today.</p>
        ) : (
          <ul className="removed">
            {s.removed.map((r) => (
              <li key={r.asset_id}>
                <b>{r.filename}</b> · {formatBytes(r.bytes)} ·{" "}
                {r.reason === "exact_duplicate" ? `exact duplicate (copy ${r.kept_copy_asset_id} stays)` : "replaced by its derived data"}
              </li>
            ))}
          </ul>
        ))}
    </article>
  );
}

function Totals({ r }: { r: StorageReport }) {
  const t = r.totals;
  return (
    <div className="stats-row">
      <Stat label="O · originals in scope" value={formatBytes(t.original_bytes)} sub={`${t.asset_count} files · video ${formatBytes(t.video_original_bytes)} · docs ${formatBytes(t.document_original_bytes)}`} />
      <Stat label="D · derived files + manifests" value={formatBytes(t.derived_bytes)} sub="added by processing" />
      <Stat label="I · SQLite + FTS index" value={formatBytes(t.index_bytes)} sub="added by processing" />
      <Stat label="Extra exact copies" value={formatBytes(t.extra_exact_copy_bytes)} sub="beyond the first copy per SHA-256" />
    </div>
  );
}

export default function Storage() {
  const res = useAsync(() => api.getStorageReport(), []);
  const [open, setOpen] = useState<Record<number, boolean>>({});
  const r = res.data;
  const max = r ? Math.max(...r.scenarios.map((s) => Math.max(s.before_bytes, s.after_bytes))) : 1;

  return (
    <section>
      <PageHeader title="Storage report" lead="How many bytes would really be freed, and under which decision. Processing alone saves nothing.">
        {r && (
          <Badge tone={USE_MOCKS ? "amber" : "green"} title={formatDate(r.generated_at)}>
            {USE_MOCKS ? "Mock fixture numbers (measured-style, not a real run)" : "Measured on disk by the backend"}
          </Badge>
        )}
      </PageHeader>

      {res.loading ? (
        <Loading label="Measuring…" />
      ) : res.error ? (
        <ErrorBox error={res.error} onRetry={res.reload} />
      ) : r ? (
        <>
          <div className="card formula-card">
            <h3>The formula</h3>
            <p className="formula-main">
              <code>{r.formula}</code>
            </p>
            <p>
              <b>O</b> = bytes of all original files in scope (every copy on every simulated system). <b>A</b> = originals still kept + <b>all</b>{" "}
              derived files (D) + the database/index (I). D and I are counted in every scenario, so the numbers are conservative.
            </p>
          </div>
          <Totals r={r} />
          <div className="legend small">
            <span>
              <i className="sw orig" /> originals kept
            </span>
            <span>
              <i className="sw derived" /> derived files (D)
            </span>
            <span>
              <i className="sw index" /> index (I)
            </span>
          </div>
          <div className="scenario-grid">
            {r.scenarios.map((s) => (
              <ScenarioCard key={s.id} s={s} max={max} open={!!open[s.id]} onToggle={() => setOpen((p) => ({ ...p, [s.id]: !p[s.id] }))} />
            ))}
          </div>

          <div className="grid-2">
            <div className="card">
              <h3>Not counted</h3>
              <ul>
                {r.not_counted.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
              <h3>Information lost if an original were removed</h3>
              <ul>
                {r.information_lost.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
            </div>
            <div className="card">
              <h3>Notes</h3>
              <ul>
                {r.notes.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
              <Callout tone="warn" title="Ericsson's illustration, not our measurement:">
                The challenge PDF (p.2) gives an example of about 1 GB of video becoming about 50 KB of text plus about 2 MB of frames, “roughly 99%”.
                We show it only for comparison. Every number above comes from {USE_MOCKS ? "the mock fixtures" : "files measured on disk"}.
              </Callout>
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}
