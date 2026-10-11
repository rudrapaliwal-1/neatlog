import { useState } from "react";
import { Link } from "react-router-dom";
import { RefreshCw, Search } from "lucide-react";
import { useJobs } from "../hooks/useJobs";
import FindingsTable from "../components/FindingsTable";
export default function Findings() {
  const { jobs, loading, error, refresh } = useJobs();
  const [filter, setFilter] = useState(new URLSearchParams(window.location.search).get("search") || "");
  const filtered = jobs.filter(j => `${j.finding?.id || j.finding_id || ""} ${j.finding?.type || ""} ${j.finding?.file_path || ""} ${j.job_id}`.toLowerCase().includes(filter.toLowerCase()));
  return <div className="page"><div className="page-heading"><div><div className="eyebrow">DETECTION INTAKE</div><h1>Security findings</h1><p>Findings supplied for uploaded projects and their remediation jobs.</p></div><Link className="button button-primary" to="/projects">Upload repository and select finding</Link></div>
    {error && <div className="error-banner">{error}</div>}
    <section className="panel table-panel"><div className="panel-heading"><div><div className="eyebrow">BACKEND RECORDS</div><h2>Findings & jobs <span className="subtle-count">{filtered.length}</span></h2></div><div className="table-tools"><div className="input-search"><Search size={15}/><input value={filter} onChange={e=>setFilter(e.target.value)} placeholder="Filter findings…" /></div><button className="icon-button" onClick={() => void refresh()} aria-label="Refresh" disabled={loading}><RefreshCw size={15} className={loading ? "spin" : ""}/></button></div></div>{loading ? <div className="loading-state"><RefreshCw size={17} className="spin"/>Loading findings…</div> : <FindingsTable jobs={filtered}/>}</section>
  </div>;
}
