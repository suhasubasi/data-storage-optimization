import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { Link } from "react-router-dom";
import type { Asset, Job, SourceSystem } from "@contracts/ts/dso-contracts";
import { api } from "../api/client";
import { useAsync } from "../lib/useAsync";
import { formatBytes, formatDate, KIND_LABEL, SOURCE_LABEL, shortHash } from "../lib/format";
import { Badge, Callout, Empty, ErrorBox, Loading, PageHeader, SourceBadge } from "../components/ui";

const STATUS_TONE = { uploaded: "grey", queued: "amber", processing: "amber", ready: "green", failed: "red" } as const;

function viewLink(a: Asset) {
  return a.kind === "video" ? `/recording/${a.id}` : `/document/${a.id}`;
}

function JobProgress({ job }: { job: Job }) {
  const pct = Math.round(job.progress * 100);
  const tone = job.status === "failed" ? "red" : job.status === "done" ? "green" : "amber";
  return (
    <div className="job">
      <div className="job-head">
        <span>
          Job <code>{job.id}</code> for <code>{job.asset_id}</code>
        </span>
        <Badge tone={tone}>{job.status}</Badge>
      </div>
      <div className="progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className={`progress-bar ${tone}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="job-foot muted">
        {pct}% · {job.stage ?? "—"}
        {job.error && <span className="err-text"> · {job.error}</span>}
      </div>
    </div>
  );
}

