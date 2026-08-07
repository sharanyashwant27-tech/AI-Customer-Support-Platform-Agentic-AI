"""Resolve and serve the React customer UI (SPA)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


def resolve_frontend_dist() -> Path | None:
    """Locate built Vite `dist` (local repo or Docker image)."""
    here = Path(__file__).resolve()
    candidates: list[Path] = []
    # Walk parents: .../app/web → .../app → .../backend → repo root (local)
    # In Docker: /app/app/web → /app/app → /app
    for depth in range(1, 6):
        if depth >= len(here.parents):
            break
        parent = here.parents[depth]
        candidates.append(parent / "frontend" / "dist")
        candidates.append(parent / "frontend_dist")
    candidates.extend(
        [
            Path("/app/frontend_dist"),
            Path("/frontend_dist"),
        ]
    )
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve() if path.exists() else path
        if resolved in seen:
            continue
        seen.add(resolved)
        if (path / "index.html").is_file():
            return path
    return None


def mount_frontend_assets(app: FastAPI, dist: Path) -> None:
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="ui-assets")
