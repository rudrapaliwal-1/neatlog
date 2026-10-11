import type { LucideIcon } from "lucide-react";
export default function StatCard({ label, value, detail, icon: Icon, tone = "cyan" }: {
  label: string; value: number | string; detail: string; icon: LucideIcon; tone?: "cyan" | "green" | "amber" | "red";
}) {
  return <article className="stat-card"><div className={`stat-icon ${tone}`}><Icon size={18} /></div><div className="stat-label">{label}</div><div className="stat-value">{value}</div><div className="stat-detail">{detail}</div></article>;
}