"""Owned project onboarding with strict ZIP extraction limits."""
from __future__ import annotations

import hashlib
import io
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from uuid import uuid4
import zipfile

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..auth import current_user
from ..database import utc_now
from ..manifest import TARGET_MANIFEST
from ..models import WorkflowError

router = APIRouter(prefix="/api/projects", tags=["projects"])
MAX_ARCHIVE = 10 * 1024 * 1024
MAX_EXTRACTED = 32 * 1024 * 1024
MAX_FILE = 2 * 1024 * 1024
MAX_FILES = 500
PROJECT_ID = re.compile(r"^project-[0-9a-f]{32}$")
SENSITIVE = re.compile(r"(^|/)(\.env|\.git|\.ssh|node_modules|__pycache__|secrets?|credentials?)(/|$)|\.(pem|key|p12|pfx)$", re.I)


class NewProject(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)


def _project(request: Request, project_id: str):
    if not PROJECT_ID.fullmatch(project_id):
        raise WorkflowError("project not found", 404, "PROJECT_NOT_FOUND")
    with request.app.state.workflow.db.read() as db:
        row = db.execute("SELECT * FROM projects WHERE id = ? AND owner_id = ?",
                         (project_id, current_user())).fetchone()
    if row is None:
        raise WorkflowError("project not found", 404, "PROJECT_NOT_FOUND")
    return dict(row)


def _public(row):
    return {key: value for key, value in row.items() if key not in {"owner_id"}}


def _source_dir(request: Request, project_id: str) -> Path:
    return request.app.state.workflow.settings.project_root / project_id / "source"


@router.post("", status_code=201)
def create_project(payload: NewProject, request: Request):
    if not payload.name.strip():
        raise WorkflowError("project name is required", 422, "INVALID_PROJECT_NAME")
    project_id = "project-" + uuid4().hex
    now = utc_now()
    with request.app.state.workflow.db.transaction() as db:
        db.execute("INSERT INTO projects (id, owner_id, name, description, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                   (project_id, current_user(), payload.name.strip(), payload.description.strip(), "CREATED", now))
    return {"id": project_id, "name": payload.name.strip(), "description": payload.description.strip(),
            "status": "CREATED", "created_at": now}


@router.get("")
def list_projects(request: Request):
    with request.app.state.workflow.db.read() as db:
        rows = db.execute("SELECT * FROM projects WHERE owner_id = ? ORDER BY created_at DESC",
                          (current_user(),)).fetchall()
    return [_public(dict(row)) for row in rows]


@router.get("/{project_id}")
def get_project(project_id: str, request: Request):
    return _public(_project(request, project_id))


@router.get("/{project_id}/status")
def project_status(project_id: str, request: Request):
    row = _project(request, project_id)
    return {"id": project_id, "status": row["status"], "framework": row["framework"],
            "source_revision": row["source_revision"]}


@router.get("/{project_id}/files")
def project_files(project_id: str, request: Request):
    row = _project(request, project_id)
    if row["status"] == "CREATED":
        return []
    root = _source_dir(request, project_id)
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*")
                  if path.is_file() and path.suffix == ".py" and not SENSITIVE.search(path.relative_to(root).as_posix()))


@router.get("/{project_id}/files/{file_path:path}")
def project_file(project_id: str, file_path: str, request: Request):
    _project(request, project_id)
    name = PurePosixPath(file_path)
    if (file_path.startswith("/") or "\\" in file_path or ".." in name.parts or
            name.suffix != ".py" or SENSITIVE.search(file_path)):
        raise WorkflowError("file is not available", 404, "FILE_NOT_FOUND")
    root = _source_dir(request, project_id).resolve()
    path = (root / file_path).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.is_symlink() or path.stat().st_size > 65536:
        raise WorkflowError("file is not available", 404, "FILE_NOT_FOUND")
    return {"path": file_path, "content": path.read_text(encoding="utf-8")}


