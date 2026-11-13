import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type { OffboardingReview } from "@contracts/ts/dso-contracts";
import { api } from "../api/client";
import { useAsync } from "../lib/useAsync";
import { downloadText, formatBytes, formatDate, KIND_LABEL, SOURCE_LABEL } from "../lib/format";
import { Badge, Callout, Empty, ErrorBox, Loading, PageHeader, SourceBadge, Stat } from "../components/ui";

function toCsv(r: OffboardingReview) {
  const q = (v: string | number) => `"${String(v).replace(/"/g, '""')}"`;
  const head = ["asset_id", "filename", "kind", "bytes", "source_system", "recommendation", "reason", "duplicates_elsewhere"];
  const rows = r.rows.map((x) =>
    [x.asset_id, x.filename, x.kind, x.bytes, x.source_system, x.recommendation, x.reason, x.duplicates_elsewhere.map((d) => `${d.filename} (${d.source_system}, ${d.owner})`).join("; ")].map(q).join(","),
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
    <section>
      <PageHeader
        title="Offboarding review"
        lead="When someone leaves, check each of their files: is there a confirmed exact copy owned by someone else? This screen only recommends."
      />
      <Callout tone="safe" title="Nothing is deleted.">
        There is no delete button and no delete endpoint. “Eligible after approval” means a person may decide to remove it later through an approved
        process. Shared or similar slides never make a file eligible.
      </Callout>

      <div className="card">
        <label className="field inline">
          <span>Leaving employee (owner)</span>
          <select value={owner} onChange={(e) => setParams(e.target.value ? { owner: e.target.value } : {})}>
            <option value="">Choose an owner…</option>
            {owners.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        </label>
      </div>

      {assets.error && <ErrorBox error={assets.error} onRetry={assets.reload} />}
      {!owner ? (
        <Empty>Pick an owner to see the review. (Demo tip: “carl” owns a copy of a deck that also lives on SharePoint.)</Empty>
      ) : review.loading ? (
        <Loading label={`Reviewing files owned by ${owner}…`} />
      ) : review.error ? (
        <ErrorBox error={review.error} onRetry={review.reload} />
      ) : r ? (
        <>
          <div className="stats-row">
            <Stat label="Files owned" value={r.summary.total} />
            <Stat label="Eligible after approval" value={r.summary.eligible} sub={`${formatBytes(r.summary.eligible_bytes)} could be freed later`} />
            <Stat label="Keep" value={r.summary.keep} />
            <Stat label="Deletes performed" value={<span className="safe-val">{String(r.deletes_performed)}</span>} sub={`generated ${formatDate(r.generated_at)}`} />
          </div>
          {r.rows.length === 0 ? (
            <Empty>{owner} owns no files in the library.</Empty>
          ) : (
            <div className="card">
              <div className="card-head">
                <h3>Files owned by {r.owner}</h3>
                <div className="row-actions">
                  <button className="btn small" onClick={() => downloadText(`offboarding-${r.owner}.csv`, toCsv(r), "text/csv")}>
                    Download review (CSV) for the approver
                  </button>
                  <button className="btn small ghost" onClick={() => downloadText(`offboarding-${r.owner}.json`, JSON.stringify(r, null, 2))}>
                    JSON
                  </button>
                </div>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>File</th>
                      <th>Source</th>
                      <th className="num">Size</th>
                      <th>Recommendation</th>
                      <th>Why</th>
                      <th>Flag for approver</th>
                    </tr>
                  </thead>
                  <tbody>
                    {r.rows.map((x) => (
                      <tr key={x.asset_id}>
                        <td>
                          <Link to={x.kind === "video" ? `/recording/${x.asset_id}` : `/document/${x.asset_id}`}>{x.filename}</Link>
                          <div className="muted small">
                            {KIND_LABEL[x.kind]} · {x.asset_id}
                          </div>
                        </td>
                        <td>
                          <SourceBadge source={x.source_system} />
                        </td>
                        <td className="num">{formatBytes(x.bytes)}</td>
                        <td>
                          {x.recommendation === "eligible_after_approval" ? (
                            <Badge tone="amber">Eligible for deletion after approval</Badge>
                          ) : (
                            <Badge tone="green">Keep</Badge>
                          )}
                        </td>
                        <td className="reason">
                          {x.reason}
                          {x.duplicates_elsewhere.length > 0 && (
                            <ul className="elsewhere">
                              {x.duplicates_elsewhere.map((d) => (
                                <li key={d.asset_id}>
                                  Copy: <b>{d.filename}</b> on {SOURCE_LABEL[d.source_system]} (owner {d.owner})
                                </li>
                              ))}
                            </ul>
                          )}
                        </td>
                        <td>
                          {x.recommendation === "eligible_after_approval" ? (
                            <label className="check">
                              <input type="checkbox" checked={!!approver[x.asset_id]} onChange={(e) => setApprover((p) => ({ ...p, [x.asset_id]: e.target.checked }))} />
                              {approver[x.asset_id] ? "flagged (local note only)" : "flag"}
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
              <p className="muted small">Flags are only a note in this browser tab. They do not change or delete any file.</p>
            </div>
          )}
        </>
      ) : null}
    </section>
  );
}
