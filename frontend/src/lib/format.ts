import type { SourceSystem, AssetKind } from "@contracts/ts/dso-contracts";

/** Decimal units (1 MB = 1,000,000 bytes), same as disk vendors and the storage report. */
export function formatBytes(n: number | null | undefined, digits = 1): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const sign = n < 0 ? "−" : "";
  let v = Math.abs(n);
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (v >= 1000 && i < units.length - 1) {
    v /= 1000;
    i++;
  }
  return `${sign}${i === 0 ? v.toFixed(0) : v.toFixed(digits)} ${units[i]}`;
}

/** Exact bytes with thin separators, for formulas. */
export function exactBytes(n: number): string {
  const sign = n < 0 ? "−" : "";
  return `${sign}${Math.abs(n).toLocaleString("en-US")} B`;
}

export function formatPct(p: number | null | undefined, digits = 2): string {
  if (p === null || p === undefined) return "n/a";
  return `${p < 0 ? "−" : ""}${Math.abs(p).toFixed(digits)} %`;
}

export function formatTime(sec: number | null | undefined): string {
  if (sec === null || sec === undefined) return "—";
  const s = Math.max(0, Math.floor(sec));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-GB", { timeZone: "Europe/Stockholm", dateStyle: "medium", timeStyle: "short" }) + " (Stockholm)";
}

export const SOURCE_LABEL: Record<SourceSystem, string> = {
  sharepoint: "SharePoint",
  onedrive: "OneDrive",
  ericsson_play: "Ericsson Play",
};

export const KIND_LABEL: Record<AssetKind, string> = { video: "Recording", document: "Document" };

export const shortHash = (h: string | null | undefined, n = 12) => (h ? `${h.slice(0, n)}…` : "—");

export function downloadText(filename: string, text: string, mime = "application/json") {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
