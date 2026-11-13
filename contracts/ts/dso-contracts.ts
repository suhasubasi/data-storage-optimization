/* GENERATED from contracts/schemas/*.json by contracts/scripts/generate.sh. DO NOT EDIT. FROZEN v1.0 */

/**
 * Backend-generated asset id, e.g. 'a_01' or 'a_7f3c9e21'.
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "AssetId".
 */
export type AssetId = string;
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "AssetKind".
 */
export type AssetKind = "video" | "document";
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "Sha256".
 */
export type Sha256 = string;
/**
 * Perceptual hash as lowercase hex. imagehash.phash(hash_size=8) => 16 hex chars (64 bits). See contracts/thresholds.json.
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "PHash".
 */
export type PHash = string;
/**
 * Id unique only inside one asset: segments 's<n>', frames 'f<n>', slides 'p<page>'. Globally an item is '<asset_id>:<local_id>' (see ItemRef in api.schema.json).
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "LocalId".
 */
export type LocalId = string;
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "DerivedFileKind".
 */
export type DerivedFileKind = "transcript" | "frame" | "page_image" | "page_text" | "audio" | "other";
/**
 * Global id of an item: '<asset_id>' for a whole file, or '<asset_id>:<local_id>' for a segment/frame/slide, e.g. 'a_02:p4'. Used in matches.a_id/b_id and export chunk ids.
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "ItemRef".
 */
export type ItemRef = string;
/**
 * Simulated source label (PDF p.1 names SharePoint, OneDrive, Ericsson Play). No live connectors in the MVP; source_simulated is always true.
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "SourceSystem".
 */
export type SourceSystem = "sharepoint" | "onedrive" | "ericsson_play";
/**
 * OUR RECOMMENDATION for the status values (Page only says 'status').
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "AssetStatus".
 */
export type AssetStatus = "uploaded" | "queued" | "processing" | "ready" | "failed";
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "JobStatus".
 */
export type JobStatus = "queued" | "running" | "done" | "failed";
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "ErrorCode".
 */
export type ErrorCode =
  "not_found" | "validation_error" | "unsupported_file_type" | "conflict" | "pipeline_failed" | "internal_error";
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "MediaType".
 */
export type MediaType = "frame" | "slide" | "original";
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "MatchType".
 */
export type MatchType = "exact" | "shared" | "similar";
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "MatchLevel".
 */
export type MatchLevel = "file" | "slide";
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "SlideMatchType".
 */
export type SlideMatchType = "shared" | "similar";
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "HitType".
 */
export type HitType = "segment" | "slide" | "asset" | "chat";
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "DuplicateType".
 */
export type DuplicateType = "exact_file" | "shared_slide" | "similar_slide";
/**
 * The four scenarios from the Page's savings section (0 = today/real, 1-3 = hypothetical after approval).
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "ScenarioKey".
 */
export type ScenarioKey = "today" | "replace_videos" | "remove_exact_duplicates" | "both";
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "RemovalReason".
 */
export type RemovalReason = "replaced_by_derived" | "exact_duplicate";
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "OffboardingRecommendation".
 */
export type OffboardingRecommendation = "eligible_after_approval" | "keep";
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "ChunkKind".
 */
export type ChunkKind = "transcript_segment" | "slide_text";
/**
 * REC v1.4: the Whisper models the user can pick in the UI. small = fast, large-v3-turbo = fast + accurate (needs an NVIDIA GPU to be fast), large-v3 = most accurate (slowest). 'medium' is deliberately not offered.
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "WhisperModelName".
 */
export type WhisperModelName = "small" | "large-v3-turbo" | "large-v3";
/**
 * REC v1.4: where Whisper runs. auto = NVIDIA GPU if one is usable, else CPU. cuda = GPU only (the job fails clearly if there is none). cpu = CPU only (the default).
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "WhisperDevice".
 */
export type WhisperDevice = "auto" | "cuda" | "cpu";

/**
 * GENERATED by contracts/scripts/bundle_schemas.py. Do not edit; edit schemas/*.json.
 */
