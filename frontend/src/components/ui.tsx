import type { ReactNode } from "react";
import type { SourceSystem } from "@contracts/ts/dso-contracts";
import { ApiError } from "../api/errors";
import { SOURCE_LABEL } from "../lib/format";

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="state" role="status" aria-live="polite">
      <span className="spinner" aria-hidden /> {label}
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  const code = error instanceof ApiError ? error.code : null;
  return (
    <div className="state error" role="alert">
      <strong>Something went wrong.</strong> {error.message}
      {code && <span className="muted"> (code: {code})</span>}
      {onRetry && (
        <button className="btn small" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="state empty">{children}</div>;
}

export function PageHeader({ title, lead, children }: { title: string; lead?: ReactNode; children?: ReactNode }) {
  return (
    <header className="page-header">
      <div>
        <h2>{title}</h2>
        {lead && <p className="lead">{lead}</p>}
      </div>
      {children && <div className="page-actions">{children}</div>}
    </header>
  );
}

type Tone = "blue" | "green" | "amber" | "red" | "grey" | "purple";
export function Badge({ tone = "grey", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span className={`badge-pill ${tone}`} title={title}>
      {children}
    </span>
  );
}

export function SourceBadge({ source }: { source: SourceSystem }) {
  return (
    <Badge tone="blue" title="Source label is simulated in the MVP (no live connector)">
      {SOURCE_LABEL[source]} <span className="sim">sim</span>
    </Badge>
  );
}

export function Callout({ tone = "info", title, children }: { tone?: "info" | "warn" | "safe"; title?: string; children: ReactNode }) {
  return (
    <div className={`callout ${tone}`}>
      {title && <strong>{title} </strong>}
      {children}
    </div>
  );
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}
