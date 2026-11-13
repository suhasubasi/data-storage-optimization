import type { AssetDetail } from "@contracts/ts/dso-contracts";
import { exportUrls } from "../api/config";

/** Download links for one processed file. Files are built by the backend on request from the real derived
 *  data (nothing extra is stored). Slide decks need the unique-slide pass (videos only). */
export function Downloads({ detail, compact = false }: { detail: AssetDetail; compact?: boolean }) {
  const a = detail.asset;
  if (a.status !== "ready") return null;
  const u = exportUrls(a.id);
  const unique = detail.derived?.unique_slide_count ?? null;
  const source = detail.derived?.source_frame_count ?? null;
  const isVideo = a.kind === "video";
  return (
    <div className={compact ? "downloads compact" : "downloads"}>
      <a className="btn small" href={u.txt} download>
        Transcript .txt {isVideo ? "(with timestamps)" : "(by page)"}
      </a>
      {isVideo && (
        <a className="btn small" href={u.txtPlain} download>
          Transcript .txt (plain text)
        </a>
      )}
      {isVideo && unique !== null ? (
        <>
          <a className="btn small" href={u.pptx} download>
            Unique slides .pptx ({unique})
          </a>
          <a className="btn small" href={u.pdf} download>
            Unique slides .pdf ({unique})
          </a>
        </>
      ) : isVideo ? (
        <span className="muted small">Slide deck: available after the unique-slide pass has run for this recording.</span>
      ) : null}
      <a className="btn small ghost" href={u.json} target="_blank" rel="noreferrer">
        JSON
      </a>
      {!compact && isVideo && unique !== null && source !== null && (
        <span className="muted small">
          {unique} unique slides from {source} captured key frames. Each slide appears once, with every time range it was on screen.
        </span>
      )}
    </div>
  );
}
