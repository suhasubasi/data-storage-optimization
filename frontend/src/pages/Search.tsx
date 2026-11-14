import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { SearchHit } from "@contracts/ts/dso-contracts";
import { api } from "../api/client";
import { useAsync } from "../lib/useAsync";
import { formatTime } from "../lib/format";
import { MediaImage } from "../components/MediaImage";
import { Snippet } from "../components/Snippet";
import { Badge, Empty, ErrorBox, Loading, PageHeader, SourceBadge } from "../components/ui";
import { IconSearch } from "../components/Icons";

function hitLink(h: SearchHit) {
  if (h.hit_type === "segment") return `/recording/${h.asset_id}?seg=${h.item_id}`;
  if (h.hit_type === "chat") return `/recording/${h.asset_id}?chat=${h.item_id}${h.start != null ? `&t=${h.start}` : ""}`;
  if (h.hit_type === "asset") return h.kind === "video" ? `/recording/${h.asset_id}` : `/document/${h.asset_id}?page=1`;
  return `/document/${h.asset_id}?page=${h.page}`;
}

const HIT_META: Record<SearchHit["hit_type"], { label: string; tone: "blue" | "purple" | "grey" | "green" }> = {
  segment: { label: "Speech", tone: "blue" },
  slide: { label: "Slide text", tone: "purple" },
  chat: { label: "Meeting chat", tone: "green" },
  asset: { label: "Title / file", tone: "grey" },
};

export default function Search() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const [text, setText] = useState(q);
  const [typeFilter, setTypeFilter] = useState<SearchHit["hit_type"] | "all">("all");
  const [sel, setSel] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLOListElement>(null);
  const navigate = useNavigate();

  const res = useAsync(() => api.search(q, 50), [q], q.trim().length > 0);

  useEffect(() => setText(q), [q]);
  useEffect(() => setSel(0), [res.data, typeFilter]);
  useEffect(() => {
    input.current?.focus();
  }, []);

  function submit(e?: FormEvent, value = text) {
    e?.preventDefault();
    const v = value.trim();
    setParams(v ? { q: v } : {});
  }

  const rawHits = res.data?.hits ?? [];
  const counts = useMemo(() => {
    const c: Record<string, number> = { all: rawHits.length, segment: 0, slide: 0, chat: 0, asset: 0 };
    for (const h of rawHits) c[h.hit_type] = (c[h.hit_type] ?? 0) + 1;
    return c;
  }, [rawHits]);

  const hits = useMemo(
    () => (typeFilter === "all" ? rawHits : rawHits.filter((h) => h.hit_type === typeFilter)),
    [rawHits, typeFilter],
  );

  function onKeyDown(e: KeyboardEvent) {
    if (!hits.length || (e.key !== "ArrowDown" && e.key !== "ArrowUp")) return;
    e.preventDefault();
    const inInput = document.activeElement === input.current;
    const next = e.key === "ArrowDown" ? (inInput ? 0 : Math.min(hits.length - 1, sel + 1)) : sel - 1;
    if (next < 0) return input.current?.focus();
    setSel(next);
    list.current?.querySelectorAll<HTMLAnchorElement>("a.hit-card")[next]?.focus();
  }

  return (
    <section className="page-stack page-search" onKeyDown={onKeyDown}>
      <PageHeader
        title="Unified knowledge search"
        lead="Find the moment, slide, or conversation you need. Search across all your recordings and documents."
      />

      <div className="card search-panel">
        <form className="search-hero" onSubmit={submit} role="search">
          <div className="search-field-wrap">
            <IconSearch size={18} />
            <input
              ref={input}
              type="search"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Search spoken phrases, topics, slide bullets, chat questions, or document titles…"
              aria-label="Search query"
            />
          </div>
          <button className="btn btn-primary">Search</button>
        </form>

        <div className="search-subbar">
          <div className="pill-tabs" role="tablist">
            {(["all", "segment", "slide", "chat", "asset"] as const).map((k) => (
              <button
                key={k}
                type="button"
                role="tab"
                aria-selected={typeFilter === k}
                className={`pill-tab ${typeFilter === k ? "on" : ""}`}
                onClick={() => setTypeFilter(k)}
              >
                {k === "all" ? "All matches" : HIT_META[k].label}
                {res.data ? ` (${counts[k] ?? 0})` : ""}
              </button>
            ))}
          </div>
          <span className="muted small">
            <kbd>↑</kbd> <kbd>↓</kbd> navigate · <kbd>Enter</kbd> jump to exact frame/page
          </span>
        </div>
      </div>

      {!q ? (
        <Empty>Enter a keyword above (for example: “disaster”, “school”, “GraalVM”, or “connectivity”).</Empty>
      ) : res.loading ? (
        <Loading label={`Searching index for “${q}”…`} />
      ) : res.error ? (
        <ErrorBox error={res.error} onRetry={res.reload} />
      ) : hits.length === 0 ? (
        <Empty>No matches found in this category for “{q}”.</Empty>
      ) : (
        <div className="search-results">
          <p className="muted small">
            Showing {hits.length} of {res.data!.total} matches for <b>“{res.data!.query}”</b>
          </p>
          <ol className="hits-grid" ref={list}>
            {hits.map((h, i) => {
              const meta = HIT_META[h.hit_type];
              return (
                <li key={`${h.asset_id}:${h.item_id}`}>
                  <a
                    href={hitLink(h)}
                    className={`hit-card card ${i === sel ? "selected" : ""}`}
                    onClick={(e) => {
                      e.preventDefault();
                      navigate(hitLink(h));
                    }}
                    onFocus={() => setSel(i)}
                  >
                    <div className="hit-thumb">
                      <MediaImage
                        url={h.media?.url}
                        kind={h.media?.type === "frame" || h.hit_type === "segment" || h.hit_type === "chat" ? "frame" : "slide"}
                        title={h.text}
                        sub={h.hit_type === "segment" || h.hit_type === "chat" ? `${h.frame_id ?? ""} · ${formatTime(h.start)}` : h.hit_type === "asset" ? h.filename : `page ${h.page}`}
                        alt={`Match preview for ${h.filename}`}
                      />
                    </div>
                    <div className="hit-content">
                      <div className="hit-meta">
                        <Badge tone={meta.tone}>{meta.label}</Badge>
                        <SourceBadge source={h.source_system} />
                        <strong className="hit-file">{h.filename}</strong>
                        <span className="muted small">
                          {h.hit_type === "segment"
                            ? `${formatTime(h.start)} – ${formatTime(h.end)} (${h.frame_id ?? "no frame"})`
                            : h.hit_type === "chat"
                              ? `${h.start != null ? `≈ ${formatTime(h.start)}` : "chat"}`
                              : h.hit_type === "slide"
                                ? `page ${h.page}`
                                : "metadata"}
                        </span>
                      </div>
                      <div className="hit-snippet">
                        <Snippet html={h.snippet || h.text} />
                      </div>
                    </div>
                  </a>
                </li>
              );
            })}
          </ol>
        </div>
      )}
    </section>
  );
}
