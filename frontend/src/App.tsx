// Stream 1 owns everything in frontend/. Eight screens from the design Page.
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { api } from "./api/client";
import { useAsync } from "./lib/useAsync";
import Library from "./pages/Library";
import Search from "./pages/Search";
import Recording from "./pages/Recording";
import DocumentView from "./pages/Document";
import Duplicates from "./pages/Duplicates";
import Storage from "./pages/Storage";
import Offboarding from "./pages/Offboarding";
import Export from "./pages/Export";
import SettingsPage from "./pages/Settings";

const SCREENS = [
  { path: "library", label: "Library & ingest", icon: "⬆", el: <Library /> },
  { path: "search", label: "Search", icon: "⌕", el: <Search /> },
  { path: "recording", label: "Recording timeline", icon: "▶", el: <Recording />, param: true },
  { path: "document", label: "Document / slides", icon: "▤", el: <DocumentView />, param: true },
  { path: "duplicates", label: "Duplicates", icon: "⧉", el: <Duplicates /> },
  { path: "storage", label: "Storage report", icon: "◔", el: <Storage /> },
  { path: "offboarding", label: "Offboarding review", icon: "⇥", el: <Offboarding /> },
  { path: "export", label: "AI-ready export", icon: "{ }", el: <Export /> },
  { path: "settings", label: "Settings", icon: "⚙", el: <SettingsPage /> },
];

function BackendStatus() {
  const h = useAsync(() => api.health(), []);
  if (h.loading) return <p className="mode">LIVE API · checking…</p>;
  return h.error ? (
    <p className="mode down" title={h.error.message}>
      LIVE API · backend offline
    </p>
  ) : (
    <p className="mode live">LIVE API · v{h.data?.version}</p>
  );
}

export default function App() {
  return (
    <div className="shell">
      <aside className="nav">
        <h1>Data Storage Optimization</h1>
        <p className="sub">Hackathon MVP · local only</p>
        <BackendStatus />
        <nav aria-label="Screens">
          {SCREENS.map((s) => (
            <NavLink key={s.path} to={`/${s.path}`}>
              <span className="icon" aria-hidden>
                {s.icon}
              </span>
              {s.label}
            </NavLink>
          ))}
        </nav>
        <div className="nav-foot">
          <p>Source systems (SharePoint, OneDrive, Ericsson Play) are simulated labels; the files and transcripts are real.</p>
          <p>Nothing is ever deleted.</p>
          <p className="disclaimer">Team prototype for the Ericsson Data Storage Optimization challenge. Not an official Ericsson product.</p>
        </div>
      </aside>
      <main className="content">
        <Routes>
          <Route path="/" element={<Navigate to="/library" replace />} />
          {SCREENS.map((s) => (
            <Route key={s.path} path={`/${s.path}`} element={s.el} />
          ))}
          {SCREENS.filter((s) => s.param).map((s) => (
            <Route key={`${s.path}-id`} path={`/${s.path}/:assetId`} element={s.el} />
          ))}
          <Route path="*" element={<Navigate to="/library" replace />} />
        </Routes>
      </main>
    </div>
  );
}
