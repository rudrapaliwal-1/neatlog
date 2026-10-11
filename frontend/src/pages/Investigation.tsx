import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, RefreshCw, BrainCircuit, FileCode2, History, ShieldCheck } from "lucide-react";
import { useJobDetails } from "../hooks/useJobDetails";
import StatusBadge from "../components/StatusBadge";
import PatchDiffViewer from "../components/PatchDiffViewer";
import ApprovalPanel from "../components/ApprovalPanel";
import ActivityTimeline from "../components/ActivityTimeline";
import VerificationPanel from "../components/VerificationPanel";
import { api } from "../api/jobs";
export default function Investigation() {
  const { jobId } = useParams(); const { job, patch, events, loading, error, refresh } = useJobDetails(jobId);
  const [verifyBusy, setVerifyBusy] = useState(false); const [verifyError, setVerifyError] = useState("");
  const canVerify = job?.status === "VERIFYING" && !!patch?.patch_hash && !job.verification_running && (!job.verification || job.verification.patch_hash !== patch.patch_hash);
  async function verify() {
    if (!jobId || verifyBusy || !canVerify) return;
    setVerifyBusy(true); setVerifyError("");
    try { await api.verify(jobId); await refresh(); }
    catch (e) { setVerifyError(e instanceof Error ? e.message : "Verification request failed."); }
    finally { setVerifyBusy(false); }
  }
  if (!jobId) return <div className="page"><div className="error-state"><h2>Select a job to investigate</h2><p>Open a job from Findings or the dashboard.</p><Link to="/findings" className="button button-primary">Browse findings</Link></div></div>;
  if (loading) return <div className="page"><div className="loading-state"><RefreshCw size={18} className="spin"/>Loading job, patch and events from API…</div></div>;
  if (error || !job) return <div className="page"><div className="error-state"><h2>Unable to load investigation</h2><p>{error || "The backend returned no job."}</p><p>Check the job ID and API connectivity.</p><button className="button button-secondary" onClick={() => void refresh()}>Retry</button><Link to="/findings" className="text-link">Back to findings</Link></div></div>;
  const finding = job.finding;
  return <div className="page"><div className="page-heading"><div><Link to="/findings" className="back-link"><ArrowLeft size={14}/> Findings</Link><div className="eyebrow">INVESTIGATION / {job.job_id}</div><h1>{finding?.id || job.finding_id || job.job_id}</h1><p>{finding?.description || job.summary || "Investigation details provided by the backend."}</p></div><div className="heading-actions"><StatusBadge status={job.status}/><button className="button button-secondary" onClick={() => void refresh()}><RefreshCw size={14}/> Refresh</button></div></div>
    {job.status === "EXECUTION_ERROR" && <div className="error-banner" role="alert">The backend could not complete this attempt. Inspect the audit trail and confirm the Ollama model and verifier are available.</div>}<div className="investigation-summary"><div><span>Vulnerability</span><strong>{finding?.type || "Not provided"}</strong></div><div><span>Severity</span><strong className={`severity ${String(finding?.severity || "").toLowerCase()}`}>{finding?.severity || "—"}</strong></div><div><span>Affected file</span><strong><FileCode2 size={14}/>{finding?.file_path || "—"}</strong></div><div><span>Attempt</span><strong>{patch?.attempt ?? job.attempt ?? "—"}</strong></div></div>
    <div className="investigation-grid"><div className="investigation-main"><section className="panel"><div className="panel-heading"><div><div className="eyebrow">ACTIVE PATCH</div><h2><FileCode2 size={18}/> Proposed code changes</h2></div><span className="version-pill">Attempt {patch?.attempt ?? job.attempt ?? "—"}</span></div><PatchDiffViewer patch={patch}/><div className="patch-explanation"><BrainCircuit size={17}/><div><strong>Patch explanation</strong><p>{patch?.explanation || "No patch explanation was included in the backend response."}</p></div></div></section>
      <section className="panel"><div className="panel-heading"><div><div className="eyebrow">ADVERSARIAL VERIFICATION</div><h2><ShieldCheck size={18}/> Test evidence</h2></div></div><p className="fine-print">Latest completed verification run. Its exact patch hash is shown below.</p><VerificationPanel result={job.verification}/>{verifyError && <div className="error-banner">{verifyError}</div>}<div className="verify-action"><button className="button button-primary" disabled={verifyBusy || !canVerify} onClick={() => void verify()}>{verifyBusy ? <RefreshCw size={15} className="spin"/> : <ShieldCheck size={15}/>} Request verification</button><span>Backend controls execution and returns the result.</span></div></section>
      </div><div className="investigation-side"><ApprovalPanel job={job} patch={patch} onUpdated={() => void refresh()}/><section className="panel"><div className="panel-heading"><div><div className="eyebrow">ROOT CAUSE</div><h3><BrainCircuit size={16}/> Analysis</h3></div></div><p className="analysis-copy">{patch?.root_cause || "Root-cause analysis has not been supplied yet."}</p></section><section className="panel"><div className="panel-heading"><div><div className="eyebrow">AUDIT TRAIL</div><h3><History size={16}/> Revision history</h3></div></div><ActivityTimeline events={events}/></section></div></div>
  </div>;
}