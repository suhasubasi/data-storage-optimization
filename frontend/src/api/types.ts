import type {
  AssetList, AssetDetail, Asset, Job, Timeline, SlideList, SearchResponse, DuplicateReport,
  DuplicateType, StorageReport, OffboardingReview, ExportAsset, Health, SourceSystem, ChatLog,
  Settings, SettingsUpdate,
} from "@contracts/ts/dso-contracts";

/** One method per endpoint in contracts/openapi.yaml. */
export interface Api {
  health(): Promise<Health>;
  listAssets(owner?: string): Promise<AssetList>;
  getAsset(assetId: string): Promise<AssetDetail>;
  uploadAsset(file: File, sourceSystem: SourceSystem, owner: string): Promise<Asset>;
  processAsset(assetId: string): Promise<Job>;
  getJob(jobId: string): Promise<Job>;
  getTimeline(assetId: string): Promise<Timeline>;
  getSlides(assetId: string): Promise<SlideList>;
  search(q: string, limit?: number): Promise<SearchResponse>;
  getDuplicates(type?: DuplicateType): Promise<DuplicateReport>;
  /** includeTestData=false (default): only real uploaded files; generated test files are left out. */
  getStorageReport(includeTestData?: boolean): Promise<StorageReport>;
  getOffboarding(owner: string): Promise<OffboardingReview>;
  exportAsset(assetId: string): Promise<ExportAsset>;
  exportJsonl(): Promise<string>;
  /** REC v1.2: meeting chat of a recording (empty messages if none attached). */
  getChat(assetId: string): Promise<ChatLog>;
  attachChat(assetId: string, file: File, recordingStart?: string): Promise<ChatLog>;
  /** REC v1.4: Whisper model + device for jobs started after a change (never re-processes on its own). */
  getSettings(): Promise<Settings>;
  putSettings(body: SettingsUpdate): Promise<Settings>;
}
