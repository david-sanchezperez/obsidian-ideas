"""Encola una tarea en agent-loops a partir de un encaje detectado por review.evaluate_fit."""
import logging
import os
from pathlib import Path

import httpx

from notes import read_dispatch, write_dispatch

log = logging.getLogger(__name__)

AGENT_LOOPS_URL = os.environ.get("AGENT_LOOPS_URL", "")
PR_CALLBACK_URL = os.environ.get("PR_CALLBACK_URL", "")


def _ensure_board(client: httpx.Client, slug: str, name: str) -> None:
    resp = client.get("/api/boards")
    resp.raise_for_status()
    if any(b["slug"] == slug for b in resp.json()):
        return
    client.post("/api/boards", json={"slug": slug, "name": name}).raise_for_status()


def dispatch_task(fit: dict, repo_info: dict) -> dict:
    """fit: salida de review.evaluate_fit(). repo_info: repos.json[fit['project_slug']]."""
    if not AGENT_LOOPS_URL:
        raise RuntimeError("AGENT_LOOPS_URL no configurada")
    slug = fit["project_slug"]
    with httpx.Client(base_url=AGENT_LOOPS_URL, timeout=15) as client:
        _ensure_board(client, slug, repo_info["name"])
        payload = {
            "title": fit["task_title"],
            "body": fit["task_body"],
            "repo_url": repo_info["repo_url"],
            "repo_branch": repo_info.get("repo_branch", "main"),
            "board": slug,
            # tenant=host_gpu (ver AGENTS.md/capabilities) evita el auto_decompose normal:
            # esta tarea la recoge el poller del host, no el dispatcher de contenedores.
            "auto_decompose": fit.get("tenant") != "host_gpu",
        }
        if fit.get("tenant"):
            payload["tenant"] = fit["tenant"]
        if PR_CALLBACK_URL:
            payload["callback_url"] = PR_CALLBACK_URL
        resp = client.post("/api/tasks", json=payload)
        resp.raise_for_status()
        return resp.json()


def retry_pending(vault_dir: Path, repos: dict) -> tuple[int, int]:
    """Reintenta el encolado de notas marcadas 'pending' (fallaron por PC apagado, etc.).
    Devuelve (intentadas, encoladas_con_éxito)."""
    attempted = ok = 0
    for note in vault_dir.glob("*.md"):
        fit = read_dispatch(note)
        if not fit or fit.get("status") != "pending":
            continue
        repo_info = repos.get(fit.get("project_slug"))
        if not repo_info:
            continue
        attempted += 1
        try:
            dispatch_task(fit, repo_info)
            write_dispatch(note, "dispatched", fit)
            ok += 1
        except Exception:
            log.exception("reintento fallido para %s", note.name)
    return attempted, ok
