import { useEffect, useRef, useState, type FormEvent } from "react";
import type { ChatMessage } from "@contracts/ts/dso-contracts";
import { api } from "../api/client";
import { useAsync } from "../lib/useAsync";
import { formatBytes, formatTime } from "../lib/format";
import { Badge, Callout, Empty, ErrorBox, Loading } from "./ui";

export function ChatPanel({
  assetId,
  focusId,
  onJump,
  embedded = false,
}: {
  assetId: string;
  focusId?: string | null;
  onJump: (t: number) => void;
  embedded?: boolean;
}) {
  const chat = useAsync(() => api.getChat(assetId), [assetId]);
  const [file, setFile] = useState<File | null>(null);
  const [start, setStart] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<Error | null>(null);
  const refs = useRef<Record<string, HTMLLIElement | null>>({});

  useEffect(() => {
    if (focusId && chat.data) setTimeout(() => refs.current[focusId]?.scrollIntoView({ block: "center", behavior: "smooth" }), 80);
  }, [focusId, chat.data]);

  async function attach(e: FormEvent) {
    e.preventDefault();
    if (!file) return setErr(new Error("Choose a .msg or .txt chat file first."));
    setBusy(true);
    setErr(null);
    try {
      await api.attachChat(assetId, file, start.trim() || undefined);
      setFile(null);
      chat.reload();
    } catch (x) {
      setErr(x as Error);
    } finally {
      setBusy(false);
    }
  }

  const log = chat.data;
  const msgs: ChatMessage[] = log?.messages ?? [];
  return (
    <div className={embedded ? "chat-embedded" : "card chat-panel"}>
      <div className="panel-head-inline">
        <span className="small muted">{msgs.length} {msgs.length === 1 ? "message" : "messages"}</span>
        {log?.alignment && (
          <Badge tone={log.alignment.status === "estimated" ? "amber" : "grey"} title={log.alignment.note}>
            {log.alignment.status === "estimated" ? "times estimated (±1 min)" : "times unknown"}
          </Badge>
        )}
      </div>

      {chat.loading ? (
        <Loading label="Loading meeting chat…" />
      ) : chat.error ? (
        <ErrorBox error={chat.error} onRetry={chat.reload} />
      ) : (
        <>
          {log?.source && log.alignment && (
            <Callout tone="info">
              From <b>{log.source.filename}</b> ({formatBytes(log.source.bytes)}, sha256 <code>{log.source.sha256.slice(0, 10)}…</code>). {log.alignment.note}
            </Callout>
          )}
          {msgs.length === 0 ? (
            <Empty>No meeting chat attached to this recording yet.</Empty>
          ) : (
            <ol className="chat-feed">
              {msgs.map((m) => (
                <li key={m.id} ref={(el) => (refs.current[m.id] = el)} className={focusId === m.id ? "active" : ""}>
                  <button
                    type="button"
                    className="chat-row"
                    disabled={m.t === null}
                    onClick={() => m.t !== null && onJump(m.t)}
                    title={m.t === null ? "No estimated timestamp in recording" : "Jump video & slide to this chat moment"}
                  >
                    <span className="chat-time">
                      <span>{m.clock}</span>
                      <span className="muted small">{m.t === null ? "—" : `≈ ${formatTime(m.t)}`}</span>
                    </span>
                    <span className="chat-body">
                      <strong>{m.author}</strong>
                      <span>{m.text ? m.text : <span className="muted">(no text)</span>}</span>
                      {m.has_image && <span className="muted small">contained image (not stored)</span>}
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          )}
        </>
      )}

      <form className="chat-upload-form" onSubmit={attach}>
        <label className="field">
          <span>{msgs.length > 0 ? "Replace meeting chat" : "Attach meeting chat"} (.msg or .txt)</span>
          <input type="file" accept=".msg,.txt" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        <label className="field">
          <span>Recording start (optional local ISO)</span>
          <input value={start} onChange={(e) => setStart(e.target.value)} placeholder="e.g. 2023-03-29T15:35:03" />
        </label>
        <button className="btn btn-secondary btn-sm" disabled={busy}>
          {busy ? "Attaching…" : "Attach chat"}
        </button>
        {err && <span className="err-inline">{err.message}</span>}
      </form>
    </div>
  );
}
