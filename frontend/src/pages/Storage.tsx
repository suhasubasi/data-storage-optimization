import { useState } from "react";
import type { StorageReport, StorageScenario } from "@contracts/ts/dso-contracts";
import { api } from "../api/client";
import { useAsync } from "../lib/useAsync";
import { exactBytes, formatBytes, formatDate, formatPct } from "../lib/format";
import { Badge, Callout, ErrorBox, Loading, PageHeader, StatCard } from "../components/ui";
import { checkScenario } from "../lib/impact";

const pctOf = (v: number, max: number) => `max(${v > 0 ? 2 : 0}px, ${(v / Math.max(1, max)) * 100}%)`;

function checkFormula(s: StorageScenario) {
  const { after, pct, valid } = checkScenario(s);
  return { A: after, pct, ok: valid };
}

function ScenarioCard({
  s,
  max,
  open,
  onToggle,
}: {
  s: StorageScenario;
  max: number;
  open: boolean;
  onToggle: () => void;
}) {
  const c = checkFormula(s);
  const negative = s.saved_bytes <= 0;

  return (
    <article className={`card scenario-card ${s.hypothetical ? "hypo" : "real"}`}>
      <div className="card-head">
        <h3>{s.label}</h3>
        {s.hypothetical ? <Badge tone="amber">Simulated · requires approval</Badge> : <Badge tone="blue">Measured · current disk</Badge>}
      </div>
      <p className="muted small">{s.description}</p>

      <div className={`scenario-kpi ${negative ? "neg" : "pos"}`}>
        <strong>{formatPct(s.savings_pct)}</strong>
        <span>
          {negative ? "added" : s.hypothetical ? "potential reduction" : "reduction"}: {formatBytes(Math.abs(s.saved_bytes))}
        </span>
      </div>

      <div className="stack-bars" aria-hidden>
        <div className="stack-row">
          <span className="stack-label">Before (O)</span>
          <div className="stack-track">
            <div className="seg-orig" style={{ width: pctOf(s.before_bytes, max) }} />
          </div>
          <span className="stack-val">{formatBytes(s.before_bytes)}</span>
        </div>
        <div className="stack-row">
          <span className="stack-label">After (A)</span>
          <div className="stack-track">
            <div className="seg-orig" style={{ width: pctOf(s.kept_original_bytes, max) }} title="Kept originals" />
            <div className="seg-derived" style={{ width: pctOf(s.derived_bytes, max) }} title="Derived outputs (D)" />
            <div className="seg-index" style={{ width: pctOf(s.index_bytes, max) }} title="SQLite + FTS index (I)" />
          </div>
          <span className="stack-val">{formatBytes(s.after_bytes)}</span>
        </div>
      </div>

      <div className="formula-panel">
        <code>{s.formula}</code>
        <div className="small muted">
          A = {exactBytes(s.kept_original_bytes)} kept + {exactBytes(s.derived_bytes)} D + {exactBytes(s.index_bytes)} I = <b>{exactBytes(c.A)}</b>
        </div>
        <div className="small">
          Verified: <b>{formatPct(c.pct, 4)}</b>{" "}
          {c.ok ? <Badge tone="green">✓ Matches report</Badge> : <Badge tone="red">✗ Check formula</Badge>}
        </div>
      </div>

      <button type="button" className="btn btn-secondary btn-xs" onClick={onToggle} aria-expanded={open}>
        {open ? "Hide" : "Show"} flagged removals ({s.removed.length})
      </button>

      {open &&
        (s.removed.length === 0 ? (
          <p className="muted small">None — nothing is removed in current read-only mode.</p>
        ) : (
          <ul className="removed-list">
            {s.removed.map((r) => (
              <li key={r.asset_id}>
                <b>{r.filename}</b> · {formatBytes(r.bytes)} ·{" "}
                {r.reason === "exact_duplicate" ? `exact copy (keep ${r.kept_copy_asset_id})` : "replaced by derived index"}
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
    <div className="stats-grid-4">
      <StatCard
        label="O · Originals in scope"
        value={formatBytes(t.original_bytes)}
        sub={`${t.asset_count} files (video ${formatBytes(t.video_original_bytes)} · docs ${formatBytes(t.document_original_bytes)})`}
        tone="accent"
      />
      <StatCard label="D · Derived files + manifests" value={formatBytes(t.derived_bytes)} sub="Transcripts, slide decks, keyframes" />
      <StatCard label="I · SQLite + FTS index" value={formatBytes(t.index_bytes)} sub="Database index (always counted)" />
      <StatCard label="Exact duplicate overhead" value={formatBytes(t.extra_exact_copy_bytes)} sub="Copies beyond first per SHA-256" tone="safe" />
    </div>
  );
}

export default function Storage() {
  const [includeTest, setIncludeTest] = useState(false);
  const res = useAsync(() => api.getStorageReport(includeTest), [includeTest]);
  const [open, setOpen] = useState<Record<number, boolean>>({});
  const r = res.data;
  const max = r ? Math.max(...r.scenarios.map((s) => Math.max(s.before_bytes, s.after_bytes))) : 1;

  return (
    <section className="page-stack page-storage">
      <PageHeader
        title="Storage optimizer"
        lead="Understand your storage footprint. Compare measured usage with potential savings before making decisions."
        actions={r && <Badge tone="green" title={formatDate(r.generated_at)}>Measured on disk</Badge>}
      />

      <div className="card scope-card">
        <div className="scope-head">
          <label className="check-inline">
            <input type="checkbox" checked={includeTest} onChange={(e) => setIncludeTest(e.target.checked)} />
            <span>Include synthetic generated test files</span>
          </label>
          <span className="muted small">
            {r?.scope === "all_files"
              ? "Scope: all library assets including synthetic test files."
              : r?.excluded_test_data && r.excluded_test_data.asset_count > 0
                ? `Real uploads only (${r.excluded_test_data.asset_count} synthetic files totaling ${formatBytes(
                    r.excluded_test_data.original_bytes + r.excluded_test_data.derived_bytes,
                  )} excluded conservatively).`
                : "Scope: all real uploaded files."}
          </span>
        </div>
      </div>

      {res.loading ? (
        <Loading label="Measuring files on disk…" />
      ) : res.error ? (
        <ErrorBox error={res.error} onRetry={res.reload} />
      ) : r ? (
        <>
          <Totals r={r} />

          <div className="card scenario-comparison">
            <div className="card-head"><div><span className="section-eyebrow">COMPARE THE DECISIONS</span><h2>Four scenarios. One consistent calculation.</h2></div><Badge tone="blue">Nothing deleted</Badge></div>
            <p className="muted small">Savings are relative to original file bytes. Every scenario includes all derived files and the index. Positive savings require an approved change to retained originals.</p>
            <div className="table-wrap"><table className="data-table">
              <thead><tr><th>Scenario</th><th className="num">Original baseline</th><th className="num">Total after</th><th className="num">Savings</th><th>Decision</th></tr></thead>
              <tbody>{r.scenarios.map((s) => <tr key={s.id} className={s.key === "both" ? "combined-scenario" : ""}>
                <td><a href={`#scenario-${s.id}`}>{s.label}</a></td>
                <td className="num">{formatBytes(s.before_bytes)}</td><td className="num">{formatBytes(s.after_bytes)}</td>
                <td className="num"><strong>{checkScenario(s).valid ? formatPct(s.savings_pct, 1) : "Check formula"}</strong></td>
                <td>{s.hypothetical ? <Badge tone="amber">Requires approval</Badge> : <Badge tone="blue">Current usage</Badge>}</td>
              </tr>)}</tbody>
            </table></div>
          </div>

          <div className="card formula-banner">
            <div>
              <div className="small muted">Canonical savings equation</div>
              <code className="formula-big">{r.formula}</code>
            </div>
            <div className="legend-row small">
              <span><i className="sw sw-orig" /> Kept originals</span>
              <span><i className="sw sw-derived" /> Derived (D)</span>
              <span><i className="sw sw-index" /> SQLite Index (I)</span>
            </div>
          </div>

          <div className="scenario-grid">
            {r.scenarios.map((s) => (
              <div id={`scenario-${s.id}`} key={s.id} className="scenario-anchor"><ScenarioCard s={s} max={max} open={!!open[s.id]} onToggle={() => setOpen((p) => ({ ...p, [s.id]: !p[s.id] }))} /></div>
            ))}
          </div>

          <div className="split-2">
            <div className="card">
              <h3>Methodology boundaries</h3>
              <h4>Not counted in totals</h4>
              <ul className="plain-list">
                {r.not_counted.map((x) => <li key={x}>{x}</li>)}
              </ul>
              <h4>Lost if originals are later removed</h4>
              <ul className="plain-list">
                {r.information_lost.map((x) => <li key={x}>{x}</li>)}
              </ul>
            </div>
            <div className="card">
              <h3>Notes &amp; challenge benchmark comparison</h3>
              <ul className="plain-list">
                {r.notes.map((x) => <li key={x}>{x}</li>)}
              </ul>
              <Callout tone="warn" title="Ericsson challenge brief illustration vs real measurements:">
                The hackathon PDF illustrates ~1 GB video → 50 KB text + 2 MB frames (~99% saving). All figures above reflect actual byte sizes on disk in your workspace.
              </Callout>
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}
