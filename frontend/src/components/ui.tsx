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

/** What source_simulated means: only the SOURCE SYSTEM label is simulated; files and their transcripts are real. */
export const SIMULATED_SOURCE_HINT =
  "Only the source-system label is simulated: there is no live SharePoint / OneDrive / Ericsson Play connection in the MVP. " +
  "The file itself, its hashes and its transcript are real.";

export function SourceBadge({ source }: { source: SourceSystem }) {
  return (
    <Badge tone="blue" title={SIMULATED_SOURCE_HINT}>
      {SOURCE_LABEL[source]} <span className="sim">simulated source</span>
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
