# GENERATED from contracts/schemas/*.json by contracts/scripts/generate.sh. DO NOT EDIT. FROZEN v1.0

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, RootModel


class AssetId(RootModel[str]):
    root: str = Field(
        ...,
        description="Backend-generated asset id, e.g. 'a_01' or 'a_7f3c9e21'.",
        pattern="^a_[A-Za-z0-9]+$",
    )


class AssetKind(StrEnum):
    video = "video"
    document = "document"


class LocalId(RootModel[str]):
    root: str = Field(
        ...,
        description="Id unique only inside one asset: segments 's<n>', frames 'f<n>', slides 'p<page>'. Globally an item is '<asset_id>:<local_id>' (see ItemRef in api.schema.json).",
        pattern="^[sfp][0-9]+$",
    )


class OriginalRef(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: str = Field(
        ...,
        description="Relative to the data/ directory, e.g. 'originals/a_01/deck.pdf'. Read-only.",
    )
    bytes: int = Field(..., ge=0)
    sha256: str = Field(..., pattern="^[0-9a-f]{64}$")


class AssetMetadata(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    title: str | None
    author: str | None
    doc_number: str | None
    revision: str | None
    date: str | None = Field(
        ...,
        description="As found in the source (PDF metadata or text). ISO 8601 if parseable, else raw string.",
    )
    language: str | None = Field(
        ...,
        description="Detected language code for videos (faster-whisper), e.g. 'en', 'sv'. null for documents unless detected.",
    )
    duration_seconds: float | None = Field(
        None,
        description="OUR RECOMMENDATION (not on the Page): video length. Optional.",
        ge=0.0,
    )


class Segment(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: str = Field(
        ...,
        description="Id unique only inside one asset: segments 's<n>', frames 'f<n>', slides 'p<page>'. Globally an item is '<asset_id>:<local_id>' (see ItemRef in api.schema.json).",
        pattern="^[sfp][0-9]+$",
    )
    start: float = Field(..., description="Seconds from video start.", ge=0.0)
    end: float = Field(..., ge=0.0)
    text: str
    frame_id: str | None = Field(
        ...,
        description="The kept frame on screen when this segment STARTS (frame.t_start <= start < frame.t_end).",
    )
    speaker: str | None = Field(
        ..., description="Always null in the MVP (speaker ID is out of scope)."
    )


class Frame(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: str = Field(
        ...,
        description="Id unique only inside one asset: segments 's<n>', frames 'f<n>', slides 'p<page>'. Globally an item is '<asset_id>:<local_id>' (see ItemRef in api.schema.json).",
        pattern="^[sfp][0-9]+$",
    )
    t_start: float = Field(..., ge=0.0)
    t_end: float = Field(
        ...,
        description="Time of the next kept frame, or video end. Covers [t_start, t_end).",
        ge=0.0,
    )
    path: str = Field(..., description="e.g. 'frames/f3.webp'. WebP, max 1280 px wide.")
    bytes: int = Field(..., ge=0)
    phash: str = Field(
        ...,
        description="Perceptual hash as lowercase hex. imagehash.phash(hash_size=8) => 16 hex chars (64 bits). See contracts/thresholds.json.",
        pattern="^[0-9a-f]{16}$",
    )
    matched_slide: str | None = Field(
        ...,
        description="STRETCH (levels 3-4). Global slide ref '<asset_id>:p<page>' or null. Always null in P0.",
    )
    slide: int | None = Field(
        None,
        description="REC v1.1 (unique-slide pass): 1-based number of the unique slide shown in this time range. Several ranges can show the same slide (the talk went back to it); they then share one image file. Absent on manifests made before the pass.",
        ge=1,
    )
    source_frames: list[LocalId] | None = Field(
        None,
        description="REC v1.1: ids of the originally extracted key frames merged into this time range (audit trail). The first one is this frame's id.",
        min_length=1,
    )


class Slide(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: str = Field(
        ...,
        description="Id unique only inside one asset: segments 's<n>', frames 'f<n>', slides 'p<page>'. Globally an item is '<asset_id>:<local_id>' (see ItemRef in api.schema.json).",
        pattern="^[sfp][0-9]+$",
    )
    page: int = Field(..., description="1-based page number.", ge=1)
    text: str
    text_sha256: str = Field(
        ...,
        description="SHA-256 of the NORMALISED page text (rule in CONTRACTS.md: NFKC, lowercase, collapse whitespace, strip). The file SHA-256 is original.sha256; together with phash these are the three hashes.",
        pattern="^[0-9a-f]{64}$",
    )
    phash: str = Field(
        ...,
        description="Perceptual hash as lowercase hex. imagehash.phash(hash_size=8) => 16 hex chars (64 bits). See contracts/thresholds.json.",
        pattern="^[0-9a-f]{16}$",
    )
    path: str = Field(..., description="e.g. 'pages/p4.webp'.")
    bytes: int = Field(..., ge=0)


class DerivedFileKind(StrEnum):
    transcript = "transcript"
    frame = "frame"
    page_image = "page_image"
    page_text = "page_text"
    audio = "audio"
    other = "other"


class DerivedFile(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: str
    bytes: int = Field(..., ge=0)
    kind: DerivedFileKind


class AppliedAs(StrEnum):
    pipeline = "pipeline"
    post_pass = "post_pass"


class BoxItem(RootModel[float]):
    root: float = Field(..., ge=0.0, le=1.0)


class OverlayMask(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    box: list[BoxItem] = Field(..., max_length=4, min_length=4)
    area_fraction: float = Field(..., ge=0.0, le=1.0)


class UniqueSlidesInfo(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    method: str
    applied_as: AppliedAs = Field(
        ...,
        description="'pipeline' = during processing; 'post_pass' = later, on the already extracted frames (no re-transcription).",
    )
    applied_at: str | None = Field(
        None,
        description="ISO 8601 UTC time of a post-pass; null when applied during processing.",
    )
    source_frame_count: int = Field(..., ge=0)
    unique_slide_count: int = Field(..., ge=0)
    run_count: int = Field(
        ..., description="Number of time ranges in frames[] after the pass.", ge=0
    )
    source_frame_bytes: int = Field(..., ge=0)
    unique_slide_bytes: int = Field(..., ge=0)
    overlay_mask: OverlayMask | None = Field(
        ...,
        description="Ignored live-overlay area (e.g. webcam box) as [x0, y0, x1, y1] fractions of the picture, or null.",
    )
    params: dict[str, float]


class SourceSystem(StrEnum):
    sharepoint = "sharepoint"
    onedrive = "onedrive"
    ericsson_play = "ericsson_play"


class AssetStatus(StrEnum):
    uploaded = "uploaded"
    queued = "queued"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class ErrorCode(StrEnum):
    not_found = "not_found"
    validation_error = "validation_error"
    unsupported_file_type = "unsupported_file_type"
    conflict = "conflict"
    pipeline_failed = "pipeline_failed"
    internal_error = "internal_error"


class Error(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    code: ErrorCode
    message: str = Field(..., description="Simple English, safe to show in the UI.")
    details: dict[str, Any] | None = Field(
        None, description="Optional extra info (e.g. field errors)."
    )


class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    error: Error


class Asset(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: str = Field(
        ...,
        description="Backend-generated asset id, e.g. 'a_01' or 'a_7f3c9e21'.",
        pattern="^a_[A-Za-z0-9]+$",
    )
    filename: str
    kind: AssetKind
    bytes: int = Field(..., description="Measured size of the original.", ge=0)
    sha256: str = Field(..., pattern="^[0-9a-f]{64}$")
    source_system: SourceSystem
    source_simulated: bool
    owner: str
    status: AssetStatus
    created_at: AwareDatetime = Field(
        ...,
        description="OUR RECOMMENDATION: upload time (ISO 8601). Used to pick the copy kept in scenario 2.",
    )
    derived_bytes: int = Field(
        ...,
        description="Sum of derived_files + manifest bytes; 0 until processed.",
        ge=0,
    )
    original_url: str = Field(..., description="e.g. '/files/originals/a_01/deck.pdf'")
    test_data: bool | None = Field(
        None,
        description="REC v1.1: true = generated sample/test file (not customer data). Kept for the duplicate demo; excluded from the default storage report.",
    )


class BytesByKind(RootModel[int]):
    root: int = Field(..., ge=0)


class DerivedSummary(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    derived_bytes: int = Field(
        ..., description="derived_files total + manifest_bytes.", ge=0
    )
    manifest_bytes: int = Field(..., ge=0)
    file_count: int = Field(..., ge=0)
    segment_count: int = Field(..., ge=0)
    frame_count: int = Field(..., ge=0)
    slide_count: int = Field(..., ge=0)
    bytes_by_kind: dict[str, BytesByKind]
    unique_slide_count: int | None = Field(
        None,
        description="REC v1.1: unique slides after the unique-slide pass (videos); null if the pass has not run.",
        ge=0,
    )
    source_frame_count: int | None = Field(
        None,
        description="REC v1.1: key frames extracted before the unique-slide pass; null if the pass has not run.",
        ge=0,
    )


class AssetList(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    assets: list[Asset]


class Job(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: str
    asset_id: str = Field(
        ...,
        description="Backend-generated asset id, e.g. 'a_01' or 'a_7f3c9e21'.",
        pattern="^a_[A-Za-z0-9]+$",
    )
    status: JobStatus
    progress: float = Field(..., description="0.0 to 1.0", ge=0.0, le=1.0)
    stage: str | None = Field(
        None,
        description="OUR RECOMMENDATION: optional current step, e.g. 'transcribing'.",
    )
    error: str | None
    started_at: AwareDatetime | None
    finished_at: AwareDatetime | None


class FrameView(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: str
    t_start: float
    t_end: float
    image_url: str
    bytes: int = Field(..., ge=0)
    phash: str
    matched_slide: str | None
    slide: int | None = Field(
        None,
        description="REC v1.1: unique slide number shown in this time range (null before the unique-slide pass).",
        ge=1,
    )


class Timeline(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    asset_id: str = Field(
        ...,
        description="Backend-generated asset id, e.g. 'a_01' or 'a_7f3c9e21'.",
        pattern="^a_[A-Za-z0-9]+$",
    )
    language: str | None
    duration_seconds: float | None
    original_url: str = Field(..., description="Original video, kept, for playback.")
    segments: list[Segment]
    frames: list[FrameView]


class MatchType(StrEnum):
    exact = "exact"
    shared = "shared"
    similar = "similar"


class MatchLevel(StrEnum):
    file = "file"
    slide = "slide"


class HashRecord(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    file_sha256: str = Field(..., pattern="^[0-9a-f]{64}$")
    text_sha256: str = Field(..., pattern="^[0-9a-f]{64}$")
    phash: str = Field(
        ...,
        description="Perceptual hash as lowercase hex. imagehash.phash(hash_size=8) => 16 hex chars (64 bits). See contracts/thresholds.json.",
        pattern="^[0-9a-f]{16}$",
    )


class DuplicateType(StrEnum):
    exact_file = "exact_file"
    shared_slide = "shared_slide"
    similar_slide = "similar_slide"


class DuplicateMember(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    asset_id: str = Field(
        ...,
        description="Backend-generated asset id, e.g. 'a_01' or 'a_7f3c9e21'.",
        pattern="^a_[A-Za-z0-9]+$",
    )
    filename: str
    source_system: SourceSystem
    owner: str
    bytes: int = Field(..., description="Original file bytes.", ge=0)
    slide_id: str | None = Field(..., description="null for exact_file groups.")
    page: int | None
    image_url: str | None


class DuplicateEvidence(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    method: str = Field(
        ..., description="e.g. 'sha256', 'text_sha256+phash', 'phash', 'text_ratio'."
    )
    sha256: str | None = None
    text_sha256: str | None = None
    phash_distance: int | None = None
    text_similarity: float | None = Field(None, description="0..1")


class DuplicateGroup(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: str
    type: DuplicateType
    needs_review: bool = Field(
        ..., description="true for similar_slide (never treated as exact)."
    )
    score: float = Field(..., description="1.0 for exact; similarity 0..1 otherwise.")
    evidence: DuplicateEvidence
    members: list[DuplicateMember] = Field(..., min_length=2)


class Counts(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    exact_file: int = Field(..., ge=0)
    shared_slide: int = Field(..., ge=0)
    similar_slide: int = Field(..., ge=0)


class DuplicateReport(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    groups: list[DuplicateGroup]
    counts: Counts


class ScenarioKey(StrEnum):
    today = "today"
    replace_videos = "replace_videos"
    remove_exact_duplicates = "remove_exact_duplicates"
    both = "both"


class StorageTotals(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    asset_count: int = Field(..., ge=0)
    original_bytes: int = Field(
        ..., description="O: every copy on every (simulated) system.", ge=0
    )
    video_original_bytes: int = Field(..., ge=0)
    document_original_bytes: int = Field(..., ge=0)
    derived_bytes: int = Field(
        ..., description="All derived_files + manifests, all assets.", ge=0
    )
    index_bytes: int = Field(
        ..., description="Measured size of the SQLite file (incl. FTS).", ge=0
    )
    extra_exact_copy_bytes: int = Field(
        ...,
        description="Bytes of all copies beyond the first in each SHA-256 group.",
        ge=0,
    )


class Scope(StrEnum):
    real_files = "real_files"
    all_files = "all_files"


class ExcludedTestData(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    asset_count: int = Field(..., ge=0)
    original_bytes: int = Field(..., ge=0)
    derived_bytes: int = Field(..., ge=0)
    asset_ids: list[AssetId]


class OffboardingRecommendation(StrEnum):
    eligible_after_approval = "eligible_after_approval"
    keep = "keep"


class DuplicateLocation(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    asset_id: str = Field(
        ...,
        description="Backend-generated asset id, e.g. 'a_01' or 'a_7f3c9e21'.",
        pattern="^a_[A-Za-z0-9]+$",
    )
    filename: str
    source_system: SourceSystem
    owner: str


class OffboardingRow(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    asset_id: str = Field(
        ...,
        description="Backend-generated asset id, e.g. 'a_01' or 'a_7f3c9e21'.",
        pattern="^a_[A-Za-z0-9]+$",
    )
    filename: str
    kind: AssetKind
    bytes: int = Field(..., ge=0)
    source_system: SourceSystem
    recommendation: OffboardingRecommendation
    reason: str = Field(
        ...,
        description="e.g. 'Confirmed exact duplicate at SharePoint: deck.pdf (owner: bob)' or 'No exact copy elsewhere'.",
    )
    duplicates_elsewhere: list[DuplicateLocation]


class Summary(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    total: int = Field(..., ge=0)
    eligible: int = Field(..., ge=0)
    keep: int = Field(..., ge=0)
    eligible_bytes: int = Field(..., ge=0)


class OffboardingReview(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    owner: str
    generated_at: AwareDatetime
    deletes_performed: Literal[False]
    rows: list[OffboardingRow]
    summary: Summary


class Provenance(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    asset_id: str = Field(
        ...,
        description="Backend-generated asset id, e.g. 'a_01' or 'a_7f3c9e21'.",
        pattern="^a_[A-Za-z0-9]+$",
    )
    filename: str
    sha256: str = Field(..., pattern="^[0-9a-f]{64}$")
    source_system: SourceSystem
    source_simulated: bool
    owner: str
    original_url: str


class ExportMatch(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    level: MatchLevel
    type: MatchType
    a: str = Field(
        ...,
        description="Global id of an item: '<asset_id>' for a whole file, or '<asset_id>:<local_id>' for a segment/frame/slide, e.g. 'a_02:p4'. Used in matches.a_id/b_id and export chunk ids.",
        pattern="^a_[A-Za-z0-9]+(:[sfp][0-9]+)?$",
    )
    b: str = Field(
        ...,
        description="Global id of an item: '<asset_id>' for a whole file, or '<asset_id>:<local_id>' for a segment/frame/slide, e.g. 'a_02:p4'. Used in matches.a_id/b_id and export chunk ids.",
        pattern="^a_[A-Za-z0-9]+(:[sfp][0-9]+)?$",
    )
    score: float
    method: str


class Health(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    status: Literal["ok"]
    version: str


class MediaType(StrEnum):
    frame = "frame"
    slide = "slide"
    original = "original"


class SlideMatchType(StrEnum):
    shared = "shared"
    similar = "similar"


class HitType(StrEnum):
    segment = "segment"
    slide = "slide"
    asset = "asset"
    chat = "chat"


class RemovalReason(StrEnum):
    replaced_by_derived = "replaced_by_derived"
    exact_duplicate = "exact_duplicate"


class ChunkKind(StrEnum):
    transcript_segment = "transcript_segment"
    slide_text = "slide_text"


class ChatMessage(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: str = Field(
        ..., description="'c<n>', 1-based, in chat order.", pattern="^c[0-9]+$"
    )
    clock: str = Field(
        ..., description="Wall-clock time exactly as written in the chat, e.g. '16:44'."
    )
    t: float | None = Field(
        ...,
        description="Estimated seconds from the recording start (start of the written minute minus the recording start). null if the recording start is unknown or the message is outside the recording.",
    )
    author: str
    text: str
    has_image: bool = Field(
        ..., description="The message contained a picture (not stored; only noted)."
    )


class ChatSource(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    filename: str
    bytes: int = Field(..., ge=0)
    sha256: str = Field(..., pattern="^[0-9a-f]{64}$")
    attached_at: AwareDatetime


class Basis(StrEnum):
    filename = "filename"
    manual = "manual"
    unknown = "unknown"


class Status(StrEnum):
    estimated = "estimated"
    unknown = "unknown"


class ChatAlignment(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    recording_start: str | None = Field(
        ...,
        description="Local wall-clock start of the recording, 'YYYY-MM-DDTHH:MM:SS' (no time zone), or null if unknown.",
    )
    basis: Basis = Field(
        ...,
        description="Where recording_start came from: 'filename', 'manual', or 'unknown'.",
    )
    uncertainty_seconds: float | None = Field(
        ...,
        description="Chat times are written to the minute, so t can be up to this many seconds early.",
    )
    status: Status = Field(
        ...,
        description="'estimated' (times computed, not checked against speech), 'unknown' (no recording start).",
    )
    note: str


class ChatLog(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    asset_id: str = Field(
        ...,
        description="Backend-generated asset id, e.g. 'a_01' or 'a_7f3c9e21'.",
        pattern="^a_[A-Za-z0-9]+$",
    )
    source: ChatSource | None
    alignment: ChatAlignment | None
    messages: list[ChatMessage]


class PipelineInfo(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    version: str
    model: str | None = Field(
        ..., description="e.g. 'faster-whisper small int8'; null for documents."
    )
    frame_threshold: int | None = Field(
        ..., description="pHash distance used to keep a new frame; null for documents."
    )
    seconds: float = Field(..., description="Wall-clock processing time.", ge=0.0)
    warnings: list[str] | None = Field(
        None,
        description="OUR RECOMMENDATION (not on the Page): non-fatal issues, e.g. 'no text layer on page 3'. Optional.",
    )
    unique_slides: UniqueSlidesInfo | None = Field(
        None,
        description="REC v1.1: unique-slide pass result (videos); absent or null if it has not run.",
    )


class Manifest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    schema_version: Literal["1.0"] = Field(
        "1.0",
        description="OUR RECOMMENDATION (not on the Page): lets the backend reject old manifests. Optional; default '1.0'.",
    )
    asset_id: str = Field(
        ...,
        description="Backend-generated asset id, e.g. 'a_01' or 'a_7f3c9e21'.",
        pattern="^a_[A-Za-z0-9]+$",
    )
    kind: AssetKind
    original: OriginalRef
    metadata: AssetMetadata
    segments: list[Segment] = Field(
        ..., description="Timed transcript segments. Empty for documents."
    )
    frames: list[Frame] = Field(
        ..., description="Kept key frames. Empty for documents."
    )
    slides: list[Slide] = Field(
        ..., description="One entry per PDF page. Empty for videos."
    )
    derived_files: list[DerivedFile] = Field(
        ...,
        description="EVERY derived file kept on disk for this asset (transcript, each frame, each page image, optional audio), with its real measured size. manifest.json itself is NOT listed (it cannot contain its own size); the backend measures it at ingest. Temporary files (e.g. extracted WAV) are deleted by the pipeline and never listed. The storage report sums ONLY this list + manifest bytes, so frames[].bytes / slides[].bytes are informational and must not be added again.",
    )
    pipeline: PipelineInfo


class MediaRef(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: MediaType
    asset_id: str = Field(
        ...,
        description="Backend-generated asset id, e.g. 'a_01' or 'a_7f3c9e21'.",
        pattern="^a_[A-Za-z0-9]+$",
    )
    item_id: str | None = Field(
        None, description="Local frame/slide id, null for 'original'."
    )
    url: str
    bytes: int | None = Field(None, ge=0)
    t_start: float | None = None
    t_end: float | None = None
    page: int | None = None


class AssetDetail(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    asset: Asset
    metadata: AssetMetadata | None
    derived: DerivedSummary | None
    pipeline: PipelineInfo | None
    latest_job: Job | None


class SlideMatch(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: SlideMatchType
    other_asset_id: str = Field(
        ...,
        description="Backend-generated asset id, e.g. 'a_01' or 'a_7f3c9e21'.",
        pattern="^a_[A-Za-z0-9]+$",
    )
    other_slide_id: str
    other_filename: str
    other_page: int
    other_source_system: SourceSystem
    score: float
    method: str


class SlideView(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: str
    page: int = Field(..., ge=1)
    text: str
    hashes: HashRecord
    image_url: str
    bytes: int = Field(..., ge=0)
    matches: list[SlideMatch]


class SlideList(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    asset_id: str = Field(
        ...,
        description="Backend-generated asset id, e.g. 'a_01' or 'a_7f3c9e21'.",
        pattern="^a_[A-Za-z0-9]+$",
    )
    metadata: AssetMetadata | None
    slides: list[SlideView]


class SearchHit(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    hit_type: HitType
    asset_id: str = Field(
        ...,
        description="Backend-generated asset id, e.g. 'a_01' or 'a_7f3c9e21'.",
        pattern="^a_[A-Za-z0-9]+$",
    )
    filename: str
    kind: AssetKind
    source_system: SourceSystem
    owner: str
    text: str = Field(
        ...,
        description="Full segment or slide text; for 'asset' hits the indexed title + file name + metadata.",
    )
    snippet: str = Field(
        ...,
        description="FTS5 snippet() with matches wrapped in <mark>…</mark>. Only <mark> tags; frontend must escape everything else.",
    )
    start: float | None = Field(..., description="Seconds (segments only).")
    end: float | None
    page: int | None = Field(..., description="Page number (slides only).")
    item_id: str = Field(
        ...,
        description="Local segment id ('s12'), slide id ('p4'), chat message id ('c3', REC v1.2), or 'meta' for a hit on the file's title / file name / metadata (REC v1.1).",
    )
    frame_id: str | None = Field(
        ..., description="Frame on screen for a segment hit; null for slides."
    )
    media: MediaRef | None = Field(
        ..., description="Frame image (segment hit) or page image (slide hit)."
    )
    score: float = Field(
        ..., description="FTS5 bm25 rank turned positive; higher = better."
    )


class SearchResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    query: str
    total: int = Field(..., ge=0)
    hits: list[SearchHit]


class RemovedItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    asset_id: str = Field(
        ...,
        description="Backend-generated asset id, e.g. 'a_01' or 'a_7f3c9e21'.",
        pattern="^a_[A-Za-z0-9]+$",
    )
    filename: str
    bytes: int = Field(..., ge=0)
    reason: RemovalReason
    kept_copy_asset_id: AssetId | None = Field(
        ..., description="For exact_duplicate: the copy that stays."
    )


class StorageScenario(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: int = Field(..., description="0 = today (real), 1-3 hypothetical.", ge=0, le=3)
    key: ScenarioKey
    label: str
    description: str
    hypothetical: bool = Field(
        ...,
        description="false only for scenario 0. Nothing is ever deleted by the tool.",
    )
    formula: str = Field(..., description="Human-readable A formula for this scenario.")
    before_bytes: int = Field(..., description="O", ge=0)
    after_bytes: int = Field(
        ..., description="A = kept_original_bytes + derived_bytes + index_bytes", ge=0
    )
    saved_bytes: int = Field(..., description="O - A (negative in scenario 0).")
    savings_pct: float | None = Field(
        ..., description="(O - A) / O * 100; null when O = 0."
    )
    kept_original_bytes: int = Field(..., ge=0)
    derived_bytes: int = Field(..., ge=0)
    index_bytes: int = Field(..., ge=0)
    removed: list[RemovedItem] = Field(
        ..., description="Hypothetical removals after approval. Empty for scenario 0."
    )


class StorageReport(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    generated_at: AwareDatetime
    formula: Literal["Savings % = (O − A) / O × 100"]
    totals: StorageTotals
    scenarios: list[StorageScenario] = Field(..., max_length=4, min_length=4)
    not_counted: list[str]
    information_lost: list[str]
    notes: list[str]
    scope: Scope | None = Field(
        None,
        description="REC v1.1: 'real_files' (default) = generated test files excluded; 'all_files' = everything in the library.",
    )
    excluded_test_data: ExcludedTestData | None = Field(
        None,
        description="REC v1.1: generated test files left out of this report (empty when scope = all_files).",
    )


class ExportChunk(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    schema_version: Literal["1.0"]
    chunk_id: str = Field(
        ...,
        description="Global id of an item: '<asset_id>' for a whole file, or '<asset_id>:<local_id>' for a segment/frame/slide, e.g. 'a_02:p4'. Used in matches.a_id/b_id and export chunk ids.",
        pattern="^a_[A-Za-z0-9]+(:[sfp][0-9]+)?$",
    )
    kind: ChunkKind
    text: str
    start: float | None
    end: float | None
    page: int | None
    frame_id: str | None
    slide_id: str | None
    image_url: str | None
    language: str | None
    metadata: AssetMetadata
    source: Provenance


class ExportAsset(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    schema_version: Literal["1.0"]
    exported_at: AwareDatetime
    source: Provenance
    kind: AssetKind
    metadata: AssetMetadata
    pipeline: PipelineInfo | None
    chunks: list[ExportChunk]
    frames: list[FrameView]
    slides: list[SlideView]
    matches: list[ExportMatch] = Field(
        ..., description="All exact/shared/similar matches touching this asset."
    )


class DsoContracts(BaseModel):
    AssetId: str | None = Field(
        None,
        description="Backend-generated asset id, e.g. 'a_01' or 'a_7f3c9e21'.",
        pattern="^a_[A-Za-z0-9]+$",
    )
    AssetKind_1: AssetKind | None = Field(None, alias="AssetKind")
    Sha256: str | None = Field(None, pattern="^[0-9a-f]{64}$")
    PHash: str | None = Field(
        None,
        description="Perceptual hash as lowercase hex. imagehash.phash(hash_size=8) => 16 hex chars (64 bits). See contracts/thresholds.json.",
        pattern="^[0-9a-f]{16}$",
    )
    LocalId: str | None = Field(
        None,
        description="Id unique only inside one asset: segments 's<n>', frames 'f<n>', slides 'p<page>'. Globally an item is '<asset_id>:<local_id>' (see ItemRef in api.schema.json).",
        pattern="^[sfp][0-9]+$",
    )
    OriginalRef_1: OriginalRef | None = Field(None, alias="OriginalRef")
    AssetMetadata_1: AssetMetadata | None = Field(None, alias="AssetMetadata")
    Segment_1: Segment | None = Field(None, alias="Segment")
    Frame_1: Frame | None = Field(None, alias="Frame")
    Slide_1: Slide | None = Field(None, alias="Slide")
    DerivedFileKind_1: DerivedFileKind | None = Field(None, alias="DerivedFileKind")
    DerivedFile_1: DerivedFile | None = Field(None, alias="DerivedFile")
    PipelineInfo_1: PipelineInfo | None = Field(None, alias="PipelineInfo")
    UniqueSlidesInfo_1: UniqueSlidesInfo | None = Field(None, alias="UniqueSlidesInfo")
    Manifest_1: Manifest | None = Field(None, alias="Manifest")
    ItemRef: str | None = Field(
        None,
        description="Global id of an item: '<asset_id>' for a whole file, or '<asset_id>:<local_id>' for a segment/frame/slide, e.g. 'a_02:p4'. Used in matches.a_id/b_id and export chunk ids.",
        pattern="^a_[A-Za-z0-9]+(:[sfp][0-9]+)?$",
    )
    SourceSystem_1: SourceSystem | None = Field(None, alias="SourceSystem")
    AssetStatus_1: AssetStatus | None = Field(None, alias="AssetStatus")
    JobStatus_1: JobStatus | None = Field(None, alias="JobStatus")
    ErrorCode_1: ErrorCode | None = Field(None, alias="ErrorCode")
    ErrorResponse_1: ErrorResponse | None = Field(None, alias="ErrorResponse")
    MediaRef_1: MediaRef | None = Field(None, alias="MediaRef")
    Asset_1: Asset | None = Field(None, alias="Asset")
    DerivedSummary_1: DerivedSummary | None = Field(None, alias="DerivedSummary")
    AssetDetail_1: AssetDetail | None = Field(None, alias="AssetDetail")
    AssetList_1: AssetList | None = Field(None, alias="AssetList")
    Job_1: Job | None = Field(None, alias="Job")
    FrameView_1: FrameView | None = Field(None, alias="FrameView")
    Timeline_1: Timeline | None = Field(None, alias="Timeline")
    MatchType_1: MatchType | None = Field(None, alias="MatchType")
    MatchLevel_1: MatchLevel | None = Field(None, alias="MatchLevel")
    SlideMatch_1: SlideMatch | None = Field(None, alias="SlideMatch")
    HashRecord_1: HashRecord | None = Field(None, alias="HashRecord")
    SlideView_1: SlideView | None = Field(None, alias="SlideView")
    SlideList_1: SlideList | None = Field(None, alias="SlideList")
    SearchHit_1: SearchHit | None = Field(None, alias="SearchHit")
    SearchResponse_1: SearchResponse | None = Field(None, alias="SearchResponse")
    DuplicateType_1: DuplicateType | None = Field(None, alias="DuplicateType")
    DuplicateMember_1: DuplicateMember | None = Field(None, alias="DuplicateMember")
    DuplicateEvidence_1: DuplicateEvidence | None = Field(
        None, alias="DuplicateEvidence"
    )
    DuplicateGroup_1: DuplicateGroup | None = Field(None, alias="DuplicateGroup")
    DuplicateReport_1: DuplicateReport | None = Field(None, alias="DuplicateReport")
    ScenarioKey_1: ScenarioKey | None = Field(None, alias="ScenarioKey")
    RemovedItem_1: RemovedItem | None = Field(None, alias="RemovedItem")
    StorageScenario_1: StorageScenario | None = Field(None, alias="StorageScenario")
    StorageTotals_1: StorageTotals | None = Field(None, alias="StorageTotals")
    StorageReport_1: StorageReport | None = Field(None, alias="StorageReport")
    OffboardingRecommendation_1: OffboardingRecommendation | None = Field(
        None, alias="OffboardingRecommendation"
    )
    DuplicateLocation_1: DuplicateLocation | None = Field(
        None, alias="DuplicateLocation"
    )
    OffboardingRow_1: OffboardingRow | None = Field(None, alias="OffboardingRow")
    OffboardingReview_1: OffboardingReview | None = Field(
        None, alias="OffboardingReview"
    )
    Provenance_1: Provenance | None = Field(None, alias="Provenance")
    ExportChunk_1: ExportChunk | None = Field(None, alias="ExportChunk")
    ExportMatch_1: ExportMatch | None = Field(None, alias="ExportMatch")
    ExportAsset_1: ExportAsset | None = Field(None, alias="ExportAsset")
    Health_1: Health | None = Field(None, alias="Health")
    MediaType_1: MediaType | None = Field(None, alias="MediaType")
    SlideMatchType_1: SlideMatchType | None = Field(None, alias="SlideMatchType")
    HitType_1: HitType | None = Field(None, alias="HitType")
    RemovalReason_1: RemovalReason | None = Field(None, alias="RemovalReason")
    ChunkKind_1: ChunkKind | None = Field(None, alias="ChunkKind")
    ChatMessage_1: ChatMessage | None = Field(None, alias="ChatMessage")
    ChatSource_1: ChatSource | None = Field(None, alias="ChatSource")
    ChatAlignment_1: ChatAlignment | None = Field(None, alias="ChatAlignment")
    ChatLog_1: ChatLog | None = Field(None, alias="ChatLog")
