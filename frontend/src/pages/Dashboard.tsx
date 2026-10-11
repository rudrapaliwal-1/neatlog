import { useEffect, useState } from "react";
import { Activity, CheckCircle2, Clock3, ShieldAlert, ArrowUpRight, RefreshCw, Zap, CircleCheck, FileSearch } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api/jobs";
import { useJobs } from "../hooks/useJobs";
import StatCard from "../components/StatCard";
import FindingsTable from "../components/FindingsTable";
import StatusBadge from "../components/StatusBadge";
export default function Dashboard() {
  const { jobs, loading, error, refresh } = useJobs();
  const [health, setHealth] = useState<"checking" | "online" | "offline">("checking");
  useEffect(() => { api.health().then(() => setHealth("online")).catch(() => setHealth("offline")); }, []);
  const awaiting = jobs.filter(j => j.status === "AWAITING_APPROVAL").length;
  const verified = jobs.filter(j => j.status === "VERIFIED").length;
  const failed = jobs.filter(j => ["VERIFICATION_FAILED","POLICY_REJECTED","EXECUTION_ERROR","RETRY_EXHAUSTED"].includes(String(j.status))).length;
  const total = jobs.length;
  const distribution = ["AWAITING_APPROVAL","VERIFYING","VERIFIED","VERIFICATION_FAILED","POLICY_REJECTED","EXECUTION_ERROR"].map(status => ({ status, count: jobs.filter(j => j.status === status).length }));
  return <div className="page">
    <div className="page-heading"><div><div className="eyebrow">SECURITY OPERATIONS CENTER</div><h1>Overview</h1><p>Track remediation from finding to independently verified evidence.</p></div><button className="button button-secondary" onClick={() => void refresh()} disabled={loading}><RefreshCw size={15} className={loading ? "spin" : ""} /> Refresh data</button><Link className="button button-primary" to="/projects">New Project → Upload Repository</Link></div>
    <div className="connection-strip"><span className={`pulse-dot ${health === "offline" ? "offline" : ""}`} /><span>API server: <strong>{health === "checking" ? "Checking…" : health === "online" ? "Online" : "Unavailable"}</strong></span><span className="connection-divider" /> <span>Data source: <strong>Backend API</strong></span>{error && <span className="connection-error">{error}</span>}</div>
    <div className="stats-grid"><StatCard label="Security findings / jobs" value={loading ? "—" : total} detail="Returned by GET /api/jobs" icon={FileSearch} /><StatCard label="Awaiting approval" value={loading ? "—" : awaiting} detail="Requires your decision" icon={Clock3} tone="amber" /><StatCard label="Verified fixes" value={loading ? "—" : verified} detail="Backend status = VERIFIED" icon={CheckCircle2} tone="green" /><StatCard label="Failed / blocked" value={loading ? "—" : failed} detail="Failed, rejected or errored" icon={ShieldAlert} tone="red" /></div>
    <div className="dashboard-grid"><section className="panel recent-panel"><div className="panel-heading"><div><div className="eyebrow">REMEDIATION QUEUE</div><h2>Recent jobs</h2></div><Link to="/findings" className="text-link">All findings <ArrowUpRight size={14} /></Link></div>{loading ? <div className="loading-state"><RefreshCw size={17} className="spin" /> Loading jobs from backend…</div> : <FindingsTable jobs={jobs.slice(0, 6)} />}</section>
    <section className="panel distribution-panel"><div className="panel-heading"><div><div className="eyebrow">LIVE WORKFLOW</div><h2>Status distribution</h2></div><Activity size={18} className="text-cyan" /></div>{!loading && !jobs.length ? <div className="empty-state">Workflow metrics appear when jobs are available from the API.</div> : <div className="distribution-list">{distribution.map(d => <div className="distribution-item" key={d.status}><div className="distribution-label"><StatusBadge status={d.status} /><strong>{d.count}</strong></div><div className="meter"><span style={{ width: `${total ? d.count / total * 100 : 0}%` }} /></div></div>)}</div>}<div className="scope-note"><Zap size={15} /><span>Verification is scoped to the reported test suite. A green result is not a blanket security guarantee.</span></div></section></div>
    <section className="workflow-strip"><div><span className="workflow-step">01</span><div><strong>Analyze</strong><small>Finding & root cause</small></div></div><span className="workflow-arrow">→</span><div><span className="workflow-step">02</span><div><strong>Review</strong><small>Policy + human approval</small></div></div><span className="workflow-arrow">→</span><div><span className="workflow-step">03</span><div><strong>Verify</strong><small>Isolated test execution</small></div></div><span className="workflow-arrow">→</span><div><span className="workflow-step verified"><CircleCheck size={16}/></span><div><strong>Prove</strong><small>Evidence & audit trail</small></div></div></section>
  </div>;
}