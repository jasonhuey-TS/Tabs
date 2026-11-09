import { useState, useEffect } from "react";
import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import Apps from "./pages/Apps";
import Contracts from "./pages/Contracts";
import Licenses from "./pages/Licenses";
import SyncStatus from "./pages/SyncStatus";
import Settings from "./pages/Settings";
import IntegrationLibrary from "./pages/IntegrationLibrary";
import Reclamation from "./pages/Reclamation";

export default function App() {
  const [page, setPage] = useState("dashboard");
  const [workflowPrefill, setWorkflowPrefill] = useState(null);   // "Start Workflow" on an app opens the Reclamation form

  useEffect(() => {
    const onStart = e => { setWorkflowPrefill(e.detail); setPage("reclamation"); };
    window.addEventListener("tab:start-workflow", onStart);
    return () => window.removeEventListener("tab:start-workflow", onStart);
  }, []);

  const pages = {
    dashboard: <Dashboard />,
    reclamation: <Reclamation initialPrefill={workflowPrefill} onPrefillConsumed={() => setWorkflowPrefill(null)} />,
    apps: <Apps />,
    contracts: <Contracts />,
    licenses: <Licenses />,
    sync: <SyncStatus />,
    settings: <Settings />,
    "integration-library": <IntegrationLibrary />,
  };

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden", fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif" }}>
      <Sidebar active={page} onNav={setPage} />
      <main style={{ flex: 1, overflowY: "auto", background: "#F4F6FA", padding: "2rem 2.5rem" }}>
        {pages[page] || <Dashboard />}
      </main>
    </div>
  );
}