export interface DsoContracts {
  AssetId?: AssetId;
  AssetKind?: AssetKind;
  Sha256?: Sha256;
  PHash?: PHash;
  LocalId?: LocalId;
  OriginalRef?: OriginalRef;
  AssetMetadata?: AssetMetadata;
  Segment?: Segment;
  Frame?: Frame;
  Slide?: Slide;
  DerivedFileKind?: DerivedFileKind;
  DerivedFile?: DerivedFile;
  PipelineInfo?: PipelineInfo;
  UniqueSlidesInfo?: UniqueSlidesInfo;
  Manifest?: Manifest;
  ItemRef?: ItemRef;
  SourceSystem?: SourceSystem;
  AssetStatus?: AssetStatus;
  JobStatus?: JobStatus;
  ErrorCode?: ErrorCode;
  ErrorResponse?: ErrorResponse;
  MediaRef?: MediaRef;
  Asset?: Asset;
  DerivedSummary?: DerivedSummary;
  AssetDetail?: AssetDetail;
  AssetList?: AssetList;
  Job?: Job;
  FrameView?: FrameView;
  Timeline?: Timeline;
  MatchType?: MatchType;
  MatchLevel?: MatchLevel;
  SlideMatch?: SlideMatch;
  HashRecord?: HashRecord;
  SlideView?: SlideView;
  SlideList?: SlideList;
  SearchHit?: SearchHit;
  SearchResponse?: SearchResponse;
  DuplicateType?: DuplicateType;
  DuplicateMember?: DuplicateMember;
  DuplicateEvidence?: DuplicateEvidence;
  DuplicateGroup?: DuplicateGroup;
  DuplicateReport?: DuplicateReport;
  ScenarioKey?: ScenarioKey;
  RemovedItem?: RemovedItem;
  StorageScenario?: StorageScenario;
  StorageTotals?: StorageTotals;
  StorageReport?: StorageReport;
  OffboardingRecommendation?: OffboardingRecommendation;
  DuplicateLocation?: DuplicateLocation;
  OffboardingRow?: OffboardingRow;
  OffboardingReview?: OffboardingReview;
  Provenance?: Provenance;
  ExportChunk?: ExportChunk;
  ExportMatch?: ExportMatch;
  ExportAsset?: ExportAsset;
  Health?: Health;
  MediaType?: MediaType;
  SlideMatchType?: SlideMatchType;
  HitType?: HitType;
  RemovalReason?: RemovalReason;
  ChunkKind?: ChunkKind;
  ChatMessage?: ChatMessage;
  ChatSource?: ChatSource;
  ChatAlignment?: ChatAlignment;
  ChatLog?: ChatLog;
  WhisperModelName?: WhisperModelName;
  WhisperDevice?: WhisperDevice;
  WhisperModelInfo?: WhisperModelInfo;
  SettingsUpdate?: SettingsUpdate;
  Settings?: Settings;
}
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "OriginalRef".
 */
export interface OriginalRef {
  /**
   * Relative to the data/ directory, e.g. 'originals/a_01/deck.pdf'. Read-only.
   */
  path: string;
  bytes: number;
  sha256: Sha256;
}
/**
 * Only fill what is really present in the file / file name. Never invent doc numbers or revisions (PDF p.3: metadata not guaranteed).
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "AssetMetadata".
 */
export interface AssetMetadata {
  title: string | null;
  author: string | null;
  doc_number: string | null;
  revision: string | null;
  /**
   * As found in the source (PDF metadata or text). ISO 8601 if parseable, else raw string.
   */
  date: string | null;
  /**
   * Detected language code for videos (faster-whisper), e.g. 'en', 'sv'. null for documents unless detected.
   */
  language: string | null;
  /**
   * OUR RECOMMENDATION (not on the Page): video length. Optional.
   */
  duration_seconds?: number | null;
}
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "Segment".
 */
export interface Segment {
  id: LocalId;
  /**
   * Seconds from video start.
   */
  start: number;
  end: number;
  text: string;
  /**
   * The kept frame on screen when this segment STARTS (frame.t_start <= start < frame.t_end).
   */
  frame_id: string | null;
  /**
   * Always null in the MVP (speaker ID is out of scope).
   */
  speaker: string | null;
}
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "Frame".
 */
