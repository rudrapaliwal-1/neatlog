import { useState } from "react";
import { Navigate, Route, Routes, useParams } from "react-router-dom";
import { AlertCircle, X } from "lucide-react";
import Sidebar from "./components/Sidebar";
import Header from "./components/Header";
import Dashboard from "./pages/Dashboard";
import Projects from "./pages/Projects";
import Findings from "./pages/Findings";
import Investigation from "./pages/Investigation";
import Evidence from "./pages/Evidence";
import ActivityPage from "./pages/Activity";

function JobRoute() { const { jobId } = useParams(); return <Investigation key={jobId} />; }
export default function App() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  return <div className={`app-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}><div className={`sidebar-overlay ${mobileOpen ? "visible" : ""}`} onClick={() => setMobileOpen(false)} /><div className={mobileOpen ? "sidebar-mobile open" : "sidebar-mobile"}><button className="mobile-close icon-button" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X size={17}/></button><Sidebar /></div><div className="desktop-sidebar"><Sidebar /></div><main className="main-area"><Header onMenu={() => { if (window.matchMedia("(max-width: 950px)").matches) setMobileOpen(true); else setSidebarCollapsed(v => !v); }}/><Routes><Route path="/" element={<Dashboard/>}/><Route path="/projects" element={<Projects/>}/><Route path="/findings" element={<Findings/>}/><Route path="/investigation" element={<Investigation/>}/><Route path="/jobs/:jobId" element={<JobRoute/>}/><Route path="/verification" element={<Navigate to="/findings" replace/>}/><Route path="/activity" element={<ActivityPage/>}/><Route path="/evidence" element={<Evidence/>}/><Route path="*" element={<div className="page"><div className="error-state"><AlertCircle size={24}/><h2>Page not found</h2><p>This route is not part of the SENTINEL-X workspace.</p><a className="button button-primary" href="/">Return to overview</a></div></div>}/></Routes><footer className="app-footer"><span>SENTINEL-X <span className="footer-separator">/</span> Team BeyondSight</span><span>Autonomous remediation. Adversarial verification.</span></footer></main></div>;
}
