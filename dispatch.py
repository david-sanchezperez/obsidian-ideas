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


def retry_one(note: Path, repos: dict) -> bool:
    """Reintenta el encolado de una única nota 'pending'. True si quedó encolada."""
    fit = read_dispatch(note)
    if not fit or fit.get("status") != "pending":
        return False
    repo_info = repos.get(fit.get("project_slug"))
    if not repo_info:
        return False
    try:
        task = dispatch_task(fit, repo_info)
        write_dispatch(note, "dispatched", fit, task)
        return True
    except Exception:
        log.exception("reintento fallido para %s", note.name)
        return False


def retry_pending(vault_dir: Path, repos: dict) -> tuple[int, int]:
    """Reintenta el encolado de todas las notas marcadas 'pending' (fallaron por
    PC apagado, etc.). Devuelve (intentadas, encoladas_con_éxito)."""
    pending = [n for n in vault_dir.glob("*.md") if (read_dispatch(n) or {}).get("status") == "pending"]
    ok = sum(retry_one(n, repos) for n in pending)
    return len(pending), ok


# Estados de agent-loops que ya no van a cambiar solos — dejar de hacer polling
# sobre ellos y avisar una vez.
TERMINAL_STATUSES = {"done", "archived", "gave_up", "blocked"}


def sync_dispatch_statuses(vault_dir: Path) -> list[dict]:
    """Consulta agent-loops por cada nota 'dispatched' con task_id conocido y
    actualiza la nota si el estado cambió. Devuelve las notas cuyo estado
    acaba de pasar a uno terminal (done/archived/gave_up/blocked) en esta
    pasada, para poder avisar por Telegram solo de las novedades."""
    if not AGENT_LOOPS_URL:
        return []
    changed: list[dict] = []
    with httpx.Client(base_url=AGENT_LOOPS_URL, timeout=15) as client:
        for note in vault_dir.glob("*.md"):
            fit = read_dispatch(note)
            if not fit or fit.get("status") != "dispatched" or not fit.get("task_id"):
                continue
            prev_status = fit.get("agent_loops_status")
            # Una vez en estado terminal ya no cambia de estado, pero el PR puede
            # abrirse unos instantes después (webhook de idea-pr-opener) — seguimos
            # consultando hasta que aparezca pr_url, luego sí paramos.
            if prev_status in TERMINAL_STATUSES and fit.get("pr_url"):
                continue
            try:
                resp = client.get(f"/api/tasks/{fit['task_id']}")
                resp.raise_for_status()
                task = resp.json()
            except Exception:
                log.exception("no se pudo consultar el estado de la tarea %s", fit["task_id"])
                continue
            new_status = task.get("status")
            new_pr_url = task.get("pr_url") and not fit.get("pr_url")
            if new_status == prev_status and not new_pr_url:
                continue
            write_dispatch(note, "dispatched", fit, task)
            if new_status in TERMINAL_STATUSES and new_status != prev_status:
                changed.append({
                    "note_name": note.name,
                    "task_title": fit["task_title"],
                    "project_slug": fit["project_slug"],
                    "status": new_status,
                })
            if new_pr_url:
                changed.append({
                    "note_name": note.name,
                    "task_title": fit["task_title"],
                    "project_slug": fit["project_slug"],
                    "status": "pr_opened",
                    "pr_url": task["pr_url"],
                })
    return changed
