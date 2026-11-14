import type { ReactNode } from "react";

const TOKEN_RE = /<mark>([\s\S]*?)<\/mark>/gi;

export function Snippet({ html }: { html: string }) {
  const out: ReactNode[] = [];
  let last = 0;
  let k = 0;
  TOKEN_RE.lastIndex = 0;
  for (let m = TOKEN_RE.exec(html); m; m = TOKEN_RE.exec(html)) {
    if (m.index > last) out.push(html.slice(last, m.index));
    out.push(<mark key={k++}>{m[1]}</mark>);
    last = m.index + m[0].length;
  }
  if (last < html.length) out.push(html.slice(last));
  return <>{out}</>;
}
