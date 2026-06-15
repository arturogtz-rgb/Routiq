"""MongoDB backup access for the Super Admin (download latest dump, no SSH).

The daily cron (deploy/scripts/06-backup-mongo.sh) writes gzip archives into the
shared `mongo_backups` volume, mounted read-only into the backend at BACKUP_DIR.
These endpoints let the Master list and download them from the panel.
"""
import os
import glob
import asyncio
import logging
import subprocess
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


def freshness() -> dict:
    """Backup freshness status (used by the status endpoint and the alert loop)."""
    files = _list_files()
    if not files:
        return {"ok": False, "available": 0, "stale": True, "last_at": None,
                "hours_since": None, "message": "No hay respaldos. Activa el cron diario (06-backup-mongo.sh) en el VPS."}
    st = os.stat(files[0])
    last = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
    hours = (datetime.now(timezone.utc) - last).total_seconds() / 3600
    stale = hours > 24
    return {
        "ok": not stale, "available": len(files), "stale": stale,
        "last_at": last.isoformat(), "hours_since": round(hours, 1),
        "message": ("El último respaldo tiene más de 24 horas. Revisa el cron diario en el VPS."
                    if stale else "Respaldos al día."),
    }


@router.get("/backups/status")
async def backup_status(user: dict = Depends(require_roles("super_admin"))):
    return freshness()


def _run_mongodump(path: str) -> tuple[int, str]:
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    cmd = ["mongodump", f"--uri={mongo_url}", f"--db={db_name}", f"--archive={path}", "--gzip"]
    proc = subprocess.run(cmd, capture_output=True, timeout=110)
    return proc.returncode, (proc.stderr.decode("utf-8", "ignore")[:500])


@router.post("/backups/run")
async def run_backup(user: dict = Depends(require_roles("super_admin"))):
    """Genera un respaldo de MongoDB al instante (sin SSH) en BACKUP_DIR."""
    import shutil
    if not shutil.which("mongodump"):
        raise HTTPException(status_code=503, detail="mongodump no está disponible en el servidor.")
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
    except Exception:
        raise HTTPException(status_code=500, detail="El volumen de respaldos es de solo lectura. Habilita escritura en el backend para generar respaldos desde el panel.")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = os.path.join(BACKUP_DIR, f"routiq-{ts}.gz")
    try:
        rc, err = await asyncio.to_thread(_run_mongodump, path)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="El respaldo tardó demasiado. Intenta de nuevo o genera desde el VPS.")
    except Exception as e:  # noqa: BLE001
        log.exception("backup run failed")
        raise HTTPException(status_code=500, detail=f"No se pudo generar el respaldo: {str(e)[:200]}")
    if rc != 0 or not os.path.isfile(path):
        log.error("mongodump rc=%s err=%s", rc, err)
        raise HTTPException(status_code=500, detail="No se pudo generar el respaldo. Revisa permisos del volumen de backups.")
    return {"ok": True, **_meta(path)}


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
