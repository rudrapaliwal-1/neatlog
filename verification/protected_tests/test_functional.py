"""IMMUTABLE FUNCTIONAL AND REGRESSION TEST SUITE.

Protected from AI edits.
Ensures that legitimate document access, anonymous rejection, and 404s work as specified.
"""

import pytest
from verification.lab.app.access import get_document


def test_owner_accesses_own_document_successfully():
    """Requirement 1: Owner accesses their own document successfully."""
    doc_alice = get_document("alice", "doc_alice_1")
    assert doc_alice is not None
    assert doc_alice["id"] == "doc_alice_1"
    assert doc_alice["owner_id"] == "alice"

    doc_bob = get_document("bob", "doc_bob_1")
    assert doc_bob is not None
    assert doc_bob["id"] == "doc_bob_1"
    assert doc_bob["owner_id"] == "bob"


def test_anonymous_user_cannot_access_private_documents():
    """Requirement 4: Anonymous user cannot access private documents."""
    # None user
    with pytest.raises(PermissionError, match="(?i)anonymous|denied|required"):
        get_document(None, "doc_alice_1")

    # Empty string user
    with pytest.raises(PermissionError, match="(?i)anonymous|denied|required"):
        get_document("", "doc_alice_1")

    # Whitespace only user
    with pytest.raises(PermissionError, match="(?i)anonymous|denied|required"):
        get_document("   ", "doc_alice_1")


def test_nonexistent_document_handled_correctly():
    """Requirement 5: Nonexistent document is handled correctly (raises LookupError)."""
    with pytest.raises(LookupError, match="(?i)not found"):
        get_document("alice", "doc_nonexistent_999")


def test_legitimate_functionality_remains_intact():
    """Requirement 7: Legitimate functionality and fields remain intact."""
    doc = get_document("alice", "doc_alice_2")
    assert doc["title"] == "Alice Financial Audit"
    assert doc["is_private"] is True
    assert "content" in doc