export default function Library() {
  const assets = useAsync(() => api.listAssets(), []);
  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState<SourceSystem>("sharepoint");
  const [owner, setOwner] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<Error | null>(null);
  const [lastUpload, setLastUpload] = useState<Asset | null>(null);
  const [jobs, setJobs] = useState<Record<string, Job>>({});
  const [drag, setDrag] = useState(false);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  // Poll running jobs (real job endpoint; progress comes from the pipeline, never simulated).
  const running = Object.values(jobs).filter((j) => j.status === "queued" || j.status === "running");
  useEffect(() => {
    if (!running.length) return;
    const t = setInterval(async () => {
      const updates = await Promise.all(running.map((j) => api.getJob(j.id).catch(() => j)));
      setJobs((prev) => {
        const next = { ...prev };
        for (const u of updates) next[u.asset_id] = u;
        return next;
      });
      assets.reload(); // keep the status column in step with the job
    }, 1000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running.map((j) => j.id).join(",")]);

  async function upload(e: FormEvent) {
    e.preventDefault();
    if (!file) return setFormError(new Error("Choose an .mp4, .pdf or .pptx file first."));
    if (!owner.trim()) return setFormError(new Error("Owner is required (who owns this file?)."));
    setBusy(true);
    setFormError(null);
    try {
      const a = await api.uploadAsset(file, source, owner.trim());
      setLastUpload(a);
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
      assets.reload();
    } catch (err) {
      setFormError(err as Error);
    } finally {
      setBusy(false);
    }
  }

  async function process(a: Asset) {
    try {
      const j = await api.processAsset(a.id);
      setJobs((p) => ({ ...p, [a.id]: j }));
      assets.reload();
    } catch (err) {
      setFormError(err as Error);
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDrag(false);
    const f = e.dataTransfer.files?.[0];
    if (f) setFile(f);
  }

  const list = assets.data?.assets ?? [];
  const realList = list.filter((a) => !a.test_data);
  const testList = list.filter((a) => a.test_data);
  const totalOrig = realList.reduce((s, a) => s + a.bytes, 0);
  const totalDerived = realList.reduce((s, a) => s + a.derived_bytes, 0);

  return (
    <section>
      <PageHeader
        title="Library & ingest"
        lead="Upload a recording (.mp4) or a document (.pdf or PowerPoint .pptx) with a simulated source label and owner, then start processing. The original is kept untouched."
      />

      <div className="grid-2">
        <form className="card" onSubmit={upload}>
          <h3>1 · Upload a file</h3>
          <div
            className={`dropzone ${drag ? "drag" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={onDrop}
          >
            <input
              ref={fileInput}
              id="file"
              type="file"
              accept=".mp4,.pdf,.pptx,video/mp4,application/pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <label htmlFor="file">
              {file ? (
                <>
                  <strong>{file.name}</strong> · {formatBytes(file.size)}
                </>
              ) : (
                <>Drop a file here or <u>browse</u> (.mp4, .pdf or .pptx)</>
              )}
            </label>
          </div>
          <div className="row">
            <label className="field">
              <span>Source system (simulated)</span>
              <select value={source} onChange={(e) => setSource(e.target.value as SourceSystem)}>
                {(Object.keys(SOURCE_LABEL) as SourceSystem[]).map((s) => (
                  <option key={s} value={s}>
                    {SOURCE_LABEL[s]}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Owner</span>
              <input value={owner} onChange={(e) => setOwner(e.target.value)} placeholder="e.g. the person or team that owns the file" />
            </label>
          </div>
          <button className="btn primary" disabled={busy}>
            {busy ? "Uploading and hashing…" : "Upload (computes SHA-256)"}
          </button>
          {formError && <ErrorBox error={formError} />}
          {lastUpload && (
            <Callout tone="safe" title="Uploaded.">
              <code>{lastUpload.id}</code> {lastUpload.filename} · SHA-256 <code>{shortHash(lastUpload.sha256, 16)}</code>.
              Uploading the same bytes twice on purpose creates two assets, to simulate copies across systems.{" "}
              <button type="button" className="btn small" onClick={() => process(lastUpload)}>
                2 · Start processing
              </button>
            </Callout>
          )}
        </form>

        <div className="card">
          <h3>Processing jobs</h3>
          {Object.values(jobs).length === 0 ? (
            <Empty>No job started in this session. Press <b>Process</b> on a file with status "uploaded".</Empty>
          ) : (
            Object.values(jobs)
              .reverse()
              .map((j) => <JobProgress key={j.id} job={j} />)
          )}
          <p className="muted small">
            Processing creates derived files (transcript, key frames, page images, hashes). This <b>adds</b> bytes. It frees
            nothing by itself; see the Storage report.
          </p>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <h3>All files</h3>
          <span className="muted">
            {realList.length} real file{realList.length === 1 ? "" : "s"} · originals {formatBytes(totalOrig)} · derived (added) {formatBytes(totalDerived)}
            {testList.length > 0 && (
              <>
                {" "}
                · plus {testList.length} generated test files ({formatBytes(testList.reduce((s, a) => s + a.bytes + a.derived_bytes, 0))}, not in the totals)
              </>
            )}
          </span>
        </div>
        {assets.loading && !assets.data ? (
          <Loading />
        ) : assets.error ? (
          <ErrorBox error={assets.error} onRetry={assets.reload} />
        ) : list.length === 0 ? (
          <Empty>No files yet. Upload one above.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>File</th>
                  <th>Type</th>
                  <th>Source</th>
                  <th>Owner</th>
                  <th>Status</th>
                  <th className="num">Original</th>
                  <th className="num">Derived (added)</th>
                  <th>SHA-256</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {list.map((a) => (
                  <tr key={a.id}>
                    <td>
                      {a.status === "ready" ? <Link to={viewLink(a)}>{a.filename}</Link> : a.filename}
                      <div className="muted small">
                        {a.id} · {formatDate(a.created_at)}{" "}
                        {a.test_data && (
                          <Badge tone="amber" title="Generated test file (synthetic sample). Kept on disk; left out of the default storage report.">
                            test file
                          </Badge>
                        )}
                      </div>
                    </td>
                    <td>{KIND_LABEL[a.kind]}</td>
                    <td>
                      <SourceBadge source={a.source_system} />
                    </td>
                    <td>{a.owner}</td>
                    <td>
                      <Badge tone={STATUS_TONE[a.status]}>{a.status}</Badge>
                    </td>
                    <td className="num">{formatBytes(a.bytes)}</td>
                    <td className="num">{a.derived_bytes ? `+${formatBytes(a.derived_bytes)}` : "—"}</td>
                    <td>
                      <code title={a.sha256}>{shortHash(a.sha256, 10)}</code>
                    </td>
                    <td>
                      <div className="actions">
                      {(a.status === "uploaded" || a.status === "failed") && (
                        <button className="btn small" onClick={() => process(a)}>
                          Process
                        </button>
                      )}
                      {a.status === "ready" && confirmId !== a.id && (
                        <button className="btn small" onClick={() => setConfirmId(a.id)}>
                          Re-process…
                        </button>
                      )}
                      {a.status === "ready" && (
                        <Link className="btn small ghost" to={viewLink(a)}>
                          Open
                        </Link>
                      )}
                      </div>
                      {a.status === "ready" && confirmId === a.id && (
                        <div className="confirm-box" role="alertdialog" aria-label={`Re-process ${a.filename}?`}>
                          <p className="small">
                            Re-process <b>{a.filename}</b>? This runs the whole pipeline again
                            {a.kind === "video" ? " (speech-to-text included: a long recording can take many minutes)" : ""}. The
                            current transcript, frames and pages stay in place and keep being served until the new run succeeds; if
                            it fails, nothing is replaced. The original file is never touched.
                          </p>
                          <div className="actions">
                            <button
                              className="btn small primary"
                              onClick={() => {
                                setConfirmId(null);
                                process(a);
                              }}
                            >
                              Yes, re-process
                            </button>
                            <button className="btn small ghost" onClick={() => setConfirmId(null)}>
                              Cancel
                            </button>
                          </div>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
