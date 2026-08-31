"""Construcción de notas Markdown para el vault de ideas."""
import json
import re
from datetime import date
from pathlib import Path

VAULT_DIR = Path(__file__).parent / "vault"

# Vocabulario cerrado de tags. Añadir aquí para ampliarlo — el LLM y los
# hashtags manuales del mensaje solo pueden usar valores de esta lista.
# Vive aquí (módulo ligero, sin deps de red/scraping) para que dashboard.py
# no tenga que arrastrar httpx/trafilatura/pypdf solo por esta lista.
ALLOWED_TAGS = [
    "agentes-ia",
    "modelos-llm",
    "infraestructura-local",
    "seguridad-gobernanza",
    "investigacion",
    "arquitectura-multimodelo",
    "second-brain",
    "otros",
    "todo",
    "learning",
]

DISPATCH_RE = re.compile(r"\n?<!-- dispatch: (.*) -->\n?$")
TAGS_LINE_RE = re.compile(r"^tags: \[(.*)\]$", re.MULTILINE)


def read_tags(path: Path) -> list[str]:
    match = TAGS_LINE_RE.search(path.read_text(encoding="utf-8"))
    if not match or not match.group(1).strip():
        return []
    return [t.strip() for t in match.group(1).split(",")]


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
TITLE_LINE_RE = re.compile(r'^title: "(.*)"$', re.MULTILINE)
DATE_LINE_RE = re.compile(r"^date: (.*)$", re.MULTILINE)
SOURCE_LINE_RE = re.compile(r"^source: (.*)$", re.MULTILINE)
HASHTAGS_LINE_RE = re.compile(r"\n#[\w-].*$", re.MULTILINE)
SOURCE_LINK_LINE_RE = re.compile(r"\n🔗 .*$", re.MULTILINE)


def parse_note(path: Path) -> dict:
    """Nota completa ya parseada: title, date, tags, source, body (resumen,
    sin frontmatter/hashtags/comentario de dispatch) y dispatch (si tiene)."""
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    frontmatter, body = (match.group(1), match.group(2)) if match else ("", text)

    title_match = TITLE_LINE_RE.search(frontmatter)
    date_match = DATE_LINE_RE.search(frontmatter)
    source_match = SOURCE_LINE_RE.search(frontmatter)

    body = DISPATCH_RE.sub("", body)
    body = HASHTAGS_LINE_RE.sub("", body)
    body = SOURCE_LINK_LINE_RE.sub("", body)
    # quita la primera línea "# Título" — ya está en el campo title
    body = re.sub(r"^\n?# .*\n", "", body, count=1)

    return {
        "filename": path.name,
        "title": title_match.group(1) if title_match else path.stem,
        "date": date_match.group(1) if date_match else "",
        "tags": read_tags(path),
        "source": source_match.group(1) if source_match else None,
        "body": body.strip(),
        "dispatch": read_dispatch(path),
    }


def slugify(text: str, max_len: int = 60) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_-]+", "-", slug).strip("-")
    return slug[:max_len] or "nota"


def build_note(title: str, summary: str, tags: list[str], source_url: str | None) -> str:
    tags_line = " ".join(f"#{t}" for t in tags) if tags else ""
    frontmatter = [
        "---",
        f"title: \"{title}\"",
        f"date: {date.today().isoformat()}",
        f"tags: [{', '.join(tags)}]",
    ]
    if source_url:
        frontmatter.append(f"source: {source_url}")
    frontmatter.append("---")

    lines = frontmatter + ["", f"# {title}", "", summary]
    if source_url:
        lines += ["", f"🔗 {source_url}"]
    if tags_line:
        lines += ["", tags_line]
    return "\n".join(lines) + "\n"


def save_note(title: str, summary: str, tags: list[str], source_url: str | None) -> Path:
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{date.today().isoformat()}-{slugify(title)}.md"
    path = VAULT_DIR / filename
    # evita sobreescribir si ya existe una nota con el mismo slug hoy
    i = 2
    while path.exists():
        path = VAULT_DIR / f"{date.today().isoformat()}-{slugify(title)}-{i}.md"
        i += 1
    path.write_text(build_note(title, summary, tags, source_url), encoding="utf-8")
    return path


def read_dispatch(path: Path) -> dict | None:
    """Lee el estado de despacho de una nota, si tiene ({"status", "project_slug", ...})."""
    match = DISPATCH_RE.search(path.read_text(encoding="utf-8"))
    return json.loads(match.group(1)) if match else None


def write_dispatch(path: Path, status: str, fit: dict, task: dict | None = None) -> None:
    """Anota (o actualiza) el estado de despacho al final de una nota ya guardada.

    task: respuesta cruda de POST /api/tasks en agent-loops (id, board_id,
    status...), si ya se conoce — permite luego consultar/enlazar la tarea real
    en vez de perder el rastro tras el despacho inicial.
    """
    text = DISPATCH_RE.sub("", path.read_text(encoding="utf-8")).rstrip("\n")
    payload = {
        "status": status,
        "project_slug": fit["project_slug"],
        "task_title": fit["task_title"],
        "task_body": fit["task_body"],
    }
    if task:
        payload["task_id"] = task.get("id")
        payload["board_id"] = task.get("board_id")
        payload["agent_loops_status"] = task.get("status")
    else:
        # preserva task_id/board_id ya conocidos si solo se actualiza el status
        # (p.ej. el sync periódico marcando done/blocked sobre un dispatch previo)
        prev = read_dispatch(path)
        if prev:
            for k in ("task_id", "board_id", "agent_loops_status"):
                if k in prev:
                    payload[k] = prev[k]
    text += f"\n<!-- dispatch: {json.dumps(payload, ensure_ascii=False)} -->\n"
    path.write_text(text, encoding="utf-8")
