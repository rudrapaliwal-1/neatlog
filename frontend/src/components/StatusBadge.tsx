import { CheckCircle2, Clock3, XCircle, ShieldAlert, LoaderCircle, CircleHelp } from "lucide-react";
import type { WorkflowStatus } from "../api/types";

const config: Record<string, { label: string; className: string; icon: typeof CheckCircle2 }> = {
  VERIFIED: { label: "Verified", className: "success", icon: CheckCircle2 },
  AWAITING_APPROVAL: { label: "Awaiting approval", className: "warning", icon: Clock3 },
  PLANNING: { label: "Planning", className: "info", icon: LoaderCircle },
  VERIFYING: { label: "Verifying", className: "info", icon: LoaderCircle },
  VERIFICATION_FAILED: { label: "Verification failed", className: "danger", icon: XCircle },
  POLICY_REJECTED: { label: "Policy rejected", className: "danger", icon: ShieldAlert },
  USER_REJECTED: { label: "Rejected by user", className: "danger", icon: XCircle },
  RETRY_EXHAUSTED: { label: "Retry exhausted", className: "danger", icon: XCircle },
  EXECUTION_ERROR: { label: "Execution error", className: "danger", icon: XCircle },
  FINDING_RECEIVED: { label: "Finding received", className: "muted", icon: Clock3 },
};
export default function StatusBadge({ status }: { status?: string | WorkflowStatus }) {
  const item = config[status || ""] || { label: status || "Unknown", className: "muted", icon: CircleHelp };
  const Icon = item.icon;
  return <span className={`badge ${item.className}`}><Icon size={13} />{item.label}</span>;
}