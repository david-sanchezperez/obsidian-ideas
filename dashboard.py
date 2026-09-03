"""Panel web para el vault: ver qué se ha guardado, con qué tags, qué pasó con
cada idea despachada a agent-loops (cola, PR) — y forzar el reintento de una
idea 'pending'. http.server, como idea-pr-opener — sin dependencias nuevas
más allá de las que ya trae el resto del bot (httpx, vía dispatch.py).
"""
import os
from datetime import datetime
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from dispatch import retry_one
from notes import ALLOWED_TAGS, VAULT_DIR, parse_note, read_dispatch
from review import load_repos

PORT = int(os.environ.get("DASHBOARD_PORT", "8788"))
AGENT_LOOPS_URL = os.environ.get("AGENT_LOOPS_URL", "")

STATUS_BADGES = {
    "pending": ("⏳ sin encolar", "#8a6d3b"),
    "dispatched": ("🕒 en cola", "#31708f"),
    "triage": ("🕒 en cola", "#31708f"),
    "todo": ("🕒 en cola", "#31708f"),
    "ready": ("🕒 lista", "#31708f"),
    "running": ("⚙️ trabajándose", "#2e6da4"),
    "blocked": ("🚧 bloqueada", "#a94442"),
    "done": ("✅ terminada", "#3c763d"),
    "archived": ("✅ terminada", "#3c763d"),
    "gave_up": ("❌ abandonada", "#a94442"),
}

# Estados "en curso" (ni pending sin encolar, ni terminales) para el resumen.
QUEUE_STATUSES = ("dispatched", "triage", "todo", "ready", "running", "blocked")

