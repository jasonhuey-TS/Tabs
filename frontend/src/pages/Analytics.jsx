import Dashboard from "./Dashboard";
import PortfolioInsights from "../components/PortfolioInsights";

// The Analytics page: your existing dashboard, unchanged, followed by the portfolio metrics and inventory sections.
// To show the new sections first, swap the two lines below.
export default function Analytics() {
  return (
    <div>
      <Dashboard />
      <PortfolioInsights />
    </div>
  );
}
