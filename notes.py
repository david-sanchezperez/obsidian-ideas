"""Construcción de notas Markdown para el vault de ideas."""
import json
import re
from datetime import date
from pathlib import Path

VAULT_DIR = Path(__file__).parent / "vault"

DISPATCH_RE = re.compile(r"\n?<!-- dispatch: (.*) -->\n?$")
TAGS_LINE_RE = re.compile(r"^tags: \[(.*)\]$", re.MULTILINE)


def read_tags(path: Path) -> list[str]:
    match = TAGS_LINE_RE.search(path.read_text(encoding="utf-8"))
    if not match or not match.group(1).strip():
        return []
    return [t.strip() for t in match.group(1).split(",")]


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


def write_dispatch(path: Path, status: str, fit: dict) -> None:
    """Anota (o actualiza) el estado de despacho al final de una nota ya guardada."""
    text = DISPATCH_RE.sub("", path.read_text(encoding="utf-8")).rstrip("\n")
    payload = {
        "status": status,
        "project_slug": fit["project_slug"],
        "task_title": fit["task_title"],
        "task_body": fit["task_body"],
    }
    text += f"\n<!-- dispatch: {json.dumps(payload, ensure_ascii=False)} -->\n"
    path.write_text(text, encoding="utf-8")
