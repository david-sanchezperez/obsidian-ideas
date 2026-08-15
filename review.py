"""Revisa las notas guardadas y sugiere iniciativas aplicables."""
import json
import os
from pathlib import Path

import httpx

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

PROMPT = """Eres un asistente que ayuda a decidir qué hacer con ideas guardadas en un \
vault personal de Obsidian. Te doy los proyectos activos del usuario y una lista de notas \
(título, tags y resumen). Para cada nota o grupo de notas relacionadas, evalúa si es \
aplicable a alguno de los proyectos activos y, si lo es, propón una iniciativa concreta y \
accionable indicando a qué proyecto aplica. Sé breve y directo, en castellano. Ignora las \
notas sin aplicación clara — no hace falta comentar todas.

Proyectos activos:
{projects}

Notas:
{notes}
"""

PROJECTS_FILE = Path(__file__).parent / "projects.md"
REPOS_FILE = Path(__file__).parent / "repos.json"
INFRA_FILE = Path(__file__).parent / "infra.md"

FIT_PROMPT = """Eres un asistente que decide si una idea guardada en un vault personal de \
Obsidian tiene aplicación concreta en alguno de los proyectos activos del usuario. Te doy la \
lista de proyectos (slug, nombre, descripción y, si las tiene, sus capacidades declaradas para \
dispatch automático — ver AGENTS.md de cada repo), infraestructura desplegada que da contexto \
adicional (pero NO es un destino válido de tarea — no tiene repo propio), y la nota. Responde \
SOLO un JSON con esta forma exacta, sin markdown ni explicación:

Si NO hay encaje claro y accionable:
{{"matches": false}}

Si SÍ hay encaje CON una capacidad declarada de un proyecto (coincide con un "when" de sus \
capabilities):
{{"matches": true, "project_slug": "<slug exacto de la lista de proyectos>", \
"capability_id": "<id de la capacidad declarada que aplica>", \
"tenant": "<tenant de esa capacidad si la tiene, o null>", \
"telegram_note": "<1-2 frases en castellano explicando el encaje, para mostrar al usuario>", \
"task_title": "<título corto y accionable de la tarea>", \
"task_body": "<descripción concreta de qué evaluar/implementar, en castellano, incluyendo las \
constraints de la capacidad si las tiene>"}}

Si SÍ hay encaje pero NINGUNA capacidad declarada del proyecto aplica (relación genérica, no \
una de sus acciones concretas):
{{"matches": true, "project_slug": "<slug exacto de la lista de proyectos>", \
"capability_id": null, "tenant": null, \
"telegram_note": "<1-2 frases en castellano explicando el encaje, para mostrar al usuario>", \
"task_title": "<título corto y accionable de la tarea>", \
"task_body": "<descripción concreta de qué implementar, en castellano>"}}

Sé exigente: solo marca encaje si la iniciativa es concreta y accionable, no una vaga relación \
temática. Prioriza que "when" de una capacidad declarada matchee sobre un encaje genérico — es \
una señal mucho más fuerte que "el tema se parece". project_slug SIEMPRE debe ser uno de los \
proyectos listados, nunca de la infraestructura.

Proyectos (slug: nombre — descripción — capacidades declaradas):
{projects}

Infraestructura desplegada (contexto, no es destino de tarea):
{infra}

Nota:
{note}
"""


def load_notes(vault_dir: Path) -> list[str]:
    return [p.read_text(encoding="utf-8") for p in sorted(vault_dir.glob("*.md"))]


def load_projects(projects_file: Path = PROJECTS_FILE) -> str:
    if not projects_file.exists():
        return "(sin lista de proyectos configurada)"
    return projects_file.read_text(encoding="utf-8")


def format_notes(notes: list[str]) -> str:
    return "\n\n---\n\n".join(notes)


def review(notes: list[str], projects: str | None = None) -> str:
    api_key = os.environ["DEEPSEEK_API_KEY"]
    resp = httpx.post(
        DEEPSEEK_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "user",
                    "content": PROMPT.format(
                        projects=projects or load_projects(), notes=format_notes(notes)
                    ),
                }
            ],
        },
        timeout=90,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def load_repos(repos_file: Path = REPOS_FILE) -> dict:
    if not repos_file.exists():
        return {}
    return json.loads(repos_file.read_text(encoding="utf-8"))


def load_infra(infra_file: Path = INFRA_FILE) -> str:
    if not infra_file.exists():
        return "(sin infraestructura documentada)"
    return infra_file.read_text(encoding="utf-8")


def _format_project(slug: str, info: dict) -> str:
    line = f"- {slug}: {info['name']} — {info.get('description', '')}"
    caps = info.get("capabilities") or []
    if not caps:
        return line
    cap_lines = "\n".join(
        f"    - {c['id']}: cuando {c.get('when', '').strip()} -> {c.get('action', '').strip()}"
        for c in caps
        if "id" in c
    )
    return f"{line}\n  Capacidades declaradas:\n{cap_lines}"


def evaluate_fit(note: str, repos: dict | None = None, infra: str | None = None) -> dict | None:
    """Evalúa si una nota tiene encaje accionable en algún proyecto. Devuelve None si no, o
    {"project_slug", "telegram_note", "task_title", "task_body"} si sí."""
    repos = repos if repos is not None else load_repos()
    if not repos:
        return None
    projects_list = "\n".join(_format_project(slug, info) for slug, info in repos.items())
    api_key = os.environ["DEEPSEEK_API_KEY"]
    resp = httpx.post(
        DEEPSEEK_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "user",
                    "content": FIT_PROMPT.format(
                        projects=projects_list, infra=infra or load_infra(), note=note
                    ),
                }
            ],
            "response_format": {"type": "json_object"},
        },
        timeout=60,
    )
    resp.raise_for_status()
    result = json.loads(resp.json()["choices"][0]["message"]["content"])
    if not result.get("matches") or result.get("project_slug") not in repos:
        return None
    return result