export interface Frame {
  id: LocalId;
  t_start: number;
  /**
   * Time of the next kept frame, or video end. Covers [t_start, t_end).
   */
  t_end: number;
  /**
   * e.g. 'frames/f3.webp'. WebP, max 1280 px wide.
   */
  path: string;
  bytes: number;
  phash: PHash;
  /**
   * STRETCH (levels 3-4). Global slide ref '<asset_id>:p<page>' or null. Always null in P0.
   */
  matched_slide: string | null;
  /**
   * REC v1.1 (unique-slide pass): 1-based number of the unique slide shown in this time range. Several ranges can show the same slide (the talk went back to it); they then share one image file. Absent on manifests made before the pass.
   */
  slide?: number;
  /**
   * REC v1.1: ids of the originally extracted key frames merged into this time range (audit trail). The first one is this frame's id.
   *
   * @minItems 1
   */
  source_frames?: [LocalId, ...LocalId[]];
}
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "Slide".
 */
export interface Slide {
  id: LocalId;
  /**
   * 1-based page number.
   */
  page: number;
  text: string;
  /**
   * SHA-256 of the NORMALISED page text (rule in CONTRACTS.md: NFKC, lowercase, collapse whitespace, strip). The file SHA-256 is original.sha256; together with phash these are the three hashes.
   */
  text_sha256: string;
  phash: PHash;
  /**
   * e.g. 'pages/p4.webp'.
   */
  path: string;
  bytes: number;
}
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "DerivedFile".
 */
export interface DerivedFile {
  path: string;
  bytes: number;
  kind: DerivedFileKind;
}
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "PipelineInfo".
 */
export interface PipelineInfo {
  version: string;
  /**
   * e.g. 'faster-whisper small int8'; null for documents.
   */
  model: string | null;
  /**
   * pHash distance used to keep a new frame; null for documents.
   */
  frame_threshold: number | null;
  /**
   * Wall-clock processing time.
   */
  seconds: number;
  /**
   * OUR RECOMMENDATION (not on the Page): non-fatal issues, e.g. 'no text layer on page 3'. Optional.
   */
  warnings?: string[];
  /**
   * REC v1.1: unique-slide pass result (videos); absent or null if it has not run.
   */
  unique_slides?: UniqueSlidesInfo | null;
}
/**
 * REC v1.1: result of the unique-slide pass (one image per unique slide; near-identical repeats removed). Video only.
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "UniqueSlidesInfo".
 */
export interface UniqueSlidesInfo {
  method: string;
  /**
   * 'pipeline' = during processing; 'post_pass' = later, on the already extracted frames (no re-transcription).
   */
  applied_as: "pipeline" | "post_pass";
  /**
   * ISO 8601 UTC time of a post-pass; null when applied during processing.
   */
  applied_at?: string | null;
  source_frame_count: number;
  unique_slide_count: number;
  /**
   * Number of time ranges in frames[] after the pass.
   */
  run_count: number;
  source_frame_bytes: number;
  unique_slide_bytes: number;
  /**
   * Ignored live-overlay area (e.g. webcam box) as [x0, y0, x1, y1] fractions of the picture, or null.
   */
  overlay_mask: {
    /**
     * @minItems 4
     * @maxItems 4
     */
    box: [number, number, number, number];
    area_fraction: number;
  } | null;
  params: {
    [k: string]: number;
  };
}
/**
 * FROZEN v1.0. One manifest.json per processed original, written by Stream 3 (pipeline) to data/derived/<asset_id>/manifest.json and ingested by Stream 2 (backend). Shape follows the approved design Page, section 5. All paths inside 'segments/frames/slides/derived_files' are relative to data/derived/<asset_id>/. The pipeline NEVER deletes or modifies the original.
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "Manifest".
 */
export interface Manifest {
  /**
   * OUR RECOMMENDATION (not on the Page): lets the backend reject old manifests. Optional; default '1.0'.
   */
  schema_version?: "1.0";
  asset_id: AssetId;
  kind: AssetKind;
  original: OriginalRef;
  metadata: AssetMetadata;
  /**
   * Timed transcript segments. Empty for documents.
   */
  segments: Segment[];
  /**
   * Kept key frames. Empty for documents.
   */
  frames: Frame[];
  /**
   * One entry per PDF page. Empty for videos.
   */
  slides: Slide[];
  /**
   * EVERY derived file kept on disk for this asset (transcript, each frame, each page image, optional audio), with its real measured size. manifest.json itself is NOT listed (it cannot contain its own size); the backend measures it at ingest. Temporary files (e.g. extracted WAV) are deleted by the pipeline and never listed. The storage report sums ONLY this list + manifest bytes, so frames[].bytes / slides[].bytes are informational and must not be added again.
   */
  derived_files: DerivedFile[];
  pipeline: PipelineInfo;
}
/**
 * Every non-2xx response uses this body (backend must override FastAPI's default 422 shape).
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "ErrorResponse".
 */
