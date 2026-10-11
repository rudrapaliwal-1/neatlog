import { useMemo } from "react";
import { FileCode2, Plus, Minus } from "lucide-react";
import type { Patch, PatchFile } from "../api/types";

function parseDiff(diff: string) {
  return diff.split("\n").map((line, i) => ({ line, n: i + 1, kind: line.startsWith("+") && !line.startsWith("+++") ? "add" : line.startsWith("-") && !line.startsWith("---") ? "remove" : line.startsWith("@@") ? "hunk" : "context" }));
}
export default function PatchDiffViewer({ patch }: { patch: Patch | null }) {
  const files: PatchFile[] = patch?.files?.length ? patch.files : patch?.diff ? [{ file_path: "Patch diff", diff: patch.diff }] : [];
  const lines = useMemo(() => files.flatMap(f => parseDiff(f.diff || "")), [files]);
  if (!patch) return <div className="empty-state">No patch payload is available from the API.</div>;
  return <div className="diff-viewer">
    <div className="diff-filebar"><div><FileCode2 size={15} /><strong>{files.length ? files.map(f => f.file_path).join(", ") : "No changed files reported"}</strong></div><div className="diff-counts"><span className="add-text"><Plus size={13} />{files.reduce((n,f)=>n+(f.additions||0),0)} additions</span><span className="remove-text"><Minus size={13} />{files.reduce((n,f)=>n+(f.deletions||0),0)} deletions</span></div></div>
    {files.some(f => f.diff) ? <pre className="diff-code">{lines.map((line, i) => <div key={i} className={`diff-line ${line.kind}`}><span className="line-number">{line.n}</span><span className="line-content">{line.line || " "}</span></div>)}</pre> : <div className="empty-state">Backend returned a patch object without unified diff text. The diff contract needs confirmation.</div>}
  </div>;
}