// Search snippets contain only <mark>…</mark> tags (contract). We split on those tags and render the
// rest as plain React text, so nothing else from the server is ever interpreted as HTML.
export function Snippet({ html }: { html: string }) {
  const parts = html.split(/(<mark>|<\/mark>)/);
  let on = false;
  const out: JSX.Element[] = [];
  parts.forEach((p, i) => {
    if (p === "<mark>") on = true;
    else if (p === "</mark>") on = false;
    else if (p) out.push(on ? <mark key={i}>{p}</mark> : <span key={i}>{p}</span>);
  });
  return <>{out}</>;
}
