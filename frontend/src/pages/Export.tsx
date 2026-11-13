import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { ExportChunk } from "@contracts/ts/dso-contracts";
import { api } from "../api/client";
import { USE_MOCKS, absUrl } from "../api/config";
import { useAsync } from "../lib/useAsync";
import { downloadText, formatTime } from "../lib/format";
import { AssetPicker } from "../components/AssetPicker";
import { Badge, Callout, Empty, ErrorBox, Loading, PageHeader, SourceBadge } from "../components/ui";

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

export default function Export() {
  const [tab, setTab] = useState<"jsonl" | "asset">("jsonl");
  const assets = useAsync(() => api.listAssets(), []);
  const ready = (assets.data?.assets ?? []).filter((a) => a.status === "ready");
  const [assetId, setAssetId] = useState<string | undefined>();
  const id = assetId ?? ready.find((a) => a.kind === "document")?.id ?? ready[0]?.id;

  const jsonl = useAsync(() => api.exportJsonl(), [], tab === "jsonl");
  const one = useAsync(() => api.exportAsset(id!), [id], tab === "asset" && !!id);
  const parsed = useMemo(() => parseJsonl(jsonl.data ?? ""), [jsonl.data]);

  return (
    <section>
      <PageHeader
        title="AI-ready export"
        lead="Clean text chunks with timestamps or page numbers, and a source link back to the original file (kept). Ready for search, RAG or fine-tuning pipelines."
      />
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === "jsonl"} className={`tab ${tab === "jsonl" ? "on" : ""}`} onClick={() => setTab("jsonl")}>
          All chunks · JSONL
        </button>
        <button role="tab" aria-selected={tab === "asset"} className={`tab ${tab === "asset" ? "on" : ""}`} onClick={() => setTab("asset")}>
          One file · JSON
        </button>
      </div>

      {tab === "jsonl" ? (
        jsonl.loading ? (
          <Loading label="Building export…" />
        ) : jsonl.error ? (
          <ErrorBox error={jsonl.error} onRetry={jsonl.reload} />
        ) : parsed.chunks.length === 0 ? (
          <Empty>No chunks yet. Process a recording or a document first.</Empty>
        ) : (
          <>
            <div className="card">
              <div className="card-head">
                <h3>
                  {parsed.chunks.length} chunks{" "}
                  <span className="muted small">
                    · one JSON object per line ({`GET /api/export.jsonl`}){parsed.bad > 0 && ` · ${parsed.bad} unreadable lines`}
                  </span>
                </h3>
                <button className="btn primary small" onClick={() => downloadText("dso-export.jsonl", jsonl.data!, "application/x-ndjson")}>
                  Download export.jsonl
                </button>
              </div>
              {USE_MOCKS && <Callout tone="info">Mock mode: this is the fixture file <code>contracts/fixtures/export.jsonl</code>, unchanged.</Callout>}
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>chunk_id</th>
                      <th>Kind</th>
                      <th>Text</th>
                      <th>Where</th>
                      <th>Source (provenance)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {parsed.chunks.map((c) => (
                      <tr key={c.chunk_id}>
                        <td>
                          <code>{c.chunk_id}</code>
                        </td>
                        <td>
                          <Badge tone={c.kind === "transcript_segment" ? "blue" : "purple"}>{c.kind}</Badge>
                        </td>
                        <td className="reason">{c.text}</td>
                        <td>
                          <Link to={sourceLink(c)}>
                            {c.kind === "transcript_segment" ? `${formatTime(c.start)}–${formatTime(c.end)}` : `page ${c.page}`}
                          </Link>
                        </td>
                        <td>
                          <div>
                            {USE_MOCKS ? (
                              <span title={`${c.source.original_url} (served by the backend in live mode)`}>{c.source.filename}</span>
                            ) : (
                              <a href={absUrl(c.source.original_url)} target="_blank" rel="noreferrer" title="Original file (kept, read-only)">
                                {c.source.filename}
                              </a>
                            )}
                          </div>
                          <SourceBadge source={c.source.source_system} />
                          <div className="muted small">
                            sha256 <code>{c.source.sha256.slice(0, 10)}…</code>
                            {c.metadata.doc_number && ` · ${c.metadata.doc_number}`}
                            {c.metadata.revision && ` rev ${c.metadata.revision}`}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <details className="card">
              <summary>Raw JSONL (first 3 lines)</summary>
              <pre className="code">{jsonl.data!
                .split("\n")
                .filter((l) => l.trim())
                .slice(0, 3)
                .map((l) => {
                  try {
                    return JSON.stringify(JSON.parse(l), null, 2);
                  } catch {
                    return l;
                  }
                })
                .join("\n\n")}</pre>
            </details>
          </>
        )
      ) : (
        <>
          <div className="card">
            {assets.data && <AssetPicker assets={ready} kind="any" value={id} label="Processed file" onChange={setAssetId} />}
          </div>
          {assets.error ? (
            <ErrorBox error={assets.error} onRetry={assets.reload} />
          ) : assets.loading ? (
            <Loading />
          ) : !id ? (
            <Empty>No processed files yet.</Empty>
          ) : one.loading ? (
            <Loading label="Building export…" />
          ) : one.error ? (
            <ErrorBox error={one.error} onRetry={one.reload} />
          ) : one.data ? (
            <div className="card">
              <div className="card-head">
                <h3>
                  {one.data.source.filename}{" "}
                  <span className="muted small">
                    · {one.data.chunks.length} chunks · {one.data.frames.length} frames · {one.data.slides.length} slides · {one.data.matches.length} matches
                  </span>
                </h3>
                <button
                  className="btn primary small"
                  onClick={() => downloadText(`${one.data!.source.asset_id}.export.json`, JSON.stringify(one.data, null, 2))}
                >
                  Download JSON
                </button>
              </div>
              <pre className="code tall">{JSON.stringify(one.data, null, 2)}</pre>
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
