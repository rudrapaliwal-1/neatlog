"""Privacy-preserving Neatlogs instrumentation for patch generation.

Use ``observer.workflow(job_id=..., attempt=..., model_id=...)`` around one
generation attempt, then call ``observer.event(...)`` at the documented steps.
No prompt, source, patch, verifier summary, exception text or credential is
accepted as telemetry metadata.
"""

from .neatlogs_observer import AgentEvent, NeatlogsObserver

__all__ = ["AgentEvent", "NeatlogsObserver"]
