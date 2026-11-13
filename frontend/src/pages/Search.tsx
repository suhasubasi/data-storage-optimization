import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { SearchHit } from "@contracts/ts/dso-contracts";
import { api } from "../api/client";
import { USE_MOCKS } from "../api/config";
import { useAsync } from "../lib/useAsync";
import { formatTime } from "../lib/format";
import { MediaImage } from "../components/MediaImage";
import { Snippet } from "../components/Snippet";
import { Badge, Empty, ErrorBox, Loading, PageHeader, SourceBadge } from "../components/ui";

const EXAMPLES = ["handover", "energy saving", "power per site", "dropped calls", "sleep modes"];

function hitLink(h: SearchHit) {
  return h.hit_type === "segment" ? `/recording/${h.asset_id}?seg=${h.item_id}` : `/document/${h.asset_id}?page=${h.page}`;
}

export default function Search() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const [text, setText] = useState(q);
  const [sel, setSel] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLOListElement>(null);
  const navigate = useNavigate();
  const res = useAsync(() => api.search(q, 20), [q], q.trim().length > 0);

  useEffect(() => setText(q), [q]);
  useEffect(() => setSel(0), [res.data]);
  useEffect(() => {
    input.current?.focus();
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === "/" && document.activeElement !== input.current) {
        e.preventDefault();
        input.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function submit(e?: FormEvent, value = text) {
    e?.preventDefault();
    const v = value.trim();
    setParams(v ? { q: v } : {});
  }

  const hits = res.data?.hits ?? [];
  function onKeyDown(e: KeyboardEvent) {
    if (!hits.length || (e.key !== "ArrowDown" && e.key !== "ArrowUp")) return;
    e.preventDefault();
    const inInput = document.activeElement === input.current;
    const next = e.key === "ArrowDown" ? (inInput ? 0 : Math.min(hits.length - 1, sel + 1)) : sel - 1;
    if (next < 0) return input.current?.focus();
    setSel(next);
    list.current?.querySelectorAll<HTMLAnchorElement>("a.hit")[next]?.focus();
  }

  return (
    <section onKeyDown={onKeyDown}>
      <PageHeader
        title="Search"
        lead="One box over every transcript sentence and every slide. Each result shows the text, the frame or slide it belongs to, and the timestamp or page."
      />
      <form className="search-bar" onSubmit={submit} role="search">
        <input
          ref={input}
          className="search-input"
          type="search"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Search recordings and documents…  (press / to focus)"
          aria-label="Search recordings and documents"
        />
        <button className="btn primary">Search</button>
      </form>
      <div className="chips">
        <span className="muted small">Try:</span>
        {EXAMPLES.map((x) => (
          <button key={x} className="chip" onClick={() => submit(undefined, x)}>
            {x}
          </button>
        ))}
        <span className="muted small kbd-hint">
          <kbd>↑</kbd> <kbd>↓</kbd> to move, <kbd>Enter</kbd> to open
        </span>
      </div>

      {!q ? (
        <Empty>Type a word or phrase and press Enter. {USE_MOCKS && "(Mock mode searches the fixture manifests in the browser; live mode uses SQLite FTS5.)"}</Empty>
      ) : res.loading ? (
        <Loading label={`Searching for “${q}”…`} />
      ) : res.error ? (
        <ErrorBox error={res.error} onRetry={res.reload} />
      ) : hits.length === 0 ? (
        <Empty>No results for “{q}”. Try a shorter word, or check that the files are processed.</Empty>
      ) : (
        <>
          <p className="muted">
            {res.data!.total} result{res.data!.total === 1 ? "" : "s"} for “{res.data!.query}”
          </p>
          <ol className="hits" ref={list}>
            {hits.map((h, i) => (
              <li key={`${h.asset_id}:${h.item_id}`}>
                <a
                  href={hitLink(h)}
                  className={`hit card ${i === sel ? "sel" : ""}`}
                  onClick={(e) => {
                    e.preventDefault();
                    navigate(hitLink(h));
                  }}
                  onFocus={() => setSel(i)}
                >
                  <div className="hit-media">
                    <MediaImage
                      url={h.media?.url}
                      kind={h.hit_type === "segment" ? "frame" : "slide"}
                      title={h.text}
                      sub={h.hit_type === "segment" ? `${h.frame_id ?? ""} · ${formatTime(h.media?.t_start)}` : `page ${h.page}`}
                      alt={h.hit_type === "segment" ? `Frame ${h.frame_id}` : `Page ${h.page}`}
                    />
                  </div>
                  <div className="hit-body">
                    <div className="hit-meta">
                      <Badge tone={h.hit_type === "segment" ? "blue" : "purple"}>{h.hit_type === "segment" ? "Recording" : "Slide"}</Badge>
                      <b>{h.filename}</b>
                      <SourceBadge source={h.source_system} />
                      <span className="muted small">owner {h.owner}</span>
                    </div>
                    <p className="hit-text">
                      <Snippet html={h.snippet} />
                    </p>
                    <div className="hit-where">
                      {h.hit_type === "segment" ? (
                        <>
                          ⏱ <b>{formatTime(h.start)}</b>–{formatTime(h.end)} · frame <code>{h.frame_id ?? "—"}</code> → jump to this moment
                        </>
                      ) : (
                        <>
                          📄 page <b>{h.page}</b> → open this page
                        </>
                      )}
                      <span className="muted small"> · score {h.score}</span>
                    </div>
                  </div>
                </a>
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  );
}
