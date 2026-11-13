// Mock implementation of the Api interface, built ONLY from contracts/fixtures (incl. manifests).
// Where a fixture exists for an exact response we return it unchanged; for other assets we derive
// the same shape from the fixture manifests. Uploads + job progress are SIMULATED and labelled so in the UI.
import type {
  Asset, AssetDetail, Job, SlideList, SlideView, SlideMatch, SearchHit, ExportAsset, ExportChunk,
  ExportMatch, OffboardingReview, OffboardingRow, Timeline, Manifest, AssetKind, DuplicateGroup,
} from "@contracts/ts/dso-contracts";
import type { Api } from "../api/types";
import { ApiError } from "../api/errors";
import { mocks } from "./index";

const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;
const delay = <T,>(v: T, ms = 250): Promise<T> => new Promise((r) => setTimeout(() => r(clone(v)), ms));
const notFound = (what: string) => new ApiError("not_found", `${what} was not found.`, 404);

// ---- in-memory state (lost on reload, on purpose) -------------------------------------------
const assets: Asset[] = clone(mocks.assets.assets);
interface MockJob { job: Job; startedMs: number; durationMs: number; kind: AssetKind }
const jobs = new Map<string, MockJob>();
const latestJobByAsset = new Map<string, string>([["a_01", mocks.job.id]]);
jobs.set(mocks.job.id, { job: clone(mocks.job), startedMs: 0, durationMs: 0, kind: "video" });
let nextAsset = assets.length + 1;
let nextJob = 3;

const STAGES: Record<AssetKind, string[]> = {
  video: ["extracting audio", "transcribing", "extracting key frames", "hashing frames", "writing manifest"],
  document: ["splitting pages", "extracting text", "rendering pages", "hashing pages", "writing manifest"],
};

function findAsset(id: string): Asset {
  const a = assets.find((x) => x.id === id);
  if (!a) throw notFound(`Asset ${id}`);
  return a;
}

function tickJob(id: string): Job {
  const mj = jobs.get(id);
  if (!mj) throw notFound(`Job ${id}`);
  if (mj.job.status === "done" || mj.job.status === "failed") return mj.job;
  const p = Math.min(1, (Date.now() - mj.startedMs) / mj.durationMs);
  const stages = STAGES[mj.kind];
  const asset = findAsset(mj.job.asset_id);
  if (p >= 1) {
    mj.job = { ...mj.job, status: "done", progress: 1, stage: "done", finished_at: new Date().toISOString() };
    asset.status = "ready";
  } else {
    mj.job = {
      ...mj.job,
      status: p < 0.05 ? "queued" : "running",
      progress: Math.round(p * 100) / 100,
      stage: p < 0.05 ? "queued" : stages[Math.min(stages.length - 1, Math.floor(p * stages.length))],
    };
    asset.status = p < 0.05 ? "queued" : "processing";
  }
  return mj.job;
}

