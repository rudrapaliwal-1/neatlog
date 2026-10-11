"""SQLite storage with explicit write transactions."""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import os
import sqlite3
from typing import Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # The database contains password hashes, sessions, source context and
        # approval evidence. Do not inherit a permissive host umask.
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        os.close(descriptor)
        os.chmod(self.path, 0o600)
        self.initialize()
        self._secure_sidecars()

    def _secure_sidecars(self) -> None:
        for suffix in ("-wal", "-shm"):
            try:
                os.chmod(str(self.path) + suffix, 0o600)
            except FileNotFoundError:
                pass

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        self._secure_sidecars()
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def initialize(self) -> None:
        with self.connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    target_app_id TEXT NOT NULL,
                    finding_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS patch_proposals (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(id),
                    attempt INTEGER NOT NULL,
                    root_cause TEXT NOT NULL,
                    explanation TEXT NOT NULL,
                    patch_format TEXT NOT NULL,
                    patch_text TEXT NOT NULL,
                    files_changed_json TEXT NOT NULL,
                    patch_hash TEXT NOT NULL,
                    policy_status TEXT NOT NULL,
                    policy_details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(job_id, attempt)
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(id),
                    patch_id TEXT NOT NULL REFERENCES patch_proposals(id),
                    patch_hash TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    decision TEXT NOT NULL,
                    approved_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(patch_id)
                );
                CREATE TABLE IF NOT EXISTS verification_runs (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(id),
                    patch_id TEXT NOT NULL REFERENCES patch_proposals(id),
                    patch_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS workflow_events (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(id),
                    event_type TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_job ON workflow_events(job_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_runs_job ON verification_runs(job_id, created_at);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_runs_patch ON verification_runs(patch_id);
                CREATE TRIGGER IF NOT EXISTS workflow_events_no_update
                    BEFORE UPDATE ON workflow_events BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS workflow_events_no_delete
                    BEFORE DELETE ON workflow_events BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
                CREATE TABLE IF NOT EXISTS job_bindings (
                    job_id TEXT PRIMARY KEY REFERENCES jobs(id),
                    source_revision TEXT NOT NULL,
                    verification_profile TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approval_bindings (
                    approval_id TEXT PRIMARY KEY REFERENCES approvals(id),
                    target_app_id TEXT NOT NULL,
                    source_revision TEXT NOT NULL,
                    identity_kind TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS verification_leases (
                    run_id TEXT PRIMARY KEY REFERENCES verification_runs(id),
                    owner TEXT NOT NULL,
                    token TEXT NOT NULL UNIQUE,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS run_attestations (
                    run_id TEXT PRIMARY KEY REFERENCES verification_runs(id),
                    attempt INTEGER NOT NULL,
                    source_revision TEXT NOT NULL,
                    verification_profile TEXT NOT NULL,
                    test_suite_id TEXT NOT NULL,
                    evidence_digest TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    csrf_hash TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL,
                    framework TEXT,
                    archive_name TEXT,
                    archive_sha256 TEXT,
                    source_revision TEXT,
                    created_at TEXT NOT NULL,
                    uploaded_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_projects_owner ON projects(owner_id, created_at);
                CREATE TABLE IF NOT EXISTS project_jobs (
                    job_id TEXT PRIMARY KEY REFERENCES jobs(id),
                    project_id TEXT NOT NULL REFERENCES projects(id)
                );
                CREATE TABLE IF NOT EXISTS telemetry_ids (
                    resource_key TEXT PRIMARY KEY,
                    opaque_id TEXT NOT NULL UNIQUE
                );
            """)
            try:
                columns = {row["name"] for row in db.execute("PRAGMA table_info(approvals)")}
                if "attempt" not in columns:
                    db.execute("ALTER TABLE approvals ADD COLUMN attempt INTEGER")
                    db.execute("""UPDATE approvals SET attempt =
                                  (SELECT attempt FROM patch_proposals WHERE id = approvals.patch_id)""")
                job_columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)")}
                if "version" not in job_columns:
                    db.execute("ALTER TABLE jobs ADD COLUMN version INTEGER NOT NULL DEFAULT 0")
                if db.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
                    raise RuntimeError("SQLite foreign keys are disabled")
                required = {"job_bindings", "approval_bindings", "verification_leases", "run_attestations"}
                found = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not required <= found:
                    raise RuntimeError("critical database schema is incomplete")
                critical = {"idx_runs_patch", "workflow_events_no_update", "workflow_events_no_delete"}
                objects = {row[0] for row in db.execute("SELECT name FROM sqlite_master")}
                if not critical <= objects:
                    raise RuntimeError("critical database constraint is missing")
                if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise RuntimeError("database integrity check failed")
                if db.execute("PRAGMA foreign_key_check").fetchone():
                    raise RuntimeError("database foreign key integrity check failed")
                db.commit()
            except Exception:
                db.rollback()
                raise

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            self._secure_sidecars()
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        db = self.connect()
        try:
            db.execute("BEGIN")
            self._secure_sidecars()
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