export interface ErrorResponse {
  error: {
    code: ErrorCode;
    /**
     * Simple English, safe to show in the UI.
     */
    message: string;
    /**
     * Optional extra info (e.g. field errors).
     */
    details?: {} | null;
  };
}
/**
 * A pointer to something the UI can show: a key frame, a slide/page image, or the original (for playback/download).
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "MediaRef".
 */
export interface MediaRef {
  type: MediaType;
  asset_id: AssetId;
  /**
   * Local frame/slide id, null for 'original'.
   */
  item_id?: string | null;
  url: string;
  bytes?: number | null;
  t_start?: number | null;
  t_end?: number | null;
  page?: number | null;
}
/**
 * Library row. Returned by POST /api/assets (201) and GET /api/assets.
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "Asset".
 */
export interface Asset {
  id: AssetId;
  filename: string;
  kind: AssetKind;
  /**
   * Measured size of the original.
   */
  bytes: number;
  sha256: Sha256;
  source_system: SourceSystem;
  source_simulated: boolean;
  owner: string;
  status: AssetStatus;
  /**
   * OUR RECOMMENDATION: upload time (ISO 8601). Used to pick the copy kept in scenario 2.
   */
  created_at: string;
  /**
   * Sum of derived_files + manifest bytes; 0 until processed.
   */
  derived_bytes: number;
  /**
   * e.g. '/files/originals/a_01/deck.pdf'
   */
  original_url: string;
  /**
   * REC v1.1: true = generated sample/test file (not customer data). Kept for the duplicate demo; excluded from the default storage report.
   */
  test_data?: boolean;
}
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "DerivedSummary".
 */
export interface DerivedSummary {
  /**
   * derived_files total + manifest_bytes.
   */
  derived_bytes: number;
  manifest_bytes: number;
  file_count: number;
  segment_count: number;
  frame_count: number;
  slide_count: number;
  bytes_by_kind: {
    [k: string]: number;
  };
  /**
   * REC v1.1: unique slides after the unique-slide pass (videos); null if the pass has not run.
   */
  unique_slide_count?: number | null;
  /**
   * REC v1.1: key frames extracted before the unique-slide pass; null if the pass has not run.
   */
  source_frame_count?: number | null;
}
/**
 * GET /api/assets/{id}: one asset with metadata and derived summary.
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "AssetDetail".
 */
export interface AssetDetail {
  asset: Asset;
  metadata: AssetMetadata | null;
  derived: DerivedSummary | null;
  pipeline: PipelineInfo | null;
  latest_job: Job | null;
}
/**
 * Progress and errors are real, never faked. progress is stage-weighted: each step reports its own real fraction, and fixed step weights map it to 0..1 (see pipeline/dso_pipeline/video.py).
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "Job".
 */
export interface Job {
  id: string;
  asset_id: AssetId;
  status: JobStatus;
  /**
   * 0.0 to 1.0
   */
  progress: number;
  /**
   * OUR RECOMMENDATION: optional current step, e.g. 'transcribing'.
   */
  stage?: string | null;
  /**
   * REC v1.3: real progress of the current step only (0.0 to 1.0), e.g. transcribing = last finished Whisper segment end / media duration. null if the step does not report it.
   */
  stage_progress?: number | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  /**
   * REC v1.3: seconds since the job started running (measured by the server clock). null before it starts.
   */
  elapsed_s?: number | null;
  /**
   * REC v1.3: ESTIMATE of seconds left = elapsed_s * (1 - progress) / progress, from the measured rate so far. null until progress >= 0.03 and elapsed_s >= 10, and when the job is not running.
   */
  eta_s?: number | null;
}
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "AssetList".
 */
export interface AssetList {
  assets: Asset[];
}
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "FrameView".
 */
export interface FrameView {
  id: string;
  t_start: number;
  t_end: number;
  image_url: string;
  bytes: number;
  phash: string;
  matched_slide: string | null;
  /**
   * REC v1.1: unique slide number shown in this time range (null before the unique-slide pass).
   */
  slide?: number | null;
}
/**
 * GET /api/assets/{id}/timeline: transcript segments joined to frames.
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "Timeline".
 */
