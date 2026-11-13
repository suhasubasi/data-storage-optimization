import { useEffect, useRef, useState, type FormEvent } from "react";
import type { ChatMessage } from "@contracts/ts/dso-contracts";
import { api } from "../api/client";
import { useAsync } from "../lib/useAsync";
import { formatBytes, formatTime } from "../lib/format";
import { Badge, Callout, Empty, ErrorBox, Loading } from "./ui";

/** REC v1.2: the meeting chat attached to a recording. Times are ESTIMATES (chat clock minus recording start). */
export function ChatPanel({ assetId, focusId, onJump }: { assetId: string; focusId?: string | null; onJump: (t: number) => void }) {
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
    if (!file) return setErr(new Error("Choose the chat file (.msg or .txt) first."));
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
    <div className="card chat-card">
      <div className="card-head">
        <h3>Meeting chat {msgs.length > 0 && <span className="muted small">({msgs.length} messages)</span>}</h3>
        {log?.alignment && (
          <Badge tone={log.alignment.status === "estimated" ? "amber" : "grey"} title={log.alignment.note}>
            {log.alignment.status === "estimated" ? "times estimated (±1 min)" : "times unknown"}
          </Badge>
        )}
      </div>
      {chat.loading ? (
        <Loading label="Loading chat…" />
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
            <Empty>No meeting chat attached to this recording.</Empty>
          ) : (
            <ol className="chat-list">
              {msgs.map((m) => (
                <li key={m.id} ref={(el) => (refs.current[m.id] = el)} className={focusId === m.id ? "on" : ""}>
                  <button className="seg" disabled={m.t === null} onClick={() => m.t !== null && onJump(m.t)} title={m.t === null ? "No place in the recording" : "Jump to about this moment"}>
                    <span className="seg-time">
                      {m.clock}
                      <br />
                      <span className="muted small">{m.t === null ? "—" : `≈ ${formatTime(m.t)}`}</span>
                    </span>
                    <span className="seg-text">
                      <b>{m.author}</b>
                      <br />
                      {m.text ? m.text : <span className="muted">(no text)</span>}
                      {m.has_image && <span className="muted small"> · contained a picture (not stored)</span>}
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          )}
        </>
      )}
      <form className="chat-attach" onSubmit={attach}>
        <label>
          {msgs.length > 0 ? "Replace chat" : "Attach chat"} (.msg or .txt with “[HH:MM] Name” lines)
          <input type="file" accept=".msg,.txt" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        <label>
          Recording start (optional, local time)
          <input value={start} onChange={(e) => setStart(e.target.value)} placeholder="read from the file name, e.g. 2024-01-05T09:15:03" />
        </label>
        <button className="btn small" disabled={busy}>
          {busy ? "Attaching…" : "Attach"}
        </button>
        {err && <span className="err-text">{err.message}</span>}
      </form>
    </div>
  );
}
