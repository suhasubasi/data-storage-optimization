import type {
  AssetList, AssetDetail, Asset, Job, Timeline, SlideList, SearchResponse, DuplicateReport,
  DuplicateType, StorageReport, OffboardingReview, ExportAsset, Health, SourceSystem,
} from "@contracts/ts/dso-contracts";

/** One method per endpoint in contracts/openapi.yaml. Mock and live both implement it. */
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
  getStorageReport(): Promise<StorageReport>;
  getOffboarding(owner: string): Promise<OffboardingReview>;
  exportAsset(assetId: string): Promise<ExportAsset>;
  exportJsonl(): Promise<string>;
}