export interface Timeline {
  asset_id: AssetId;
  language: string | null;
  duration_seconds: number | null;
  /**
   * Original video, kept, for playback.
   */
  original_url: string;
  segments: Segment[];
  frames: FrameView[];
}
/**
 * A match from this slide to a slide in ANOTHER asset.
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "SlideMatch".
 */
export interface SlideMatch {
  type: SlideMatchType;
  other_asset_id: AssetId;
  other_slide_id: string;
  other_filename: string;
  other_page: number;
  other_source_system: SourceSystem;
  score: number;
  method: string;
}
/**
 * The three hashes for one slide (PDF p.2: split into slides and hash each).
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "HashRecord".
 */
export interface HashRecord {
  file_sha256: Sha256;
  text_sha256: Sha256;
  phash: PHash;
}
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "SlideView".
 */
export interface SlideView {
  id: string;
  page: number;
  text: string;
  hashes: HashRecord;
  image_url: string;
  bytes: number;
  matches: SlideMatch[];
}
/**
 * GET /api/assets/{id}/slides: pages with hashes and matches.
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "SlideList".
 */
export interface SlideList {
  asset_id: AssetId;
  metadata: AssetMetadata | null;
  slides: SlideView[];
}
/**
 * One search result: text + frame/slide image + timestamp (video) or page (document).
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "SearchHit".
 */
export interface SearchHit {
  hit_type: HitType;
  asset_id: AssetId;
  filename: string;
  kind: AssetKind;
  source_system: SourceSystem;
  owner: string;
  /**
   * Full segment or slide text; for 'asset' hits the indexed title + file name + metadata.
   */
  text: string;
  /**
   * FTS5 snippet() with matches wrapped in <mark>…</mark>. Only <mark> tags; frontend must escape everything else.
   */
  snippet: string;
  /**
   * Seconds (segments only).
   */
  start: number | null;
  end: number | null;
  /**
   * Page number (slides only).
   */
  page: number | null;
  /**
   * Local segment id ('s12'), slide id ('p4'), chat message id ('c3', REC v1.2), or 'meta' for a hit on the file's title / file name / metadata (REC v1.1).
   */
  item_id: string;
  /**
   * Frame on screen for a segment hit; null for slides.
   */
  frame_id: string | null;
  /**
   * Frame image (segment hit) or page image (slide hit).
   */
  media: MediaRef | null;
  /**
   * FTS5 bm25 rank turned positive; higher = better.
   */
  score: number;
}
/**
 * GET /api/search?q=
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "SearchResponse".
 */
export interface SearchResponse {
  query: string;
  total: number;
  hits: SearchHit[];
}
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "DuplicateMember".
 */
export interface DuplicateMember {
  asset_id: AssetId;
  filename: string;
  source_system: SourceSystem;
  owner: string;
  /**
   * Original file bytes.
   */
  bytes: number;
  /**
   * null for exact_file groups.
   */
  slide_id: string | null;
  page: number | null;
  image_url: string | null;
}
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "DuplicateEvidence".
 */
export interface DuplicateEvidence {
  /**
   * e.g. 'sha256', 'text_sha256+phash', 'phash', 'text_ratio'.
   */
  method: string;
  sha256?: string | null;
  text_sha256?: string | null;
  phash_distance?: number | null;
  /**
   * 0..1
   */
  text_similarity?: number | null;
}
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "DuplicateGroup".
 */
export interface DuplicateGroup {
  id: string;
  type: DuplicateType;
  /**
   * true for similar_slide (never treated as exact).
   */
  needs_review: boolean;
  /**
   * 1.0 for exact; similarity 0..1 otherwise.
   */
  score: number;
  evidence: DuplicateEvidence;
  /**
   * @minItems 2
   */
  members: [DuplicateMember, DuplicateMember, ...DuplicateMember[]];
}
/**
 * GET /api/duplicates: groups by type.
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "DuplicateReport".
 */
export interface DuplicateReport {
  groups: DuplicateGroup[];
  counts: {
    exact_file: number;
    shared_slide: number;
    similar_slide: number;
  };
}
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "RemovedItem".
 */
export interface RemovedItem {
  asset_id: AssetId;
  filename: string;
  bytes: number;
  reason: RemovalReason;
  /**
   * For exact_duplicate: the copy that stays.
   */
  kept_copy_asset_id: AssetId | null;
}
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "StorageScenario".
 */
