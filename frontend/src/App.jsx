import { useState } from "react";
import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import Apps from "./pages/Apps";
import Contracts from "./pages/Contracts";
import Licenses from "./pages/Licenses";
import SyncStatus from "./pages/SyncStatus";
import Settings from "./pages/Settings";

export default function App() {
  const [page, setPage] = useState("dashboard");

  const pages = {
    dashboard: <Dashboard />,
    apps: <Apps />,
    contracts: <Contracts />,
    licenses: <Licenses />,
    sync: <SyncStatus />,
    settings: <Settings />,
  };

  return (
    <div style={{ display: "flex", height: "100vh", background: "var(--surface-0)", color: "var(--text-primary)", fontFamily: "var(--font-sans)" }}>
      <Sidebar active={page} onNav={setPage} />
      <main style={{ flex: 1, overflowY: "auto", padding: "2rem 2.5rem" }}>
        {pages[page]}
      </main>
    </div>
  );
}
