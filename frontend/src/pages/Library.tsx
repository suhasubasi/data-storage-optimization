import { useEffect, useMemo, useRef, useState, type DragEvent, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type { Asset, Job, SourceSystem } from "@contracts/ts/dso-contracts";
import { api } from "../api/client";
import { useAsync } from "../lib/useAsync";
import { formatBytes, formatDate, formatDuration, formatEta, KIND_LABEL, SOURCE_LABEL, shortHash } from "../lib/format";
import { Badge, Callout, Empty, ErrorBox, Loading, PageHeader, SourceBadge, StatCard } from "../components/ui";
import { IconDoc, IconPlay, IconUpload } from "../components/Icons";

const STATUS_TONE = { uploaded: "grey", queued: "amber", processing: "amber", ready: "green", failed: "red" } as const;

function viewLink(a: Asset) {
  return a.kind === "video" ? `/recording/${a.id}` : `/document/${a.id}`;
}

const STAGE_LABEL: Record<string, string> = {
  queued: "Waiting in queue",
  starting: "Initializing",
  "hashing original": "Computing SHA-256",
  probing: "Probing video stream",
  "extracting key frames": "Extracting key frames",
  "finding unique slides": "Deduplicating unique slides",
  "extracting audio": "Decoding audio track",
  transcribing: "Transcribing speech",
  "writing transcript": "Writing transcript & speakers",
  "rendering pages": "Rendering document pages",
  "reading slides": "Extracting slide text",
  "rendering slides": "Rendering slides",
  "saving slide images": "Compressing slide images",
  ingesting: "Indexing in SQLite + FTS5",
  done: "Complete",
};

function JobProgress({ job }: { job: Job }) {
  const pct = Math.floor(job.progress * 100);
  const tone = job.status === "failed" ? "red" : job.status === "done" ? "green" : "blue";
  const active = job.status === "queued" || job.status === "running";
  const stage = job.stage ? STAGE_LABEL[job.stage] ?? job.stage : "—";
  const stagePct = active && job.stage_progress != null ? Math.floor(job.stage_progress * 100) : null;
  const eta = active ? formatEta(job.eta_s) : null;

  return (
    <div className="job-card">
      <div className="job-head">
        <span className="small">
          Job <code>{job.id}</code> · asset <code>{job.asset_id}</code>
        </span>
        <Badge tone={job.status === "failed" ? "red" : job.status === "done" ? "green" : "amber"}>{job.status}</Badge>
      </div>
      <div className="job-metrics">
        <strong>{pct}%</strong>
        <span>
          {stage}
          {stagePct !== null && <span className="muted"> · step {stagePct}%</span>}
        </span>
      </div>
      <div className="progress-track" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className={`progress-fill fill-${tone}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="job-foot muted small">
        {job.status === "done" ? "Duration" : "Elapsed"} {formatDuration(job.elapsed_s)}
        {active && (eta ? <> · <b>{eta}</b></> : <> · measuring ETA…</>)}
        {job.error && <span className="err-inline"> · {job.error}</span>}
      </div>
    </div>
  );
}

type KindFilter = "all" | "video" | "document" | "pending";

export default function Library() {
  const [params, setParams] = useSearchParams();
  const assets = useAsync(() => api.listAssets(), []);
  const whisper = useAsync(() => api.getSettings(), []);

  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState<SourceSystem>("sharepoint");
  const [owner, setOwner] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<Error | null>(null);
  const [lastUpload, setLastUpload] = useState<Asset | null>(null);
  const [jobs, setJobs] = useState<Record<string, Job>>({});
  const [drag, setDrag] = useState(false);
  const [confirmId, setConfirmId] = useState<string | null>(null);

  const [kindFilter, setKindFilter] = useState<KindFilter>("all");
  const [tableQuery, setTableQuery] = useState("");
  const [showTestData, setShowTestData] = useState(true);

  const fileInput = useRef<HTMLInputElement>(null);
  const uploadCardRef = useRef<HTMLFormElement>(null);
  const intakeRef = useRef<HTMLDetailsElement>(null);

  useEffect(() => {
    if (params.get("upload") === "1") {
      if (intakeRef.current) intakeRef.current.open = true;
      uploadCardRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      setParams({}, { replace: true });
    }
  }, [params, setParams]);

  useEffect(() => {
    if (assets.data?.assets.length === 0 && intakeRef.current) intakeRef.current.open = true;
  }, [assets.data]);

  const busyIds = (assets.data?.assets ?? [])
    .filter((a) => a.status === "queued" || a.status === "processing")
    .map((a) => a.id)
    .join(",");

  useEffect(() => {
    if (!busyIds) return;
    for (const id of busyIds.split(",")) {
      if (jobs[id]) continue;
      api
        .getAsset(id)
        .then((d) => {
          const j = d.latest_job;
          if (j && (j.status === "queued" || j.status === "running")) setJobs((p) => (p[id] ? p : { ...p, [id]: j }));
        })
        .catch(() => undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busyIds]);

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
      assets.silentReload();
    }, 1000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running.map((j) => j.id).join(",")]);

  async function upload(e: FormEvent) {
    e.preventDefault();
    if (!file) return setFormError(new Error("Choose an .mp4, .pdf or .pptx file first."));
    if (!owner.trim()) return setFormError(new Error("Owner name is required."));
    setBusy(true);
    setFormError(null);
    try {
      const a = await api.uploadAsset(file, source, owner.trim());
      setLastUpload(a);
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
      assets.silentReload();
    } catch (err) {
      setFormError(err as Error);
    } finally {
      setBusy(false);
    }
  }

  async function process(a: Asset) {
    if (intakeRef.current) intakeRef.current.open = true;
    uploadCardRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    try {
      const j = await api.processAsset(a.id);
      setJobs((p) => ({ ...p, [a.id]: j }));
      assets.silentReload();
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

  const all = assets.data?.assets ?? [];
  const realList = useMemo(() => all.filter((a) => !a.test_data), [all]);
  const testList = useMemo(() => all.filter((a) => a.test_data), [all]);
  const totalOrig = realList.reduce((s, a) => s + a.bytes, 0);
  const totalDerived = realList.reduce((s, a) => s + a.derived_bytes, 0);
  const videoCount = realList.filter((a) => a.kind === "video").length;
  const docCount = realList.filter((a) => a.kind === "document").length;
  const visibleList = all.filter((a) => showTestData || !a.test_data);
  const pendingCount = visibleList.filter((a) => a.status === "uploaded" || a.status === "failed").length;
  const knownOwners = useMemo(() => Array.from(new Set(all.map((a) => a.owner))).sort(), [all]);

  const filteredList = useMemo(() => {
    const q = tableQuery.trim().toLowerCase();
    return all.filter((a) => {
      if (!showTestData && a.test_data) return false;
      if (kindFilter === "video" && a.kind !== "video") return false;
      if (kindFilter === "document" && a.kind !== "document") return false;
      if (kindFilter === "pending" && a.status !== "uploaded" && a.status !== "failed") return false;
      if (q && !a.filename.toLowerCase().includes(q) && !a.owner.toLowerCase().includes(q) && !a.id.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [all, showTestData, kindFilter, tableQuery]);

  return (
    <section className="page-stack page-library">
      <PageHeader
        title="Library & ingest"
        lead="Your recordings and documents, in one place. Upload, process, and turn files into searchable knowledge."
      />

      <div className="stats-grid-4">
        <StatCard label="Library assets" value={realList.length} sub={`${videoCount} recordings · ${docCount} documents`} tone="accent" />
        <StatCard label="Protected originals" value={formatBytes(totalOrig)} sub="Never touched or deleted" />
        <StatCard label="Extracted knowledge" value={`+${formatBytes(totalDerived)}`} sub="Transcripts, key frames, slide images" />
        <StatCard
          label="Ready to explore"
          value={realList.filter((a) => a.status === "ready").length}
          sub={`${realList.filter((a) => a.status !== "ready").length} files need processing or review`}
          tone="safe"
        />
      </div>

      <details ref={intakeRef} className="intake-disclosure">
        <summary>
          <span className="intake-summary-title"><IconUpload size={18} /> Add files &amp; processing</span>
          <span className="intake-summary-meta">{running.length ? `${running.length} job${running.length === 1 ? "" : "s"} running` : "MP4 · PDF · PowerPoint"}<span className="disclosure-indicator">+</span></span>
        </summary>
        <div className="split-2 library-intake">
        <form ref={uploadCardRef} className="card upload-card" onSubmit={upload}>
          <div className="card-head">
            <h3><span className="step-number">01</span> Add to your library</h3>
            <span className="muted small">Original file stays protected</span>
          </div>

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
              id="proto-file"
              type="file"
              accept=".mp4,.pdf,.pptx,video/mp4,application/pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <label htmlFor="proto-file">
              <IconUpload size={22} />
              {file ? (
                <span>
                  <strong>{file.name}</strong> · {formatBytes(file.size)}
                </span>
              ) : (
                <span>
                  <b>Drop a file to get started</b><span>or <u>browse files</u> from your computer</span><small>MP4 recordings · PDF documents · PowerPoint decks</small>
                </span>
              )}
            </label>
          </div>

          <div className="form-grid-2">
            <div className="field">
              <span>Simulated source system</span>
              <div className="segmented" role="group" aria-label="Source system">
                {(Object.keys(SOURCE_LABEL) as SourceSystem[]).map((s) => (
                  <button
                    key={s}
                    type="button"
                    className={`seg-btn ${source === s ? "on" : ""}`}
                    onClick={() => setSource(s)}
                  >
                    {SOURCE_LABEL[s]}
                  </button>
                ))}
              </div>
            </div>

            <label className="field">
              <span>Owner</span>
              <input
                list="known-owners"
                value={owner}
                onChange={(e) => setOwner(e.target.value)}
                placeholder="e.g. ericsson-team or carl"
              />
              <datalist id="known-owners">
                {knownOwners.map((o) => (
                  <option key={o} value={o} />
                ))}
              </datalist>
            </label>
          </div>

          <div className="row-actions">
            <button className="btn btn-primary" disabled={busy}>
              {busy ? "Uploading & hashing…" : "Upload asset"}
            </button>
            <span className="muted small">Duplicates by identical bytes are stored as separate source records.</span>
          </div>

          {formError && <ErrorBox error={formError} />}
          {lastUpload && (
            <Callout tone="safe" title="Uploaded successfully.">
              <code>{lastUpload.id}</code> <b>{lastUpload.filename}</b> · SHA-256 <code>{shortHash(lastUpload.sha256, 16)}</code>{" "}
              <button type="button" className="btn btn-primary btn-xs" onClick={() => process(lastUpload)}>
                2 · Start processing
              </button>
            </Callout>
          )}
        </form>

        <div className="card">
          <div className="card-head">
            <h3><span className="step-number">02</span> Processing activity</h3>
            {whisper.data && (
              <Link to="/settings" className="small">
                <code>{whisper.data.effective_model}</code> · <code>{whisper.data.effective_device}</code> ⚙
              </Link>
            )}
          </div>
          {Object.values(jobs).length === 0 ? (
            <Empty>
              No processing job started in this session. Select <b>Process</b> on any uploaded asset below to run extraction &amp; indexing.
            </Empty>
          ) : (
            <div className="job-list">
              {Object.values(jobs)
                .reverse()
                .map((j) => (
                  <JobProgress key={j.id} job={j} />
                ))}
            </div>
          )}
          <p className="muted small">
            Processing extracts text, unique slides, speaker labels, and hashes. It frees zero bytes by itself — review savings under Storage Optimizer.
          </p>
        </div>
      </div>
      </details>

      <div className="card library-table">
        <div className="card-head"><div><span className="section-eyebrow">EXPLORE YOUR CONTENT</span><h2>All files</h2></div><span className="muted small">Find, process, and inspect your assets</span></div>
        <div className="table-toolbar">
          <div className="pill-tabs" role="tablist" aria-label="Filter files">
            <button type="button" role="tab" aria-selected={kindFilter === "all"} className={`pill-tab ${kindFilter === "all" ? "on" : ""}`} onClick={() => setKindFilter("all")}>
              All ({all.filter((a) => showTestData || !a.test_data).length})
            </button>
            <button type="button" role="tab" aria-selected={kindFilter === "video"} className={`pill-tab ${kindFilter === "video" ? "on" : ""}`} onClick={() => setKindFilter("video")}>
              Recordings ({visibleList.filter((a) => a.kind === "video").length})
            </button>
            <button type="button" role="tab" aria-selected={kindFilter === "document"} className={`pill-tab ${kindFilter === "document" ? "on" : ""}`} onClick={() => setKindFilter("document")}>
              Documents ({visibleList.filter((a) => a.kind === "document").length})
            </button>
            <button type="button" role="tab" aria-selected={kindFilter === "pending"} className={`pill-tab ${kindFilter === "pending" ? "on" : ""}`} onClick={() => setKindFilter("pending")}>
              Needs processing ({pendingCount})
            </button>
          </div>

          <div className="toolbar-right">
            <label className="check-inline small">
              <input type="checkbox" checked={showTestData} onChange={(e) => setShowTestData(e.target.checked)} />
              Show test files ({testList.length})
            </label>
            <input
              type="search"
              className="input-compact"
              value={tableQuery}
              onChange={(e) => setTableQuery(e.target.value)}
              placeholder="Filter filename, owner, or ID…"
              aria-label="Filter assets table"
            />
          </div>
        </div>

        {assets.loading && !assets.data ? (
          <Loading label="Loading library…" />
        ) : assets.error ? (
          <ErrorBox error={assets.error} onRetry={assets.reload} />
        ) : filteredList.length === 0 ? (
          <Empty>No matching files in this view.</Empty>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Asset</th>
                  <th>Source</th>
                  <th>Owner</th>
                  <th>Status</th>
                  <th className="num">Original</th>
                  <th className="num">Derived</th>
                  <th className="actions-col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredList.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <div className="asset-cell">
                        <span className={`kind-dot kind-${a.kind}`}>{a.kind === "video" ? <IconPlay size={14} /> : <IconDoc size={14} />}</span>
                        <div>
                          <div className="asset-name">
                            {a.status === "ready" ? <Link to={viewLink(a)}>{a.filename}</Link> : a.filename}
                          </div>
                          <div className="muted small">
                            {KIND_LABEL[a.kind]}{" "}
                            {a.test_data && <Badge tone="amber">test file</Badge>}
                          </div>
                          <details className="asset-details">
                            <summary>File details</summary>
                            <dl><dt>Asset ID</dt><dd><code>{a.id}</code></dd><dt>Added</dt><dd>{formatDate(a.created_at)}</dd><dt>SHA-256</dt><dd><code>{a.sha256}</code></dd></dl>
                          </details>
                        </div>
                      </div>
                    </td>
                    <td><SourceBadge source={a.source_system} /></td>
                    <td>{a.owner}</td>
                    <td><Badge tone={STATUS_TONE[a.status]}>{a.status}</Badge></td>
                    <td className="num">{formatBytes(a.bytes)}</td>
                    <td className="num muted">{a.derived_bytes ? `+${formatBytes(a.derived_bytes)}` : "—"}</td>
                    <td className="actions-col">
                      <div className="row-actions">
                        {(a.status === "uploaded" || a.status === "failed") && (
                          <button type="button" className="btn btn-primary btn-xs" onClick={() => process(a)}>
                            {a.status === "failed" ? "Retry processing" : "Process"}
                          </button>
                        )}
                        {a.status === "ready" && (
                          <Link className="btn btn-secondary btn-xs" to={viewLink(a)}>
                            Open
                          </Link>
                        )}
                        {a.status === "ready" && confirmId !== a.id && (
                          <button type="button" className="btn btn-ghost btn-xs" onClick={() => setConfirmId(a.id)}>
                            Re-process…
                          </button>
                        )}
                      </div>
                      {a.status === "ready" && confirmId === a.id && (
                        <div className="confirm-inline" role="alertdialog" aria-label={`Re-process ${a.filename}?`}>
                          <p className="small">
                            Re-run pipeline on <b>{a.filename}</b>? Existing data stays live until replacement succeeds. Originals are untouched.
                          </p>
                          <div className="row-actions">
                            <button
                              type="button"
                              className="btn btn-primary btn-xs"
                              onClick={() => {
                                setConfirmId(null);
                                process(a);
                              }}
                            >
                              Confirm
                            </button>
                            <button type="button" className="btn btn-ghost btn-xs" onClick={() => setConfirmId(null)}>
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
