import type { AssetDetail } from "@contracts/ts/dso-contracts";
import { exportUrls } from "../api/config";
import { IconDownload } from "./Icons";

export function Downloads({ detail, compact = false }: { detail: AssetDetail; compact?: boolean }) {
  const a = detail.asset;
  if (a.status !== "ready") return null;
  const u = exportUrls(a.id);
  const unique = detail.derived?.unique_slide_count ?? null;
  const source = detail.derived?.source_frame_count ?? null;
  const isVideo = a.kind === "video";
  return (
    <div className={compact ? "downloads-bar compact" : "downloads-bar"}>
      <a className="btn btn-secondary btn-sm" href={u.txt} download>
        <IconDownload /> Transcript .txt {isVideo ? "(timestamps)" : "(by page)"}
      </a>
      {isVideo && (
        <a className="btn btn-secondary btn-sm" href={u.txtPlain} download>
          <IconDownload /> Plain text .txt
        </a>
      )}
      {isVideo && unique !== null ? (
        <>
          <a className="btn btn-secondary btn-sm" href={u.pptx} download>
            <IconDownload /> Unique slides .pptx ({unique})
          </a>
          <a className="btn btn-secondary btn-sm" href={u.pdf} download>
            <IconDownload /> Unique slides .pdf ({unique})
          </a>
        </>
      ) : isVideo ? (
        <span className="muted small">Unique slide deck (.pptx/.pdf) unlocks after slide pass runs.</span>
      ) : null}
      <a className="btn btn-ghost btn-sm" href={u.json} target="_blank" rel="noreferrer">
        Raw JSON ↗
      </a>
      {!compact && isVideo && unique !== null && source !== null && (
        <span className="muted small">
          {unique} unique slides distilled from {source} extracted frames.
        </span>
      )}
    </div>
  );
}
