import Dashboard from "./Dashboard";
import PortfolioInsights from "../components/PortfolioInsights";

// The Analytics page = your existing dashboard + the portfolio metrics and inventory sections.
// Set this to false to put the new sections back below the existing dashboard.
const SECTIONS_FIRST = true;

export default function Analytics() {
  return SECTIONS_FIRST ? (
    <div>
      <PortfolioInsights first />
      <Dashboard />
    </div>
  ) : (
    <div>
      <Dashboard />
      <PortfolioInsights />
    </div>
  );
}
