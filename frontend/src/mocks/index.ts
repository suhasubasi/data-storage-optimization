// MOCKS — Stream 1 only. Typed views of the frozen fixtures in contracts/fixtures/.
// Do not edit the JSON here; regenerate with `python3 contracts/scripts/make_fixtures.py`.
// Image URLs in fixtures point at /files/... which do not exist in mock mode: we draw a labelled placeholder.
import type {
  AssetList, AssetDetail, Job, Timeline, SlideList, SearchResponse, DuplicateReport,
  StorageReport, OffboardingReview, ExportAsset, Asset, Health, Manifest, ErrorResponse,
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
import error from "@contracts/fixtures/error.json";
import exportJsonl from "@contracts/fixtures/export.jsonl?raw";
import m01 from "@contracts/fixtures/manifests/a_01.manifest.json";
import m02 from "@contracts/fixtures/manifests/a_02.manifest.json";
import m03 from "@contracts/fixtures/manifests/a_03.manifest.json";
import m04 from "@contracts/fixtures/manifests/a_04.manifest.json";

const as = <T,>(v: unknown) => v as T;

export const mocks = {
  health: as<Health>(health),
  assets: as<AssetList>(assets),
  uploadResponse: as<Asset>(uploadResponse),
  assetDetailVideo: as<AssetDetail>(assetDetailVideo),
  assetDetailDocument: as<AssetDetail>(assetDetailDocument),
  job: as<Job>(job),
  jobRunning: as<Job>(jobRunning),
  timeline: as<Timeline>(timeline),
  slides: as<SlideList>(slides),
  search: as<SearchResponse>(search),
  duplicates: as<DuplicateReport>(duplicates),
  storageReport: as<StorageReport>(storageReport),
  offboarding: as<OffboardingReview>(offboarding),
  exportAsset: as<ExportAsset>(exportAsset),
  error: as<ErrorResponse>(error),
  exportJsonl: exportJsonl as string,
  /** Example pipeline hand-off manifests, keyed by asset id. */
  manifests: Object.fromEntries(
    [m01, m02, m03, m04].map((m) => [(m as Manifest).asset_id, as<Manifest>(m)]),
  ) as Record<string, Manifest>,
};
