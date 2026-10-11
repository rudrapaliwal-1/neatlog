"""Deterministic in-memory document data for BOLA authorization lab."""

from typing import Any, Dict

DOCUMENTS: Dict[str, Dict[str, Any]] = {
    "doc_alice_1": {
        "id": "doc_alice_1",
        "owner_id": "alice",
        "title": "Alice Strategy Plan",
        "content": "Confidential corporate strategy notes for Alice.",
        "is_private": True,
    },
    "doc_alice_2": {
        "id": "doc_alice_2",
        "owner_id": "alice",
        "title": "Alice Financial Audit",
        "content": "Personal financial audit report for Alice.",
        "is_private": True,
    },
    "doc_bob_1": {
        "id": "doc_bob_1",
        "owner_id": "bob",
        "title": "Bob Cryptographic Keys",
        "content": "Private signing keys and security tokens for Bob.",
        "is_private": True,
    },
    "doc_bob_2": {
        "id": "doc_bob_2",
        "owner_id": "bob",
        "title": "Bob Performance Review",
        "content": "Managerial feedback and review for Bob.",
        "is_private": True,
    },
    "doc_charlie_1": {
        "id": "doc_charlie_1",
        "owner_id": "charlie",
        "title": "Charlie Payroll Record",
        "content": "Charlie salary and executive compensation.",
        "is_private": True,
    },
}
