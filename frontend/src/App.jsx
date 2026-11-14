import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth.jsx";
import { HowItWorks, Home, NotFound, Pilot, Privacy, Results, SiteLayout } from "./site.jsx";
import { Login, RequireAuth, Shell } from "./app/Shell.jsx";
import { Dashboard, Investigate, Scan } from "./app/Work.jsx";
import { AlertDetail, AlertsList, CampaignDetail, Campaigns, ReportPrint, Reports } from "./app/Alerts.jsx";
import { Account, Consultant, Integrations, ModelCard, Settings } from "./app/Admin.jsx";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<SiteLayout />}>
            <Route index element={<Home />} />
            <Route path="how-it-works" element={<HowItWorks />} />
            <Route path="results" element={<Results />} />
            <Route path="privacy" element={<Privacy />} />
            <Route path="pilot" element={<Pilot />} />
          </Route>
          <Route path="app/login" element={<Login />} />
          <Route path="app" element={<RequireAuth />}>
            <Route element={<Shell />}>
              <Route index element={<Dashboard />} />
              <Route path="scan" element={<Scan />} />
              <Route path="investigate" element={<Investigate />} />
              <Route path="alerts" element={<AlertsList />} />
              <Route path="alerts/:id" element={<AlertDetail />} />
              <Route path="campaigns" element={<Campaigns />} />
              <Route path="campaigns/:id" element={<CampaignDetail />} />
              <Route path="reports" element={<Reports />} />
              <Route path="reports/print" element={<ReportPrint />} />
              <Route path="integrations" element={<Integrations />} />
              <Route path="settings" element={<Settings />} />
              <Route path="consultant" element={<Consultant />} />
              <Route path="model" element={<ModelCard />} />
              <Route path="account" element={<Account />} />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Route>
          <Route element={<SiteLayout />}><Route path="*" element={<NotFound />} /></Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
