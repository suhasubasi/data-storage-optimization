// MOCKS — Stream 1 only. Typed views of the frozen fixtures in contracts/fixtures/.
// Do not edit the JSON here; regenerate with `python3 contracts/scripts/make_fixtures.py`.
// Image URLs in fixtures point at /files/... which do not exist in mock mode: show a placeholder.
import type {
  AssetList, AssetDetail, Job, Timeline, SlideList, SearchResponse, DuplicateReport,
  StorageReport, OffboardingReview, ExportAsset, Asset, Health,
} from "@contracts/ts/dso-contracts";

import health from "@contracts/fixtures/health.json";
import assets from "@contracts/fixtures/assets.json";
import uploadResponse from "@contracts/fixtures/asset_upload_response.json";
import assetDetailVideo from "@contracts/fixtures/asset_detail_video.json";
import assetDetailDocument from "@contracts/fixtures/asset_detail_document.json";
import job from "@contracts/fixtures/job.json";
import jobRunning from "@contracts/fixtures/job_running.json";
import timeline from "@contracts/fixtures/timeline.json";
import slides from "@contracts/fixtures/slides.json";
import search from "@contracts/fixtures/search.json";
import duplicates from "@contracts/fixtures/duplicates.json";
import storageReport from "@contracts/fixtures/storage_report.json";
import offboarding from "@contracts/fixtures/offboarding.json";
import exportAsset from "@contracts/fixtures/export_asset.json";

export const mocks = {
  health: health as Health,
  assets: assets as AssetList,
  uploadResponse: uploadResponse as Asset,
  assetDetailVideo: assetDetailVideo as AssetDetail,
  assetDetailDocument: assetDetailDocument as AssetDetail,
  job: job as Job,
  jobRunning: jobRunning as Job,
  timeline: timeline as Timeline,
  slides: slides as SlideList,
  search: search as SearchResponse,
  duplicates: duplicates as DuplicateReport,
  storageReport: storageReport as StorageReport,
  offboarding: offboarding as OffboardingReview,
  exportAsset: exportAsset as ExportAsset,
};