PAGE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Vault de ideas</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 900px;
          margin: 0 auto; padding: 24px 16px 64px; line-height: 1.5; }}
  h1 {{ font-size: 1.4rem; }}
  .toolbar {{ display: flex; gap: 8px; flex-wrap: wrap; margin: 16px 0 24px; }}
  .toolbar a, .toolbar select {{ font-size: 0.85rem; padding: 4px 10px; border-radius: 999px;
          border: 1px solid #8888; text-decoration: none; color: inherit; }}
  .toolbar a.active {{ background: #8884; font-weight: 600; }}
  .card {{ border: 1px solid #8885; border-radius: 10px; padding: 14px 16px; margin-bottom: 14px; }}
  .card h2 {{ font-size: 1.05rem; margin: 0 0 4px; }}
  .card h2 a {{ color: inherit; text-decoration: none; }}
  .meta {{ font-size: 0.8rem; opacity: 0.65; margin-bottom: 8px; }}
  .badge {{ display: inline-block; font-size: 0.75rem; padding: 2px 8px; border-radius: 999px;
          color: white; margin-left: 6px; }}
  .tags {{ margin-top: 8px; }}
  .tags a {{ font-size: 0.75rem; opacity: 0.75; margin-right: 8px; text-decoration: none; }}
  .empty {{ opacity: 0.6; padding: 40px 0; text-align: center; }}
  .body {{ white-space: pre-wrap; }}
  .backlink {{ font-size: 0.85rem; margin-bottom: 16px; display: inline-block; }}
</style>
</head>
<body>
<h1>📓 Vault de ideas</h1>
{content}
</body>
</html>"""


def _badge(status: str | None) -> str:
    if not status:
        return ""
    label, color = STATUS_BADGES.get(status, (status, "#8888"))
    return f'<span class="badge" style="background:{color}">{escape(label)}</span>'


def _links(dispatch: dict) -> str:
    links = ""
    if dispatch.get("task_id") and AGENT_LOOPS_URL:
        links += f' · <a href="{escape(AGENT_LOOPS_URL)}/dashboard" target="_blank">ver en agent-loops ↗</a>'
    if dispatch.get("pr_url"):
        links += f' · <a href="{escape(dispatch["pr_url"])}" target="_blank">🔀 PR ↗</a>'
    if dispatch.get("status") == "pending":
        links += f' · <a href="/retry/{escape(dispatch.get("_filename", ""))}">🔁 reintentar ahora</a>'
    return links


def _card(note: dict) -> str:
    dispatch = dict(note["dispatch"] or {})
    dispatch["_filename"] = note["filename"]
    status = dispatch.get("agent_loops_status") or dispatch.get("status")
    excerpt = note["body"][:220] + ("…" if len(note["body"]) > 220 else "")
    tags_html = "".join(
        f'<a href="/?tag={escape(t)}">#{escape(t)}</a>' for t in note["tags"]
    )
    return f"""<div class="card">
  <h2><a href="/note/{escape(note['filename'])}">{escape(note['title'])}</a>{_badge(status)}</h2>
  <div class="meta">{escape(note['date'])}{_links(dispatch)}</div>
  <div>{escape(excerpt)}</div>
  <div class="tags">{tags_html}</div>
</div>"""


def _status_of(note: dict) -> str | None:
    dispatch = note["dispatch"] or {}
    return dispatch.get("agent_loops_status") or dispatch.get("status")


def _summary_bar(notes: list[dict], status: str | None) -> str:
    counts: dict[str, int] = {}
    for n in notes:
        s = _status_of(n)
        if s:
            counts[s] = counts.get(s, 0) + 1
    if not counts:
        return ""
    parts = []
    for s, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        label = STATUS_BADGES.get(s, (s, "#8888"))[0]
        cls = "active" if s == status else ""
        parts.append(f'<a href="/?status={escape(s)}" class="{cls}">{escape(label)} · {count}</a>')
    return '<div class="toolbar">' + "".join(parts) + "</div>"


def _list_page(tag: str | None, q: str | None, status: str | None) -> str:
    notes = [parse_note(p) for p in sorted(VAULT_DIR.glob("*.md"), reverse=True)]
    summary = _summary_bar(notes, status)
    if tag:
        notes = [n for n in notes if tag in n["tags"]]
    if status:
        notes = [n for n in notes if _status_of(n) == status]
    if q:
        ql = q.lower()
        notes = [n for n in notes if ql in n["title"].lower() or ql in n["body"].lower()]

    all_tags = sorted({t for n in notes for t in n["tags"]} | set(ALLOWED_TAGS))
    toolbar = ['<div class="toolbar">']
    toolbar.append(f'<a href="/" class="{"active" if not tag and not status else ""}">todas</a>')
    for t in all_tags:
        cls = "active" if t == tag else ""
        toolbar.append(f'<a href="/?tag={escape(t)}" class="{cls}">#{escape(t)}</a>')
    toolbar.append("</div>")

    cards = "".join(_card(n) for n in notes) or '<div class="empty">Sin notas con este filtro.</div>'
    return summary + "".join(toolbar) + f'<div class="meta">{len(notes)} nota(s)</div>' + cards


def _note_page(filename: str) -> str | None:
    path = (VAULT_DIR / filename).resolve()
    if path.parent != VAULT_DIR.resolve() or not path.exists():
        return None
    note = parse_note(path)
    dispatch = dict(note["dispatch"] or {})
    dispatch["_filename"] = note["filename"]
    status = dispatch.get("agent_loops_status") or dispatch.get("status")
    source = f'<p>🔗 <a href="{escape(note["source"])}">{escape(note["source"])}</a></p>' if note["source"] else ""
    task_info = ""
    if note["dispatch"]:
        task_info = f"""<p><strong>Despacho:</strong> {_badge(status)}
          proyecto: {escape(dispatch.get('project_slug', '?'))}{_links(dispatch)}</p>"""
    tags_html = " ".join(f"#{escape(t)}" for t in note["tags"])
    return (
        '<a class="backlink" href="/">← volver</a>'
        f"<h2>{escape(note['title'])}</h2>"
        f'<div class="meta">{escape(note["date"])}</div>'
        f"{source}{task_info}"
        f'<div class="body">{escape(note["body"])}</div>'
        f'<p class="tags">{tags_html}</p>'
    )


class Handler(BaseHTTPRequestHandler):
    def _send_html(self, content: str, code: int = 200) -> None:
        body = PAGE.format(content=content).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        qs = parse_qs(url.query)
        if url.path == "/":
            content = _list_page(qs.get("tag", [None])[0], qs.get("q", [None])[0], qs.get("status", [None])[0])
            self._send_html(content)
        elif url.path.startswith("/note/"):
            filename = url.path.removeprefix("/note/")
            content = _note_page(filename)
            if content is None:
                self._send_html('<div class="empty">Nota no encontrada.</div>', 404)
            else:
                self._send_html(content)
        elif url.path.startswith("/retry/"):
            filename = url.path.removeprefix("/retry/")
            path = (VAULT_DIR / filename).resolve()
            if path.parent == VAULT_DIR.resolve() and path.exists():
                retry_one(path, load_repos())
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
        else:
            self._send_html('<div class="empty">404.</div>', 404)

    def log_message(self, *args):
        pass


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Vault dashboard en :{PORT} (vault: {VAULT_DIR})")
    server.serve_forever()


if __name__ == "__main__":
    main()
