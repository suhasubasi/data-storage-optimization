import type { ReactNode } from "react";
import type { SourceSystem } from "@contracts/ts/dso-contracts";
import { ApiError } from "../api/errors";
import { SOURCE_LABEL } from "../lib/format";

export type Tone = "grey" | "blue" | "green" | "amber" | "red" | "purple" | "teal";

export const SIMULATED_SOURCE_HINT =
  "Source systems (SharePoint, OneDrive, Ericsson Play) are simulated labels; file hashes, slides, transcripts, speakers, and byte sizes are real.";

export function Badge({ tone = "grey", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {children}
    </span>
  );
}

const SOURCE_TONE: Record<SourceSystem, Tone> = { sharepoint: "blue", onedrive: "teal", ericsson_play: "purple" };
export function SourceBadge({ source }: { source: SourceSystem }) {
  return (
    <Badge tone={SOURCE_TONE[source]} title="Simulated source label; file bytes are real">
      {SOURCE_LABEL[source]}
    </Badge>
  );
}

export function PageHeader({ title, lead, actions }: { title: string; lead: string; actions?: ReactNode }) {
  return (
    <header className="page-head">
      <div className="page-head-copy">
        <span className="page-eyebrow">YOUR KNOWLEDGE, CONNECTED</span>
        <h1>{title}</h1>
        <p className="page-lead">{lead}</p>
      </div>
      {actions && <div className="page-head-actions">{actions}</div>}
      <div className="page-orbit" aria-hidden="true"><i /><i /><i /></div>
    </header>
  );
}

export function StatCard({
  label,
  value,
  sub,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "default" | "accent" | "safe" | "warn";
}) {
  return (
    <div className={`stat-card stat-${tone}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

export function Callout({
  tone = "info",
  title,
  children,
}: {
  tone?: "info" | "warn" | "safe";
  title?: string;
  children: ReactNode;
}) {
  return (
    <div className={`callout callout-${tone}`} role={tone === "warn" ? "alert" : "note"}>
      {title && <strong className="callout-title">{title}</strong>}
      <div className="callout-body">{children}</div>
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="loading-box" aria-live="polite">
      <span className="spinner" aria-hidden />
      <span>{label}</span>
    </div>
  );
}

export function Empty({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty-box">
      <p>{children}</p>
      {action}
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  const api = error instanceof ApiError ? error : null;
  return (
    <div className="error-box" role="alert">
      <div className="error-box-head">
        <strong>{api ? `Error (${api.code})` : "Something went wrong"}</strong>
        {api && api.status > 0 && <Badge tone="red">HTTP {api.status}</Badge>}
      </div>
      <p>{error.message}</p>
      {onRetry && (
        <button className="btn btn-secondary btn-sm" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}
