import { useCallback, useEffect, useState } from "react";
import { api, unwrapList } from "../api/jobs";
import type { Job } from "../api/types";

export function useJobs(pollInterval = 0) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const refresh = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError("");
    try { setJobs(unwrapList(await api.jobs(), "jobs")); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to load jobs"); }
    finally { if (!silent) setLoading(false); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    const hasActive = jobs.some(j => ["FINDING_RECEIVED", "PLANNING", "VERIFYING"].includes(j.status));
    const intervalMs = pollInterval || (hasActive ? 4000 : 0);
    if (!intervalMs) return;
    const timer = setInterval(() => { void refresh(true); }, intervalMs);
    return () => clearInterval(timer);
  }, [jobs, pollInterval, refresh]);
  return { jobs, loading, error, refresh };
}