import { NavLink } from "react-router-dom";
import { Activity, FileSearch, LayoutDashboard, ShieldCheck, ScrollText, Crosshair, FolderOpen } from "lucide-react";
const links = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/projects", label: "Projects", icon: FolderOpen },
  { to: "/findings", label: "Findings", icon: FileSearch },
  { to: "/investigation", label: "Investigation", icon: Crosshair },
  { to: "/verification", label: "Verification", icon: ShieldCheck },
  { to: "/activity", label: "Agent activity", icon: Activity },
  { to: "/evidence", label: "Evidence reports", icon: ScrollText },
];
export default function Sidebar() {
  return <aside className="sidebar">
    <div className="brand"><div className="brand-mark"><ShieldCheck size={22} /></div><div><div className="brand-name">SENTINEL<span>-X</span></div><div className="brand-sub">SECURITY ENGINEERING</div></div></div>
    <div className="workspace-label">WORKSPACE</div>
    <nav>{links.map(({ to, label, icon: Icon, end }) => <NavLink key={to} to={to} end={end} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}><Icon size={17} /><span>{label}</span>{label === "Findings" && <span className="nav-count">Live</span>}</NavLink>)}</nav>
    <div className="sidebar-bottom"><div className="environment"><span className="pulse-dot" /><div><strong>API connection</strong><small>Configured by environment</small></div></div><div className="sidebar-foot">BEYONDSIGHT · NEATHACK 2026</div></div>
  </aside>;
}