import { CheckCircle2, XCircle, Clock3, FlaskConical, AlertTriangle } from "lucide-react";
import type { VerificationResult } from "../api/types";
import StatusBadge from "./StatusBadge";
export default function VerificationPanel({ result }: { result?: VerificationResult | null }) {
  if (!result) return <div className="empty-state"><FlaskConical size={20} /><strong>No verification result returned</strong><span>Results will appear after the backend verification engine responds.</span></div>;
  const status = result.status;
  return <div className="verification-panel"><div className="verification-hero"><div className={`verification-symbol ${status === "VERIFIED" ? "green" : "red"}`}>{status === "VERIFIED" ? <CheckCircle2 size={24} /> : <XCircle size={24} />}</div><div><div className="eyebrow">BACKEND VERIFICATION RESULT</div><h3>{status}</h3><StatusBadge status={String(status)} /></div></div>
    <div className="test-grid"><div><span>Total tests</span><strong>{result.tests_total ?? "—"}</strong></div><div><span>Passed</span><strong className="success-text">{result.tests_passed ?? "—"}</strong></div><div><span>Failed</span><strong className="danger-text">{result.tests_failed ?? "—"}</strong></div><div><span>Duration</span><strong>{result.duration_ms != null ? `${(result.duration_ms / 1000).toFixed(2)}s` : "—"}</strong></div></div>
    {!!result.test_results?.length && <div className="failed-test-list"><h4>Protected tests executed</h4>{result.test_results.map((test, index) => <code key={`${test.name}-${index}`}>{test.outcome.toUpperCase()} · {test.name}</code>)}</div>}
    {!!result.failed_tests?.length && <div className="failed-test-list"><h4><AlertTriangle size={14} /> Failed tests</h4>{result.failed_tests.map(t => <code key={t}>{t}</code>)}</div>}
    {result.execution_error && <div className="execution-error"><AlertTriangle size={15} /><div><strong>Execution error</strong><pre>{result.execution_error}</pre></div></div>}
    <div className="hash-label">VERIFIED PATCH HASH</div><code className="hash-value">{result.patch_hash || "Not provided"}</code>
    <p className="fine-print"><Clock3 size={12} /> Passing the required tests is evidence for this test suite and patch—not proof that the entire application is secure.</p>
  </div>;
}