export interface StorageScenario {
  /**
   * 0 = today (real), 1-3 hypothetical.
   */
  id: number;
  key: ScenarioKey;
  label: string;
  description: string;
  /**
   * false only for scenario 0. Nothing is ever deleted by the tool.
   */
  hypothetical: boolean;
  /**
   * Human-readable A formula for this scenario.
   */
  formula: string;
  /**
   * O
   */
  before_bytes: number;
  /**
   * A = kept_original_bytes + derived_bytes + index_bytes
   */
  after_bytes: number;
  /**
   * O - A (negative in scenario 0).
   */
  saved_bytes: number;
  /**
   * (O - A) / O * 100; null when O = 0.
   */
  savings_pct: number | null;
  kept_original_bytes: number;
  derived_bytes: number;
  index_bytes: number;
  /**
   * Hypothetical removals after approval. Empty for scenario 0.
   */
  removed: RemovedItem[];
}
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "StorageTotals".
 */
export interface StorageTotals {
  asset_count: number;
  /**
   * O: every copy on every (simulated) system.
   */
  original_bytes: number;
  video_original_bytes: number;
  document_original_bytes: number;
  /**
   * All derived_files + manifests, all assets.
   */
  derived_bytes: number;
  /**
   * Measured size of the SQLite file (incl. FTS).
   */
  index_bytes: number;
  /**
   * Bytes of all copies beyond the first in each SHA-256 group.
   */
  extra_exact_copy_bytes: number;
}
/**
 * GET /api/storage/report: measured bytes and the four scenarios.
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "StorageReport".
 */
export interface StorageReport {
  generated_at: string;
  formula: "Savings % = (O − A) / O × 100";
  totals: StorageTotals;
  /**
   * @minItems 4
   * @maxItems 4
   */
  scenarios: [StorageScenario, StorageScenario, StorageScenario, StorageScenario];
  not_counted: string[];
  information_lost: string[];
  notes: string[];
  /**
   * REC v1.1: 'real_files' (default) = generated test files excluded; 'all_files' = everything in the library.
   */
  scope?: "real_files" | "all_files";
  /**
   * REC v1.1: generated test files left out of this report (empty when scope = all_files).
   */
  excluded_test_data?: {
    asset_count: number;
    original_bytes: number;
    derived_bytes: number;
    asset_ids: AssetId[];
  };
}
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "DuplicateLocation".
 */
export interface DuplicateLocation {
  asset_id: AssetId;
  filename: string;
  source_system: SourceSystem;
  owner: string;
}
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "OffboardingRow".
 */
export interface OffboardingRow {
  asset_id: AssetId;
  filename: string;
  kind: AssetKind;
  bytes: number;
  source_system: SourceSystem;
  recommendation: OffboardingRecommendation;
  /**
   * e.g. 'Confirmed exact duplicate at SharePoint: deck.pdf (owner: bob)' or 'No exact copy elsewhere'.
   */
  reason: string;
  duplicates_elsewhere: DuplicateLocation[];
}
/**
 * GET /api/offboarding?owner=. Recommendation only; the API has no delete endpoint.
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "OffboardingReview".
 */
export interface OffboardingReview {
  owner: string;
  generated_at: string;
  deletes_performed: false;
  rows: OffboardingRow[];
  summary: {
    total: number;
    eligible: number;
    keep: number;
    eligible_bytes: number;
  };
}
/**
 * Where a piece of data came from. Every export chunk carries this.
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "Provenance".
 */
export interface Provenance {
  asset_id: AssetId;
  filename: string;
  sha256: Sha256;
  source_system: SourceSystem;
  source_simulated: boolean;
  owner: string;
  original_url: string;
}
/**
 * One AI-ready text chunk. GET /api/export.jsonl returns one ExportChunk per line. 'metadata' repeats the asset's doc_number / revision / title for revision tracking.
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "ExportChunk".
 */
export interface ExportChunk {
  schema_version: "1.0";
  chunk_id: ItemRef;
  kind: ChunkKind;
  text: string;
  start: number | null;
  end: number | null;
  page: number | null;
  frame_id: string | null;
  slide_id: string | null;
  image_url: string | null;
  language: string | null;
  metadata: AssetMetadata;
  source: Provenance;
}
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "ExportMatch".
 */
