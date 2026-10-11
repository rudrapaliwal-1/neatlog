"""Document access control module with intentional BOLA vulnerability (OWASP API1:2023).

This file is the single target file that AI remediation patches are allowed to modify.
"""

from typing import Any, Dict, Optional
from .sample_data import DOCUMENTS


def get_document(requesting_user_id: Optional[str], document_id: str) -> Dict[str, Any]:
    """Retrieve document by ID for the requesting user.

    Args:
        requesting_user_id: ID of the user requesting the document (e.g. 'alice', 'bob').
        document_id: Identifier of the document to retrieve.

    Returns:
        Dictionary containing document metadata and content.

    Raises:
        PermissionError: If requesting_user_id is anonymous or unauthorized.
        LookupError: If document_id does not exist.
    """
    # Explicit anonymous check
    if not requesting_user_id or not str(requesting_user_id).strip():
        raise PermissionError("Anonymous access denied: requesting_user_id required")

    # Nonexistent document check
    if document_id not in DOCUMENTS:
        raise LookupError(f"Document '{document_id}' not found")

    doc = DOCUMENTS[document_id]

    # VULNERABLE IMPLEMENTATION (Broken Object-Level Authorization):
    # Fails to enforce that doc["owner_id"] == requesting_user_id before returning.
    return dict(doc)