def _validate_zip(data: bytes):
    if not data or len(data) > MAX_ARCHIVE:
        raise WorkflowError("archive size is invalid", 422, "INVALID_ARCHIVE")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        entries = archive.infolist()
        if not entries or len(entries) > MAX_FILES:
            raise WorkflowError("archive is empty or has too many files", 422, "INVALID_ARCHIVE")
        seen, total = set(), 0
        for info in entries:
            name = info.filename
            path = PurePosixPath(name)
            parts = path.parts
            mode = (info.external_attr >> 16) & 0o170000
            if (not name or name.startswith("/") or "\\" in name or "\x00" in name or
                    any(part in ("", ".", "..") for part in parts) or
                    any(":" in part for part in parts) or
                    mode not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise WorkflowError("archive contains unsafe paths or file types", 422, "UNSAFE_ARCHIVE")
            normalized = path.as_posix().rstrip("/").casefold()
            if normalized in seen:
                raise WorkflowError("archive contains duplicate paths", 422, "DUPLICATE_PATH")
            seen.add(normalized)
            if info.is_dir():
                continue
            total += info.file_size
            if info.file_size > MAX_FILE or total > MAX_EXTRACTED or info.compress_size == 0 or info.file_size / info.compress_size > 100:
                raise WorkflowError("archive exceeds extraction limits", 422, "ZIP_BOMB")
        return archive, entries
    except zipfile.BadZipFile:
        raise WorkflowError("invalid ZIP archive", 422, "INVALID_ARCHIVE") from None


@router.post("/{project_id}/upload")
async def upload(project_id: str, request: Request):
    row = _project(request, project_id)
    if row["status"] != "CREATED":
        raise WorkflowError("project already has an upload", 409, "UPLOAD_EXISTS")
    if request.headers.get("content-type", "").split(";")[0] != "application/zip":
        raise WorkflowError("upload must be a ZIP archive", 415, "ZIP_REQUIRED")
    data = await request.body()
    original_name = request.headers.get("x-archive-name", "upload.zip")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,127}\.zip", original_name, re.I):
        raise WorkflowError("invalid archive filename", 422, "INVALID_ARCHIVE_NAME")
    archive, entries = _validate_zip(data)
    destination = _source_dir(request, project_id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="upload-", dir=destination.parent))
    try:
        actual_total = 0
        for info in entries:
            target = temporary / PurePosixPath(info.filename)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            copied = 0
            with archive.open(info) as source, target.open("xb") as out:
                while chunk := source.read(65536):
                    copied += len(chunk)
                    actual_total += len(chunk)
                    if copied > MAX_FILE or actual_total > MAX_EXTRACTED:
                        raise WorkflowError("archive exceeds extraction limits", 422, "ZIP_BOMB")
                    out.write(chunk)
            if copied != info.file_size:
                raise WorkflowError("archive file failed integrity check", 422, "INVALID_ARCHIVE")
        children = list(temporary.iterdir())
        if len(children) == 1 and children[0].is_dir() and not (temporary / "app").exists():
            nested = children[0]
            for child in list(nested.iterdir()):
                child.rename(temporary / child.name)
            nested.rmdir()
        framework = "Python/FastAPI" if any((temporary / x).is_file() and "fastapi" in (temporary / x).read_text(errors="ignore").lower()
                                         for x in ("requirements.txt", "pyproject.toml")) else "Unknown"
        profile = "bola-required-tests-v1"
        supported = framework == "Python/FastAPI" and (temporary / "app" / "access.py").is_file() and (temporary / "app" / "sample_data.py").is_file()
        if supported:
            source = (temporary / "app" / "access.py").read_text(encoding="utf-8")
            supported = "def get_document(" in source and "    return dict(doc)\n" in source
        status = "SUPPORTED_BOLA_CONTRACT" if supported else "UNSUPPORTED"
        revision = TARGET_MANIFEST.source_revision(temporary, Path(__file__).resolve().parents[2] / "verification" / "protected_tests") if supported else None
        temporary.rename(destination)
        with request.app.state.workflow.db.transaction() as db:
            db.execute("UPDATE projects SET status = ?, framework = ?, archive_name = ?, archive_sha256 = ?, source_revision = ?, uploaded_at = ? WHERE id = ? AND owner_id = ? AND status = 'CREATED'",
                       (status, framework, original_name, "sha256:" + hashlib.sha256(data).hexdigest(), revision, utc_now(), project_id, current_user()))
        request.app.state.workflow._telemetry("project.uploaded", project_id=project_id,
                                              success=True)
        return _public(_project(request, project_id))
    except (zipfile.BadZipFile, EOFError, RuntimeError):
        shutil.rmtree(temporary, ignore_errors=True)
        raise WorkflowError("corrupted ZIP archive", 422, "INVALID_ARCHIVE") from None
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


@router.delete("/{project_id}")
def delete_project(project_id: str, request: Request):
    _project(request, project_id)
    with request.app.state.workflow.db.transaction() as db:
        if db.execute("SELECT 1 FROM project_jobs WHERE project_id = ?", (project_id,)).fetchone():
            raise WorkflowError("project with remediation history cannot be deleted", 409, "PROJECT_HAS_JOBS")
        db.execute("DELETE FROM projects WHERE id = ? AND owner_id = ?", (project_id, current_user()))
    shutil.rmtree(_source_dir(request, project_id).parent, ignore_errors=True)
    return {"status": "deleted"}
