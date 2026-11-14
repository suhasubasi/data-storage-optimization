import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useAsync } from "../lib/useAsync";
import { checkScenario, selectEvidence } from "../lib/impact";
import { formatBytes, formatDate, formatPct } from "../lib/format";
import { Badge, ErrorBox, Loading, PageHeader, StatCard } from "../components/ui";
import { IconChart, IconCode, IconCopy, IconPlay, IconSearch, IconShield } from "../components/Icons";

export default function Overview() {
  const report = useAsync(() => api.getStorageReport(), []);
  const assets = useAsync(() => api.listAssets(), []);
  const evidence = selectEvidence(assets.data?.assets ?? []);
  const r = report.data;
  const combined = r?.scenarios.find((s) => s.key === "both");
  const today = r?.scenarios.find((s) => s.key === "today");
  const valid = combined && checkScenario(combined).valid;
  const potential = valid && combined.before_bytes > 0 && combined.saved_bytes > 0;
  const chartMax = Math.max(r?.totals.original_bytes ?? 0, valid ? combined.after_bytes : 0, 1);
  const refresh = () => { report.reload(); assets.reload(); };

  return (
    <section className="page-stack page-overview">
      <PageHeader title="Less storage. More usable knowledge."
        lead="Turn recordings and documents into searchable, traceable data. See the impact, then inspect the evidence."
        actions={<button type="button" className="btn btn-secondary btn-sm" onClick={refresh}>Refresh measurements</button>} />

      {report.loading ? <Loading label="Measuring your workspace…" /> : report.error ? <ErrorBox error={report.error} onRetry={report.reload} /> : r && (
        <>
          <div className="impact-hero">
            <div className="impact-story">
              <Badge tone="amber">Potential savings · approval required</Badge>
              <div className="impact-number">{potential ? formatPct(combined.savings_pct, 1) : "Not yet available"}</div>
              <h2>{potential ? `${formatBytes(combined.saved_bytes)} less storage in the combined scenario` : "Build your evidence from real files"}</h2>
              <p>Replace processed video originals and remove exact copies, counting each file once. All derived files and the search index remain included.</p>
              {!valid && combined && <p className="impact-warning">The report did not pass the formula check. Review the storage report before using these figures.</p>}
              {valid && !potential && <p>No positive reduction in this scope yet. Upload and process files to explore the scenarios.</p>}
              <div className="row-actions">
                <Link to="/storage" className="btn btn-primary">Explore all four scenarios <IconChart size={16} /></Link>
                <Link to="/library" className="impact-secondary">Browse your files →</Link>
              </div>
            </div>
            <div className="impact-proof">
              <div className="impact-proof-title"><span>MEASURED BASELINE → PROJECTED TOTAL</span><IconShield size={18} /></div>
              <div className="impact-volume"><span>Original files</span><strong>{formatBytes(r.totals.original_bytes)}</strong></div>
              <div className="impact-track" aria-hidden="true"><span style={{ width: `${r.totals.original_bytes / chartMax * 100}%` }} /></div>
              <div className="impact-volume"><span>After approved changes</span><strong>{valid ? formatBytes(combined.after_bytes) : "Unavailable"}</strong></div>
              <div className="impact-track after" aria-hidden="true"><span style={{ width: valid ? `${combined.after_bytes / chartMax * 100}%` : "0%" }} /></div>
              <div className="impact-today">
                <strong>Today: {today && checkScenario(today).valid ? formatBytes(today.after_bytes) : "Unavailable"} on disk</strong>
                <span>Nothing deleted. Processing adds {formatBytes(r.totals.derived_bytes + r.totals.index_bytes)} of derived data and index.</span>
                <span>Replacing video can lose motion, gestures and tone. Review the trade-offs before approving.</span>
              </div>
              <p className="impact-footnote">Real uploads only · measured {formatDate(r.generated_at)}. Test files excluded.</p>
            </div>
          </div>

          <div className="stats-grid-4 impact-stats">
            <StatCard label="Original files in scope" value={r.totals.asset_count} sub={`${formatBytes(r.totals.original_bytes)} measured on disk`} />
            <StatCard label="Ready to explore" value={assets.loading ? "…" : assets.error ? "Unavailable" : evidence.readyCount} sub="Processed real recordings & documents" />
            <StatCard label="Extra exact-copy bytes" value={formatBytes(r.totals.extra_exact_copy_bytes)} sub="SHA-256 evidence · gross copy overhead" />
            <StatCard label="Deletion policy" value="Review first" sub="Originals retained · no automatic deletion" tone="safe" />
          </div>
        </>
      )}

      {assets.error && <ErrorBox error={assets.error} onRetry={assets.reload} />}
      <div className="evidence-section">
        <div className="section-heading"><div><span className="section-eyebrow">FROM CLAIM TO EVIDENCE</span><h2>Follow the information, end to end</h2></div><span className="muted small">Every step opens the working tool</span></div>
        <div className="evidence-grid">
          <Link className="evidence-card" to={evidence.recording ? `/recording/${evidence.recording.id}` : "/library?upload=1"}>
            <div className="evidence-card-top"><IconPlay /><span>01 / DISTILL</span></div>
            <h3>Keep the useful context</h3><p>Follow time-linked speech and key frames back to the original recording.</p>
            <span className="evidence-file">{evidence.recording?.filename ?? "Add a recording to begin"}</span>
            <strong>{evidence.recording ? "Open recording" : "Upload a file"} →</strong>
          </Link>
          <Link className="evidence-card" to="/search">
            <div className="evidence-card-top"><IconSearch /><span>02 / FIND</span></div>
            <h3>Find the exact moment</h3><p>Search spoken words, slide text and meeting chat. Open a result in context.</p>
            <span className="evidence-file">Text + frame + source timestamp</span><strong>Search the workspace →</strong>
          </Link>
          <Link className="evidence-card" to="/duplicates">
            <div className="evidence-card-top"><IconCopy /><span>03 / VERIFY</span></div>
            <h3>Prove what is duplicated</h3><p>Inspect exact copies, shared slides and similar revisions with their evidence.</p>
            <span className="evidence-file">Exact matches and review candidates stay distinct</span><strong>Review duplicates →</strong>
          </Link>
          <Link className="evidence-card" to="/export">
            <div className="evidence-card-top"><IconCode /><span>04 / ACTIVATE</span></div>
            <h3>Make knowledge AI-ready</h3><p>Export structured text with source links, timestamps and slide references.</p>
            <span className="evidence-file">JSONL corpus · JSON · transcripts · slide decks</span><strong>Explore the exports →</strong>
          </Link>
        </div>
      </div>

      <div className="overview-bottom">
        <div className="card strategy-card">
          <span className="section-eyebrow">A TRACEABLE DATA STRATEGY</span>
          <h2>Keep a path back to the source</h2>
          <ol className="strategy-steps">
            <li><b>Preserve</b><span>Read-only originals and file hashes.</span></li>
            <li><b>Structure</b><span>Local extraction, time links and slide identifiers.</span></li>
            <li><b>Activate</b><span>Searchable text and portable exports with provenance.</span></li>
            <li><b>Govern</b><span>Review evidence before retention decisions.</span></li>
          </ol>
          <div className="row-actions"><Link to="/offboarding" className="btn btn-secondary btn-sm">Review an owner's files</Link>{evidence.document && <Link to={`/document/${evidence.document.id}`} className="btn btn-ghost btn-sm">Inspect a document →</Link>}</div>
        </div>
        <details className="card scope-disclosure">
          <summary><span><span className="section-eyebrow">SCOPE & NEXT STEPS</span><strong>What this proves. What comes next.</strong></span><span className="disclosure-indicator">+</span></summary>
          <p><b>Working today:</b> local processing, search, duplicate evidence, scenario reports, offboarding recommendations and structured exports.</p>
          <p><b>Current limits:</b> source-system labels are simulated. Transcript and speaker accuracy need review. Removing a video can lose motion, gestures and tone; originals are retained here.</p>
          <p><b>Further work:</b> authenticated platform connectors, access-aware retrieval, retention approvals and measured transcription quality. Video reconstruction is not implemented.</p>
        </details>
      </div>
    </section>
  );
}