async function sha256Hex(file: File): Promise<string> {
  if (file.size > 300_000_000 || !globalThis.crypto?.subtle) return "0".repeat(64);
  const buf = await file.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

// ---- helpers derived from fixtures -------------------------------------------------------------
const groups = (): DuplicateGroup[] => mocks.duplicates.groups;

function slideMatchesFor(assetId: string, slideId: string): SlideMatch[] {
  const out: SlideMatch[] = [];
  for (const g of groups()) {
    if (g.type === "exact_file") continue;
    const me = g.members.find((m) => m.asset_id === assetId && m.slide_id === slideId);
    if (!me) continue;
    for (const o of g.members) {
      if (o === me || o.slide_id === null || o.page === null) continue;
      out.push({
        type: g.type === "shared_slide" ? "shared" : "similar",
        other_asset_id: o.asset_id,
        other_slide_id: o.slide_id,
        other_filename: o.filename,
        other_page: o.page,
        other_source_system: o.source_system,
        score: g.score,
        method: g.evidence.method,
      });
    }
  }
  return out;
}

const derivedUrl = (assetId: string, path: string) => `/files/derived/${assetId}/${path}`;

function slidesFromManifest(m: Manifest): SlideView[] {
  return m.slides.map((s) => ({
    id: s.id,
    page: s.page,
    text: s.text,
    hashes: { file_sha256: m.original.sha256, text_sha256: s.text_sha256, phash: s.phash },
    image_url: derivedUrl(m.asset_id, s.path),
    bytes: s.bytes,
    matches: slideMatchesFor(m.asset_id, s.id),
  }));
}

function escapeRe(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Client-side stand-in for FTS5: AND of terms, prefix match, case-insensitive. */
function mockSearch(q: string, limit: number): SearchHit[] {
  const terms = q.toLowerCase().split(/\s+/).map((t) => t.replace(/[^\p{L}\p{N}%-]/gu, "")).filter(Boolean);
  if (!terms.length) return [];
  const re = new RegExp(`(${terms.map((t) => `\\b${escapeRe(t)}[\\p{L}\\p{N}]*`).join("|")})`, "giu");
  const matchesAll = (text: string) => terms.every((t) => new RegExp(`\\b${escapeRe(t)}`, "iu").test(text));
  const mark = (text: string) => text.replace(re, "<mark>$1</mark>");
  const score = (text: string) => (text.match(re)?.length ?? 0) + 1 / (1 + text.length / 100);
  const hits: SearchHit[] = [];
  for (const a of assets) {
    const m = mocks.manifests[a.id];
    if (!m || a.status !== "ready") continue;
    for (const s of m.segments) {
      if (!matchesAll(s.text)) continue;
      const f = m.frames.find((x) => x.id === s.frame_id) ?? null;
      hits.push({
        hit_type: "segment", asset_id: a.id, filename: a.filename, kind: a.kind, source_system: a.source_system,
        owner: a.owner, text: s.text, snippet: mark(s.text), start: s.start, end: s.end, page: null, item_id: s.id,
        frame_id: s.frame_id,
        media: f ? { type: "frame", asset_id: a.id, item_id: f.id, url: derivedUrl(a.id, f.path), bytes: f.bytes, t_start: f.t_start, t_end: f.t_end, page: null } : null,
        score: Math.round(score(s.text) * 10) / 10,
      });
    }
    for (const s of m.slides) {
      if (!matchesAll(s.text)) continue;
      hits.push({
        hit_type: "slide", asset_id: a.id, filename: a.filename, kind: a.kind, source_system: a.source_system,
        owner: a.owner, text: s.text, snippet: mark(s.text), start: null, end: null, page: s.page, item_id: s.id,
        frame_id: null,
        media: { type: "slide", asset_id: a.id, item_id: s.id, url: derivedUrl(a.id, s.path), bytes: s.bytes, t_start: null, t_end: null, page: s.page },
        score: Math.round(score(s.text) * 10) / 10,
      });
    }
  }
  return hits.sort((x, y) => y.score - x.score).slice(0, limit);
}

function offboardingFor(owner: string): OffboardingReview {
  if (owner === mocks.offboarding.owner) return mocks.offboarding;
  const rows: OffboardingRow[] = assets
    .filter((a) => a.owner === owner)
    .map((a) => {
      const elsewhere = assets.filter((o) => o.id !== a.id && o.sha256 === a.sha256 && o.owner !== owner);
      const first = elsewhere[0];
      return {
        asset_id: a.id, filename: a.filename, kind: a.kind, bytes: a.bytes, source_system: a.source_system,
        recommendation: elsewhere.length ? "eligible_after_approval" : "keep",
        reason: first
          ? `Confirmed exact duplicate (same SHA-256) at ${first.source_system}: ${first.filename} (owner: ${first.owner})`
          : "No exact copy owned by someone else. Shared or similar slides do not count.",
        duplicates_elsewhere: elsewhere.map((o) => ({ asset_id: o.id, filename: o.filename, source_system: o.source_system, owner: o.owner })),
      };
    });
  const eligible = rows.filter((r) => r.recommendation === "eligible_after_approval");
  return {
    owner, generated_at: new Date().toISOString(), deletes_performed: false, rows,
    summary: { total: rows.length, eligible: eligible.length, keep: rows.length - eligible.length, eligible_bytes: eligible.reduce((s, r) => s + r.bytes, 0) },
  };
}

function exportFor(a: Asset): ExportAsset {
  if (a.id === mocks.exportAsset.source.asset_id) return mocks.exportAsset;
  const m = mocks.manifests[a.id];
  if (!m) throw new ApiError("not_found", `Asset ${a.id} has no processed data to export yet.`, 404);
  const source = { asset_id: a.id, filename: a.filename, sha256: a.sha256, source_system: a.source_system, source_simulated: true, owner: a.owner, original_url: a.original_url };
  const base = { schema_version: "1.0" as const, metadata: m.metadata, source, language: m.metadata.language };
  const chunks: ExportChunk[] = [
    ...m.segments.map((s) => {
      const f = m.frames.find((x) => x.id === s.frame_id);
      return { ...base, chunk_id: `${a.id}:${s.id}`, kind: "transcript_segment" as const, text: s.text, start: s.start, end: s.end, page: null, frame_id: s.frame_id, slide_id: null, image_url: f ? derivedUrl(a.id, f.path) : null };
    }),
    ...m.slides.map((s) => ({ ...base, chunk_id: `${a.id}:${s.id}`, kind: "slide_text" as const, text: s.text, start: null, end: null, page: s.page, frame_id: null, slide_id: s.id, image_url: derivedUrl(a.id, s.path) })),
  ];
  const matches: ExportMatch[] = [];
  for (const g of groups()) {
    const mine = g.members.filter((x) => x.asset_id === a.id);
    for (const me of mine) {
      for (const o of g.members) {
        if (o.asset_id === a.id) continue;
        const ref = (x: typeof o) => (x.slide_id ? `${x.asset_id}:${x.slide_id}` : x.asset_id);
        const [p, q] = [ref(me), ref(o)].sort();
        matches.push({ level: g.type === "exact_file" ? "file" : "slide", type: g.type === "exact_file" ? "exact" : g.type === "shared_slide" ? "shared" : "similar", a: p, b: q, score: g.score, method: g.evidence.method });
      }
    }
  }
  return {
    schema_version: "1.0", exported_at: new Date().toISOString(), source, kind: a.kind, metadata: m.metadata, pipeline: m.pipeline,
    chunks,
    frames: m.frames.map((f) => ({ id: f.id, t_start: f.t_start, t_end: f.t_end, image_url: derivedUrl(a.id, f.path), bytes: f.bytes, phash: f.phash, matched_slide: f.matched_slide })),
    slides: slidesFromManifest(m),
    matches,
  };
}

// ---- Api -----------------------------------------------------------------------------------------
export const mockApi: Api = {
  health: () => delay(mocks.health, 50),

  listAssets: async (owner) => {
    for (const [, id] of latestJobByAsset) tickJob(id);
    return delay({ assets: owner ? assets.filter((a) => a.owner === owner) : assets }, 150);
  },

  getAsset: async (id) => {
    const a = findAsset(id);
    const jobId = latestJobByAsset.get(id);
    const latest_job = jobId ? tickJob(jobId) : null;
    if (id === "a_01") return delay({ ...mocks.assetDetailVideo, latest_job });
    if (id === "a_02") return delay(mocks.assetDetailDocument);
    const m = mocks.manifests[id];
    let detail: AssetDetail = { asset: a, metadata: null, derived: null, pipeline: null, latest_job };
    if (m) {
      const byKind: Record<string, number> = {};
      for (const f of m.derived_files) byKind[f.kind] = (byKind[f.kind] ?? 0) + f.bytes;
      const filesTotal = m.derived_files.reduce((s, f) => s + f.bytes, 0);
      const manifest_bytes = Math.max(0, a.derived_bytes - filesTotal);
      byKind.manifest = manifest_bytes;
      detail = {
        ...detail, metadata: m.metadata, pipeline: m.pipeline,
        derived: { derived_bytes: a.derived_bytes, manifest_bytes, file_count: m.derived_files.length + 1, segment_count: m.segments.length, frame_count: m.frames.length, slide_count: m.slides.length, bytes_by_kind: byKind },
      };
    }
    return delay(detail);
  },

  uploadAsset: async (file, source_system, owner) => {
    const ext = file.name.toLowerCase().split(".").pop();
    const kind: AssetKind | null = ext === "mp4" ? "video" : ext === "pdf" ? "document" : null;
    if (!kind) throw new ApiError("unsupported_file_type", "Only .mp4 (recording) and .pdf (document) files are supported.", 415);
    if (!owner.trim()) throw new ApiError("validation_error", "Owner is required.", 422, { field: "owner" });
    const sha256 = await sha256Hex(file);
    const id = `a_${String(nextAsset++).padStart(2, "0")}`;
    const asset: Asset = {
      id, filename: file.name, kind, bytes: file.size, sha256, source_system, source_simulated: true, owner: owner.trim(),
      status: "uploaded", created_at: new Date().toISOString(), derived_bytes: 0, original_url: `/files/originals/${id}/${file.name}`,
    };
    assets.push(asset);
    return delay(asset, 400);
  },

  processAsset: async (id) => {
    const a = findAsset(id);
    const prev = latestJobByAsset.get(id);
    if (prev) {
      const st = tickJob(prev).status;
      if (st === "queued" || st === "running") throw new ApiError("conflict", `A job for ${id} is already running.`, 409);
    }
    const jid = `j_${String(nextJob++).padStart(2, "0")}`;
    const job: Job = { id: jid, asset_id: id, status: "queued", progress: 0, stage: "queued", error: null, started_at: new Date().toISOString(), finished_at: null };
    jobs.set(jid, { job, startedMs: Date.now(), durationMs: a.kind === "video" ? 12000 : 7000, kind: a.kind });
    latestJobByAsset.set(id, jid);
    a.status = "queued";
    return delay(job, 200);
  },

  getJob: async (jid) => delay(tickJob(jid), 100),

  getTimeline: async (id) => {
    const a = findAsset(id);
    if (id === mocks.timeline.asset_id) return delay(mocks.timeline);
    const m = mocks.manifests[id];
    const t: Timeline = {
      asset_id: id, language: m?.metadata.language ?? null, duration_seconds: m?.metadata.duration_seconds ?? null, original_url: a.original_url,
      segments: m?.segments ?? [],
      frames: (m?.frames ?? []).map((f) => ({ id: f.id, t_start: f.t_start, t_end: f.t_end, image_url: derivedUrl(id, f.path), bytes: f.bytes, phash: f.phash, matched_slide: f.matched_slide })),
    };
    return delay(t);
  },

  getSlides: async (id) => {
    findAsset(id);
    if (id === mocks.slides.asset_id) return delay(mocks.slides);
    const m = mocks.manifests[id];
    const list: SlideList = { asset_id: id, metadata: m?.metadata ?? null, slides: m ? slidesFromManifest(m) : [] };
    return delay(list);
  },

  search: async (q, limit = 20) => {
    if (!q.trim()) throw new ApiError("validation_error", "Type at least one word to search.", 422);
    const hits = mockSearch(q, limit);
    return delay({ query: q, total: hits.length, hits }, 200);
  },

  getDuplicates: async (type) => {
    const r = mocks.duplicates;
    return delay(type ? { ...r, groups: r.groups.filter((g) => g.type === type) } : r);
  },

  getStorageReport: (_includeTestData = false) => delay(mocks.storageReport, 300),

  getOffboarding: async (owner) => {
    if (!owner.trim()) throw new ApiError("validation_error", "Pick an owner.", 422);
    return delay(offboardingFor(owner.trim()));
  },

  exportAsset: async (id) => delay(exportFor(findAsset(id))),
  exportJsonl: () => delay(mocks.exportJsonl, 150),
};
