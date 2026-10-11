"""Thin Phase 4 planner adapter: authorized context in, unapproved proposal out."""
from __future__ import annotations

import os
from functools import lru_cache

from backend.schemas import AgentProposal
from .context import build_context
from .generator import GenerationError, generate_patch
from .observability import AgentEvent, NeatlogsObserver
from .reflection import build_revision_guidance


class PlannerError(ValueError):
    """Planner input or proposal is outside the backend contract."""


@lru_cache(maxsize=1)
def _observer() -> NeatlogsObserver:
    return NeatlogsObserver(api_key="")  # Legacy names are outside the approved nine-event scope.


def propose_patch(
    finding: dict,
    source_context: dict[str, str],
    attempt: int,
    feedback: dict | None = None,
) -> dict:
    """Implement ``SENTINEL_AGENT_CALLABLE=agent.planner:propose_patch``.

    The backend owns target authorization, attempt state, policy validation,
    approval and verification. This function reads only caller-supplied source.
    """
    if type(attempt) is not int or attempt not in (0, 1, 2):
        raise PlannerError("invalid backend attempt")
    if attempt == 0:
        if feedback is not None:
            raise PlannerError("initial proposal cannot have feedback")
        guidance = None
    else:
        guidance = build_revision_guidance(feedback, attempt)
    if not isinstance(finding, dict) or not isinstance(source_context, dict):
        raise PlannerError("finding and source context must be objects")

    observer = _observer()
    model_id = os.getenv("SENTINEL_MODEL", "qwen2.5-coder:7b")
    metadata = {"attempt": attempt, "model_id": model_id}
    with observer.workflow(**metadata):
        context = build_context(finding, source_context, allowed_paths={"app/access.py"})
        if set(context["source_context"]) != {"app/access.py"}:
            raise PlannerError("authorized source context is incomplete")
        observer.event(AgentEvent.CONTEXT_PREPARATION, **metadata)
        if attempt:
            observer.event(AgentEvent.REVISION_REQUESTED, **metadata)
        observer.event(AgentEvent.PROVIDER_SELECTION, **metadata)
        observer.event(AgentEvent.INFERENCE_STARTED, **metadata)
        try:
            generated = generate_patch(finding, context["source_context"], attempt, guidance)
            observer.event(AgentEvent.INFERENCE_COMPLETED, **metadata)
            # Agent A may include local metadata; only these exact fields cross
            # into the backend's strict AgentProposal validator.
            fields = {key: generated[key] for key in AgentProposal.model_fields}
            proposal = AgentProposal.model_validate(fields)
        except TimeoutError:
            observer.event(AgentEvent.TIMEOUT, **metadata)
            raise
        except GenerationError as exc:
            if exc.failure_type == "ProviderTimeoutError":
                observer.event(AgentEvent.TIMEOUT, **metadata)
            elif exc.failure_type == "ProviderError":
                observer.event(AgentEvent.PROVIDER_ERROR, **metadata)
            observer.event(AgentEvent.PATCH_REJECTED, **metadata)
            raise
        except Exception:
            observer.event(AgentEvent.PROVIDER_ERROR, **metadata)
            observer.event(AgentEvent.PATCH_REJECTED, **metadata)
            raise
        observer.event(AgentEvent.PATCH_GENERATED, **metadata)
        if attempt:
            observer.event(AgentEvent.REVISED_PATCH_GENERATED, **metadata)
        return proposal.model_dump()
