import { useEffect, useRef, useState, type FormEvent } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api } from "./api/client";
import { useAsync } from "./lib/useAsync";
import {
  IconChart,
  IconCode,
  IconCopy,
  IconDoc,
  IconLibrary,
  IconPlay,
  IconSearch,
  IconSettings,
  IconShield,
  IconUpload,
  IconUsers,
} from "./components/Icons";
import Library from "./pages/Library";
import Search from "./pages/Search";
import Recording from "./pages/Recording";
import DocumentView from "./pages/Document";
import Duplicates from "./pages/Duplicates";
import Storage from "./pages/Storage";
import Offboarding from "./pages/Offboarding";
import Export from "./pages/Export";
import SettingsPage from "./pages/Settings";
import Overview from "./pages/Overview";

interface NavItem {
  path: string;
  label: string;
  icon: JSX.Element;
  el: JSX.Element;
  param?: boolean;
}

const NAV_GROUPS: { heading: string; items: NavItem[] }[] = [
  {
    heading: "Workspace",
    items: [
      { path: "overview", label: "Impact overview", icon: <IconChart />, el: <Overview /> },
      { path: "library", label: "Library & ingest", icon: <IconLibrary />, el: <Library /> },
      { path: "search", label: "Unified search", icon: <IconSearch />, el: <Search /> },
    ],
  },
  {
    heading: "Media & slides",
    items: [
      { path: "recording", label: "Recording studio", icon: <IconPlay />, el: <Recording />, param: true },
      { path: "document", label: "Document / slides", icon: <IconDoc />, el: <DocumentView />, param: true },
    ],
  },
  {
    heading: "Storage governance",
    items: [
      { path: "duplicates", label: "Duplicates", icon: <IconCopy />, el: <Duplicates /> },
      { path: "storage", label: "Storage optimizer", icon: <IconChart />, el: <Storage /> },
      { path: "offboarding", label: "Offboarding review", icon: <IconUsers />, el: <Offboarding /> },
    ],
  },
  {
    heading: "AI & runtime",
    items: [
      { path: "export", label: "AI-ready export", icon: <IconCode />, el: <Export /> },
      { path: "settings", label: "Runtime settings", icon: <IconSettings />, el: <SettingsPage /> },
    ],
  },
];

const ALL_ITEMS = NAV_GROUPS.flatMap((g) => g.items);

export default function App() {
  const health = useAsync(() => api.health(), []);
  const runtime = useAsync(() => api.getSettings(), []);
  const [quickQuery, setQuickQuery] = useState("");
  const quickRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes((document.activeElement as HTMLElement)?.tagName ?? "")) {
        e.preventDefault();
        quickRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function onQuickSearch(e: FormEvent) {
    e.preventDefault();
    const q = quickQuery.trim();
    navigate(q ? `/search?q=${encodeURIComponent(q)}` : "/search");
  }

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand">
          <div className="brand-mark" aria-hidden>DSO</div>
          <div className="brand-copy">
            <strong>DSO workspace</strong>
            <span>Data Storage Optimization</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          {NAV_GROUPS.map((g) => (
            <div key={g.heading} className="nav-group">
              <div className="nav-group-label">{g.heading}</div>
              {g.items.map((item) => (
                <NavLink key={item.path} to={`/${item.path}`} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
                  <span className="nav-icon">{item.icon}</span>
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className="safety-pill">
            <IconShield />
            <span>Originals stay protected</span>
          </div>
          <details className="rail-disclosure">
            <summary>About this workspace</summary>
            <p>Originals are never modified or deleted. Source labels (SharePoint, OneDrive, Ericsson Play) are simulated; transcripts, slides, speakers, and byte counts are real.</p>
            <p>Local workspace connected to your backend. Not an official Ericsson product.</p>
          </details>
          <p className="muted-rail">LOCAL WORKSPACE</p>
        </div>
      </aside>

      <div className="workspace-col">
        <header className="topbar">
          <form className="topbar-search" onSubmit={onQuickSearch} role="search">
            <IconSearch size={16} />
            <input
              ref={quickRef}
              type="search"
              value={quickQuery}
              onChange={(e) => setQuickQuery(e.target.value)}
              placeholder="Search your workspace…"
              aria-label="Global quick search"
            />
            <kbd aria-hidden="true">/</kbd>
            {quickQuery && (
              <button type="submit" className="btn btn-primary btn-xs">
                Find
              </button>
            )}
          </form>

          <div className="topbar-meta">
            {runtime.data && (
              <NavLink to="/settings" className="status-chip" title="Speech-to-text configuration for new jobs">
                <span>STT:</span>
                <code>{runtime.data.effective_model}</code>
                <span>· {runtime.data.effective_device}</span>
              </NavLink>
            )}

            {health.loading ? (
              <span className="status-chip checking">API checking…</span>
            ) : health.error ? (
              <span className="status-chip offline" title={health.error.message}>
                <i className="dot" /> Backend offline
              </span>
            ) : (
              <span className="status-chip live">
                <i className="dot" /> Live API · v{health.data?.version}
              </span>
            )}

            <button type="button" className="btn btn-primary btn-sm" onClick={() => navigate("/library?upload=1")}>
              <IconUpload size={15} /> Upload file
            </button>
          </div>
        </header>

        <main className="main-canvas">
          <Routes>
            <Route path="/" element={<Navigate to="/overview" replace />} />
            {ALL_ITEMS.map((s) => (
              <Route key={s.path} path={`/${s.path}`} element={s.el} />
            ))}
            {ALL_ITEMS.filter((s) => s.param).map((s) => (
              <Route key={`${s.path}-id`} path={`/${s.path}/:assetId`} element={s.el} />
            ))}
            <Route path="*" element={<Navigate to="/library" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
