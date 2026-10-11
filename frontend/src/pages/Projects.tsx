import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiBaseUrl, getCsrfToken, request } from "../api/client";
import { api } from "../api/jobs";

type Project = { id: string; name: string; description: string; status: string; framework: string | null; source_revision: string | null; uploaded_at: string | null };
const finding = { id: "BOLA-001", type: "BROKEN_OBJECT_LEVEL_AUTHORIZATION", severity: "HIGH" as const,
  file_path: "app/access.py", description: "A user can access another user's private document through get_document." };

function upload(projectId: string, file: File, progress: (value: number) => void): Promise<Project> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${apiBaseUrl}/api/projects/${encodeURIComponent(projectId)}/upload`);
    xhr.withCredentials = true; xhr.timeout = 120000;
    xhr.setRequestHeader("Content-Type", "application/zip"); xhr.setRequestHeader("X-CSRF-Token", getCsrfToken()); xhr.setRequestHeader("X-Archive-Name", file.name);
    xhr.upload.onprogress = event => { if (event.lengthComputable) progress(Math.round(event.loaded / event.total * 100)); };
    xhr.onload = () => { try { const value = JSON.parse(xhr.responseText); if (xhr.status >= 200 && xhr.status < 300) resolve(value); else reject(new Error(value.detail || `Upload failed (${xhr.status})`)); } catch { reject(new Error("Upload returned an invalid response")); } };
    xhr.onerror = () => reject(new Error("Upload failed: API unavailable"));
    xhr.ontimeout = () => reject(new Error("Upload timed out"));
    xhr.send(file);
  });
}

export default function Projects() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState<Project | null>(null);
  const [files, setFiles] = useState<string[]>([]);
  const [source, setSource] = useState<{ path: string; content: string } | null>(null);
  const [name, setName] = useState(""); const [description, setDescription] = useState(""); const [zip, setZip] = useState<File | null>(null);
  const [progress, setProgress] = useState(0); const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [message, setMessage] = useState("");
  async function refresh() { const rows = await request<Project[]>("/api/projects"); setProjects(rows); if (selected) setSelected(rows.find(row => row.id === selected.id) || null); }
  useEffect(() => { void refresh().catch(e => setError(e instanceof Error ? e.message : "Could not load projects")); }, []);
  async function create() {
    if (!zip) { setError("Select a ZIP archive first."); return; }
    setBusy(true); setError(""); setMessage(""); setProgress(0);
    try {
      const project = await request<Project>("/api/projects", { method: "POST", body: JSON.stringify({ name, description }) });
      const imported = await upload(project.id, zip, setProgress);
      setSelected(imported); setZip(null); setName(""); setDescription(""); await refresh();
      setMessage(imported.status === "SUPPORTED_BOLA_CONTRACT" ? "Repository uploaded. The protected BOLA test contract is available." : "Repository uploaded. Framework detected; automated remediation/verification is not yet supported for this repository.");
      setFiles(await request<string[]>(`/api/projects/${project.id}/files`));
    } catch (e) { setError(e instanceof Error ? e.message : "Project upload failed"); await refresh(); }
    finally { setBusy(false); }
  }
  async function select(project: Project) {
    setSelected(project); setSource(null); setError("");
    try { setFiles(await request<string[]>(`/api/projects/${project.id}/files`)); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not load files"); }
  }
  async function startFinding() {
    if (!selected) return;
    setBusy(true); setError("");
    try { const result = await api.createFinding({ target_app_id: selected.id, finding });
      setMessage(`Finding supplied and AI remediation started. Job ${result.job_id}`); window.location.assign(`/jobs/${result.job_id}`);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not start remediation"); }
    finally { setBusy(false); }
  }
  return <div className="page"><div className="page-heading"><div><div className="eyebrow">SOURCE ONBOARDING</div><h1>Projects</h1><p>Upload a local ZIP, inspect source files, and start a supported BOLA remediation.</p></div></div>
    <section className="panel create-panel"><div className="panel-heading"><h2>New Project → Upload Repository</h2></div>
      <label>Project name<input value={name} maxLength={100} onChange={e => setName(e.target.value)} placeholder="My FastAPI project" /></label>
      <label>Description<input value={description} maxLength={1000} onChange={e => setDescription(e.target.value)} placeholder="Optional" /></label>
      <label>ZIP archive<input type="file" accept=".zip,application/zip" onChange={e => setZip(e.target.files?.[0] || null)} /></label>
      {busy && <p role="status">Upload progress: {progress}%</p>}
      <button className="button button-primary" disabled={busy || !name.trim() || !zip} onClick={() => void create()}>Upload Repository</button>
      <p className="fine-print">Automatic remediation currently supports the explicit Python document access BOLA contract in app/access.py. Uploading a repository does not constitute a vulnerability scan.</p>
    </section>
    {error && <div className="error-banner" role="alert">{error}</div>}{message && <div className="notice wide" role="status">{message}</div>}
    <section className="panel"><div className="panel-heading"><h2>Your projects</h2><button className="button button-secondary" onClick={() => void refresh()}>Refresh</button></div>
      {projects.length === 0 ? <p>No projects uploaded yet.</p> : projects.map(project => <button key={project.id} className="button button-secondary" style={{ margin: 6 }} onClick={() => void select(project)}>{project.name} · {project.status}</button>)}
    </section>
    {selected && <section className="panel"><div className="panel-heading"><h2>{selected.name}</h2><span>{selected.status}</span></div>
      <p>{selected.description}</p><p>Framework: {selected.framework || "Pending detection"}</p><p>Source revision: <code>{selected.source_revision || "Unavailable"}</code></p>
      {selected.status === "SUPPORTED_BOLA_CONTRACT" ? <><p>Supported finding: Broken Object Level Authorization in <code>app/access.py</code>. Confirm this finding applies to a repository you are authorized to test.</p>
        <button className="button button-primary" disabled={busy} onClick={() => void startFinding()}>Select BOLA finding and generate AI fix</button></> : <p>Framework detected — automated remediation/verification not yet supported.</p>}
      <h3>Source files</h3>{files.map(path => <button key={path} className="button button-secondary" style={{ margin: 4 }} onClick={() => void request<{path:string;content:string}>(`/api/projects/${selected.id}/files/${path.split("/").map(encodeURIComponent).join("/")}`).then(setSource).catch(e => setError(e.message))}>{path}</button>)}
      {source && <div><h4>{source.path}</h4><pre style={{ overflow: "auto", maxHeight: 420 }}>{source.content}</pre></div>}
      <p><Link to="/findings">View remediation jobs</Link></p>
    </section>}
  </div>;
}
