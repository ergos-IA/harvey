"""Dashboard routes for internal documents: files the operator drops in
``data/docs/`` (a one-pager on how the process works, a price sheet…) that
anyone signed in to the dashboard can download.

The files live with the data, not in the repository, so private material
never ends up in git. Only plain files directly in that folder are served,
and only by a name the listing returned; everything goes through the
dashboard guard like any other /api route.
"""

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter()

ALLOWED = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
}

_dir_factory = None


def configure(dir_factory) -> None:
    """``dir_factory()`` returns the docs folder (so tests can move it)."""
    global _dir_factory
    _dir_factory = dir_factory


def _docs_dir() -> Path:
    return Path(_dir_factory())


def _files() -> dict[str, Path]:
    folder = _docs_dir()
    if not folder.is_dir():
        return {}
    out = {}
    for p in folder.iterdir():
        if p.name.startswith(".") or p.is_symlink() or not p.is_file():
            continue
        if p.suffix.lower() in ALLOWED:
            out[p.name] = p
    return out


@router.get("/api/docs")
async def list_docs():
    items = []
    for name, p in sorted(_files().items(), key=lambda kv: kv[0].lower()):
        st = p.stat()
        items.append({
            "name": name,
            "size": st.st_size,
            "modified": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds"),
        })
    return {"items": items}


@router.get("/api/docs/{name}")
async def get_doc(name: str):
    path = _files().get(name)
    if path is None:
        return JSONResponse({"success": False, "error": "No existe ese documento."}, status_code=404)
    return FileResponse(path, media_type=ALLOWED[path.suffix.lower()], filename=name,
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})
