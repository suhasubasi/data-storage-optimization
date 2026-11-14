import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type { OffboardingReview } from "@contracts/ts/dso-contracts";
import { api } from "../api/client";
import { useAsync } from "../lib/useAsync";
import { downloadText, formatBytes, formatDate, KIND_LABEL, SOURCE_LABEL } from "../lib/format";
import { Badge, Callout, Empty, ErrorBox, Loading, PageHeader, SourceBadge, StatCard } from "../components/ui";

function toCsv(r: OffboardingReview) {
  const q = (v: string | number) => `"${String(v).replace(/"/g, '""')}"`;
  const head = ["asset_id", "filename", "kind", "bytes", "source_system", "recommendation", "reason", "duplicates_elsewhere"];
  const rows = r.rows.map((x) =>
    [
      x.asset_id,
      x.filename,
      x.kind,
      x.bytes,
      x.source_system,
      x.recommendation,
      x.reason,
      x.duplicates_elsewhere.map((d) => `${d.filename} (${d.source_system}, ${d.owner})`).join("; "),
    ]
      .map(q)
      .join(","),
  );
  return [`# Offboarding review for ${r.owner}. RECOMMENDATION ONLY. deletes_performed=false.`, head.join(","), ...rows].join("\n");
}

export default function Offboarding() {
  const [params, setParams] = useSearchParams();
  const owner = params.get("owner") ?? "";
  const assets = useAsync(() => api.listAssets(), []);
  const owners = Array.from(new Set((assets.data?.assets ?? []).map((a) => a.owner))).sort();
  const review = useAsync(() => api.getOffboarding(owner), [owner], !!owner);
  const [approver, setApprover] = useState<Record<string, boolean>>({});
  const r = review.data;

  return (
    <section className="page-stack page-offboarding">
      <PageHeader
        title="Offboarding governance review"
        lead="Keep knowledge in the right hands. Review an owner’s files and prepare recommendations without deleting anything."
      />

      <Callout tone="safe" title="Strict read-only enforcement (deletes_performed = false).">
        This view only produces recommendations. Shared or similar slides alone never qualify an original file for removal.
      </Callout>

      <div className="card">
        <div className="owner-picker">
          <label className="picker-field">
            <span className="picker-label">Select owner</span>
            <select className="select" value={owner} onChange={(e) => setParams(e.target.value ? { owner: e.target.value } : {})}>
              <option value="">Choose an employee / owner…</option>
              {owners.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </label>
          {owners.length > 0 && (
            <div className="speaker-chips">
              {owners.map((o) => (
                <button key={o} type="button" className={`chip ${owner === o ? "on" : ""}`} onClick={() => setParams({ owner: o })}>
                  {o}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {assets.error && <ErrorBox error={assets.error} onRetry={assets.reload} />}
      {!owner ? (
        <Empty>Choose an owner above to review their inventory.</Empty>
      ) : review.loading ? (
        <Loading label={`Auditing assets owned by ${owner}…`} />
      ) : review.error ? (
        <ErrorBox error={review.error} onRetry={review.reload} />
      ) : r ? (
        <>
          <div className="stats-grid-4">
            <StatCard label="Files owned" value={r.summary.total} />
            <StatCard label="Eligible after approval" value={r.summary.eligible} sub={`${formatBytes(r.summary.eligible_bytes)} could be reclaimed`} tone="warn" />
            <StatCard label="Keep" value={r.summary.keep} tone="safe" />
            <StatCard label="Deletes performed" value={String(r.deletes_performed)} sub={formatDate(r.generated_at)} tone="safe" />
          </div>

          {r.rows.length === 0 ? (
            <Empty>{owner} owns no assets in this library.</Empty>
          ) : (
            <div className="card">
              <div className="card-head">
                <h3>Approver packet · {r.owner}</h3>
                <div className="row-actions">
                  <button type="button" className="btn btn-primary btn-sm" onClick={() => downloadText(`offboarding-${r.owner}.csv`, toCsv(r), "text/csv")}>
                    Download CSV packet
                  </button>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => downloadText(`offboarding-${r.owner}.json`, JSON.stringify(r, null, 2))}>
                    Download JSON
                  </button>
                </div>
              </div>

              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Asset</th>
                      <th>Source</th>
                      <th className="num">Size</th>
                      <th>Recommendation</th>
                      <th>Justification &amp; duplicate copies</th>
                      <th>Local reviewer note</th>
                    </tr>
                  </thead>
                  <tbody>
                    {r.rows.map((x) => (
                      <tr key={x.asset_id}>
                        <td>
                          <Link to={x.kind === "video" ? `/recording/${x.asset_id}` : `/document/${x.asset_id}`}>{x.filename}</Link>
                          <div className="muted small">{KIND_LABEL[x.kind]} · <code>{x.asset_id}</code></div>
                        </td>
                        <td><SourceBadge source={x.source_system} /></td>
                        <td className="num">{formatBytes(x.bytes)}</td>
                        <td>
                          {x.recommendation === "eligible_after_approval" ? (
                            <Badge tone="amber">Eligible after approval</Badge>
                          ) : (
                            <Badge tone="green">Keep</Badge>
                          )}
                        </td>
                        <td>
                          <div>{x.reason}</div>
                          {x.duplicates_elsewhere.length > 0 && (
                            <ul className="elsewhere-list">
                              {x.duplicates_elsewhere.map((d) => (
                                <li key={d.asset_id}>
                                  Confirmed copy: <b>{d.filename}</b> on {SOURCE_LABEL[d.source_system]} (owner {d.owner})
                                </li>
                              ))}
                            </ul>
                          )}
                        </td>
                        <td>
                          {x.recommendation === "eligible_after_approval" ? (
                            <label className="check-inline small">
                              <input type="checkbox" checked={!!approver[x.asset_id]} onChange={(e) => setApprover((p) => ({ ...p, [x.asset_id]: e.target.checked }))} />
                              {approver[x.asset_id] ? "Flagged (tab only)" : "Flag"}
                            </label>
                          ) : (
                            <span className="muted">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      ) : null}
    </section>
  );
}
