const esc = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export function unavailableImage(kind: "frame" | "slide", sub: string): string {
  const what = kind === "frame" ? "Key frame" : "Page image";
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360" font-family="system-ui,sans-serif">
<rect width="640" height="360" fill="#f1f5f9"/>
<rect x="0.5" y="0.5" width="639" height="359" fill="none" stroke="#cbd5e1" stroke-dasharray="6 6"/>
<text x="320" y="170" font-size="22" text-anchor="middle" fill="#475569">${esc(what)} not available</text>
<text x="320" y="204" font-size="14" text-anchor="middle" fill="#94a3b8">${esc(sub)}</text>
</svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}