export interface ExportMatch {
  level: MatchLevel;
  type: MatchType;
  a: ItemRef;
  b: ItemRef;
  score: number;
  method: string;
}
/**
 * GET /api/assets/{id}/export: AI-ready JSON for one asset with provenance.
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "ExportAsset".
 */
export interface ExportAsset {
  schema_version: "1.0";
  exported_at: string;
  source: Provenance;
  kind: AssetKind;
  metadata: AssetMetadata;
  pipeline: PipelineInfo | null;
  chunks: ExportChunk[];
  frames: FrameView[];
  slides: SlideView[];
  /**
   * All exact/shared/similar matches touching this asset.
   */
  matches: ExportMatch[];
}
/**
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "Health".
 */
export interface Health {
  status: "ok";
  version: string;
}
/**
 * REC v1.2: one message from a meeting chat attached to a recording.
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "ChatMessage".
 */
export interface ChatMessage {
  /**
   * 'c<n>', 1-based, in chat order.
   */
  id: string;
  /**
   * Wall-clock time exactly as written in the chat, e.g. '16:44'.
   */
  clock: string;
  /**
   * Estimated seconds from the recording start (start of the written minute minus the recording start). null if the recording start is unknown or the message is outside the recording.
   */
  t: number | null;
  author: string;
  text: string;
  /**
   * The message contained a picture (not stored; only noted).
   */
  has_image: boolean;
}
/**
 * REC v1.2: the chat file that was attached (the file itself is not stored by the app).
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "ChatSource".
 */
export interface ChatSource {
  filename: string;
  bytes: number;
  sha256: Sha256;
  attached_at: string;
}
/**
 * REC v1.2: how chat clock times were turned into recording times, and how sure we are.
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "ChatAlignment".
 */
export interface ChatAlignment {
  /**
   * Local wall-clock start of the recording, 'YYYY-MM-DDTHH:MM:SS' (no time zone), or null if unknown.
   */
  recording_start: string | null;
  /**
   * Where recording_start came from: 'filename', 'manual', or 'unknown'.
   */
  basis: "filename" | "manual" | "unknown";
  /**
   * Chat times are written to the minute, so t can be up to this many seconds early.
   */
  uncertainty_seconds: number | null;
  /**
   * 'estimated' (times computed, not checked against speech), 'unknown' (no recording start).
   */
  status: "estimated" | "unknown";
  note: string;
}
/**
 * REC v1.2: GET/POST /api/assets/{id}/chat. The meeting chat of a recording with estimated recording times.
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "ChatLog".
 */
export interface ChatLog {
  asset_id: AssetId;
  source: ChatSource | null;
  alignment: ChatAlignment | null;
  messages: ChatMessage[];
}
/**
 * REC v1.4: one selectable Whisper model and whether its weights are on this computer.
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "WhisperModelInfo".
 */
export interface WhisperModelInfo {
  name: WhisperModelName;
  /**
   * Short simple-English label, e.g. 'Fast + accurate'.
   */
  label: string;
  /**
   * true = the model weights are already in the local model cache (no download needed).
   */
  installed: boolean;
}
/**
 * REC v1.4: body of PUT /api/settings. Only affects jobs started AFTER the change; nothing is re-processed automatically.
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "SettingsUpdate".
 */
export interface SettingsUpdate {
  whisper_model: WhisperModelName;
  whisper_device: WhisperDevice;
}
/**
 * REC v1.4: saved processing settings plus what the next job will really use. Environment variables (DSO_WHISPER_MODEL, DSO_WHISPER_DEVICE) still win over the saved setting; env_overrides lists the ones that are set.
 *
 * This interface was referenced by `DsoContracts`'s JSON-Schema
 * via the `definition` "Settings".
 */
export interface Settings {
  whisper_model: WhisperModelName;
  whisper_device: WhisperDevice;
  /**
   * Model name the next job will use (after env overrides).
   */
  effective_model: string;
  /**
   * Device setting the next job will use (after env overrides): auto, cuda or cpu.
   */
  effective_device: string;
  /**
   * Names of the environment variables that override the saved setting, e.g. ['DSO_WHISPER_DEVICE'].
   */
  env_overrides: string[];
  models: WhisperModelInfo[];
  /**
   * true = an NVIDIA GPU is usable by the pipeline; null = could not be checked.
   */
  gpu_available: boolean | null;
}
