"""IMMUTABLE SECURITY TEST SUITE (Broken Object-Level Authorization).

Protected from AI edits.
Verifies that unauthorized users cannot access other users' private documents.
"""

import pytest
from verification.lab.app.access import get_document


def test_user_a_cannot_access_user_b_document():
    """Requirement 2: User A (alice) cannot access User B's document (doc_bob_1)."""
    with pytest.raises(PermissionError, match="(?i)unauthorized|forbidden|owner|denied"):
        get_document("alice", "doc_bob_1")


def test_user_b_cannot_access_user_a_document():
    """Requirement 3: User B (bob) cannot access User A's document (doc_alice_1)."""
    with pytest.raises(PermissionError, match="(?i)unauthorized|forbidden|owner|denied"):
        get_document("bob", "doc_alice_1")


def test_multiple_unauthorized_document_ids_rejected():
    """Requirement 6: Multiple unauthorized document IDs are rejected."""
    # Alice trying to access Bob's second document and Charlie's document
    for forbidden_doc in ["doc_bob_2", "doc_charlie_1"]:
        with pytest.raises(PermissionError, match="(?i)unauthorized|forbidden|owner|denied"):
            get_document("alice", forbidden_doc)

    # Bob trying to access Charlie's document
    with pytest.raises(PermissionError, match="(?i)unauthorized|forbidden|owner|denied"):
        get_document("bob", "doc_charlie_1")


def test_superficial_fix_blocking_only_single_id_rejected():
    """Requirement 8: Rejects superficial fixes that only block a single hardcoded ID."""
    # Tests a variety of cross-tenant combinations
    with pytest.raises(PermissionError, match="(?i)unauthorized|forbidden|owner|denied"):
        get_document("charlie", "doc_alice_2")

    with pytest.raises(PermissionError, match="(?i)unauthorized|forbidden|owner|denied"):
        get_document("charlie", "doc_bob_2")
