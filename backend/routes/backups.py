"""MongoDB backup access for the Super Admin (download latest dump, no SSH).

The daily cron (deploy/scripts/06-backup-mongo.sh) writes gzip archives into the
shared `mongo_backups` volume, mounted read-only into the backend at BACKUP_DIR.
These endpoints let the Master list and download them from the panel.
"""
import os
import glob
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from auth import require_roles

log = logging.getLogger("routiq.backups")
router = APIRouter()

BACKUP_DIR = os.environ.get("BACKUP_DIR", "/backups")
PATTERN = "routiq-*.gz"


def _list_files() -> list[str]:
    try:
        files = glob.glob(os.path.join(BACKUP_DIR, PATTERN))
    except Exception:
        return []
    # newest first by mtime
    return sorted(files, key=lambda p: os.path.getmtime(p), reverse=True)


def _meta(path: str) -> dict:
    st = os.stat(path)
    return {
        "filename": os.path.basename(path),
        "size_bytes": st.st_size,
        "size_mb": round(st.st_size / (1024 * 1024), 2),
        "modified_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
    }


@router.get("/backups")
async def list_backups(user: dict = Depends(require_roles("super_admin"))):
    files = _list_files()
    return {
        "backup_dir": BACKUP_DIR,
        "available": len(files),
        "backups": [_meta(f) for f in files[:30]],
    }


@router.get("/backups/latest/download")
async def download_latest(user: dict = Depends(require_roles("super_admin"))):
    files = _list_files()
    if not files:
        raise HTTPException(status_code=404, detail="No hay backups disponibles todavía. Verifica que el cron diario esté activo en el VPS.")
    path = files[0]
    return FileResponse(path, media_type="application/gzip", filename=os.path.basename(path))


@router.get("/backups/{filename}/download")
async def download_named(filename: str, user: dict = Depends(require_roles("super_admin"))):
    # path-traversal guard: only a bare filename matching our pattern
    if "/" in filename or "\\" in filename or not filename.startswith("routiq-") or not filename.endswith(".gz"):
        raise HTTPException(status_code=400, detail="Nombre de archivo inválido")
    path = os.path.join(BACKUP_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Backup no encontrado")
    return FileResponse(path, media_type="application/gzip", filename=filename)
