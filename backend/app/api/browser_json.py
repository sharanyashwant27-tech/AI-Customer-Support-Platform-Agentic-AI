"""Helpers for browser-friendly JSON responses."""

from __future__ import annotations

import html
import json
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, Response


def accepts_html(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    return "text/html" in accept and "application/json" not in accept


def pretty_json_response(
    request: Request,
    payload: dict[str, Any],
    *,
    title: str = "API JSON",
    force_raw: bool = False,
) -> Response:
    """Return payload as JSON, or a pretty HTML viewer when opened in a browser."""
    if force_raw or not accepts_html(request):
        return JSONResponse(payload)
    return HTMLResponse(_pretty_json_html(title, payload))


def _pretty_json_html(title: str, payload: dict[str, Any]) -> str:
    pretty = html.escape(json.dumps(payload, indent=2, ensure_ascii=False))
    safe_title = html.escape(title)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{safe_title}</title>
  <style>
    body {{ margin:0; font-family:"Segoe UI",system-ui,sans-serif; background:#0b1220; color:#e8eefc; }}
    main {{ max-width:900px; margin:0 auto; padding:2rem 1.25rem 3rem; }}
    h1 {{ margin:0 0 .5rem; font-size:1.35rem; }}
    p {{ color:#9db0d0; }}
    a {{ color:#2dd4bf; }}
    pre {{
      background:#121a2b; border:1px solid #24314d; border-radius:12px;
      padding:1rem 1.1rem; overflow:auto; line-height:1.45; font-size:.92rem;
      color:#d1fae5;
    }}
    .badge {{
      display:inline-block; background:rgba(45,212,191,.15); color:#2dd4bf;
      padding:.25rem .6rem; border-radius:999px; font-weight:700; font-size:.8rem;
      margin-bottom:.75rem;
    }}
  </style>
</head>
<body>
  <main>
    <div class="badge">application/json</div>
    <h1>{safe_title}</h1>
    <p>Pretty-printed API response for the browser.
      <a href="?format=raw">Raw JSON</a> · <a href="/">Home</a> · <a href="/docs">Docs</a>
    </p>
    <pre>{pretty}</pre>
  </main>
</body>
</html>"""
