// Mock mode: fixtures point at /files/... which only exist when the backend runs, so we draw a clearly
// labelled "MOCK IMAGE" SVG. Live mode: if a real image cannot be loaded we draw a NEUTRAL "image not
// available" card (never mock artwork or a MOCK label).
const esc = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

function wrap(text: string, max: number, maxLines: number): string[] {
  const words = text.split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let cur = "";
  for (const w of words) {
    if ((cur + " " + w).trim().length > max) {
      if (cur) lines.push(cur);
      cur = w;
    } else cur = (cur + " " + w).trim();
  }
  if (cur) lines.push(cur);
  if (lines.length > maxLines) {
    const cut = lines.slice(0, maxLines);
    cut[maxLines - 1] = cut[maxLines - 1].replace(/.{0,2}$/, "…");
    return cut;
  }
  return lines;
}

export function placeholderImage(kind: "frame" | "slide", title: string, sub = "", mock = true): string {
  if (!mock) return unavailableImage(kind, sub);
  const lines = wrap(title || (kind === "frame" ? "Key frame" : "Page"), 28, 4);
  const slide = kind === "slide";
  const bg = slide ? "#ffffff" : "#10151c";
  const fg = slide ? "#0b2a4a" : "#e8eef5";
  const textSvg = lines
    .map((l, i) => `<text x="40" y="${120 + i * 46}" font-size="34" font-weight="600" fill="${fg}">${esc(l)}</text>`)
    .join("");
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360" font-family="system-ui,sans-serif">
<rect width="640" height="360" fill="${bg}"/>
${slide ? `<rect width="640" height="14" fill="#1174e6"/>` : `<circle cx="590" cy="44" r="18" fill="none" stroke="#5d7a99" stroke-width="3"/><path d="M584 35 L600 44 L584 53 Z" fill="#5d7a99"/>`}
${textSvg}
<text x="40" y="320" font-size="18" fill="${slide ? "#5a6b7d" : "#8aa1b8"}">${esc(sub)}</text>
<text x="600" y="340" font-size="14" text-anchor="end" fill="#b88a00">MOCK IMAGE</text>
<rect x="0.5" y="0.5" width="639" height="359" fill="none" stroke="#c9d3de"/>
</svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function unavailableImage(kind: "frame" | "slide", sub: string): string {
  const what = kind === "frame" ? "Key frame" : "Page image";
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360" font-family="system-ui,sans-serif">
<rect width="640" height="360" fill="#f3f5f8"/>
<rect x="0.5" y="0.5" width="639" height="359" fill="none" stroke="#c9d3de" stroke-dasharray="6 6"/>
<text x="320" y="170" font-size="24" text-anchor="middle" fill="#5a6b7d">${esc(what)} not available</text>
<text x="320" y="204" font-size="16" text-anchor="middle" fill="#8a99a8">${esc(sub)}</text>
</svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}
