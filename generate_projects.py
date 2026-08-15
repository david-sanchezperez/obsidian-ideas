"""Genera projects.md y repos.json a partir de los repos en tu directorio de código.
Corre en local (no en el contenedor)."""
import json
import os
import re
import subprocess
from pathlib import Path

import yaml

CODE_DIR = Path(os.environ.get("CODE_DIR", "~/code")).expanduser()
OUTPUT = Path(__file__).parent / "projects.md"
REPOS_OUTPUT = Path(__file__).parent / "repos.json"
SKIP_FILE = Path(__file__).parent / "skip_repos.txt"


def load_skip() -> set[str]:
    """Repos a ignorar (este mismo repo siempre, más lo que liste skip_repos.txt —
    uno por línea, no versionado: cada usuario tiene sus propios repos de terceros
    o sensibles que no quiere que se evalúen ni se manden a una API externa)."""
    skip = {"obsidian-ideas"}
    if SKIP_FILE.exists():
        skip |= {line.strip() for line in SKIP_FILE.read_text().splitlines() if line.strip() and not line.startswith("#")}
    return skip


SKIP = load_skip()


def extract_description(readme: Path, max_chars: int = 700) -> str | None:
    """Título + todo el bloque de intro hasta el primer '## ' (no solo el primer párrafo),
    para que proyectos con TL;DR + sección explicativa (como loop-engineering-lab) no se
    queden en una frase suelta."""
    lines = readme.read_text(encoding="utf-8", errors="ignore").splitlines()
    title = None
    desc_lines = []
    for line in lines:
        if title is None:
            if line.startswith("# "):
                title = line[2:].strip()
            continue
        if line.startswith("## "):
            break
        stripped = line.strip().lstrip(">").strip()
        if not stripped or stripped.startswith("![") or stripped.startswith("[!["):
            continue
        desc_lines.append(stripped)
    if not title or not desc_lines:
        return None
    text = " ".join(desc_lines)
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + "…"
    return f"**{title}** — {text}"


def extract_capabilities(repo: Path) -> list[dict]:
    """Lee el bloque ```yaml capabilities: ...``` bajo '## Capacidades para dispatch
    automático' en AGENTS.md, si existe (ver local-llm-arena/AGENTS.md como plantilla).
    Le dice al clasificador de encaje QUÉ puede pedirle a este proyecto, no solo que
    existe. Ausente/mal formado -> sin capacidades declaradas, no rompe el resto."""
    agents_md = repo / "AGENTS.md"
    if not agents_md.exists():
        return []
    text = agents_md.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"```yaml\s*\n(capabilities:.*?)\n```", text, re.DOTALL)
    if not match:
        return []
    try:
        parsed = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return []
    return parsed.get("capabilities", []) if isinstance(parsed, dict) else []


def extract_title(readme: Path) -> str | None:
    for line in readme.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def repo_remote(repo: Path) -> tuple[str, str] | None:
    """Devuelve (remote_url, rama_por_defecto) del remoto 'origin' (siempre GitHub, ver [[ref_repos]])."""
    result = subprocess.run(
        ["git", "-C", str(repo), "remote", "get-url", "origin"],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    url = result.stdout.strip()
    branch_result = subprocess.run(
        ["git", "-C", str(repo), "symbolic-ref", "refs/remotes/origin/HEAD"],
        capture_output=True, text=True,
    )
    branch = branch_result.stdout.strip().rsplit("/", 1)[-1] if branch_result.returncode == 0 else "main"
    return url, branch


def generate() -> tuple[str, dict]:
    entries = []
    repos = {}
    for repo in sorted(p for p in CODE_DIR.iterdir() if p.is_dir()):
        if repo.name in SKIP:
            continue
        readme = repo / "README.md"
        if not readme.exists():
            continue
        desc = extract_description(readme)
        capabilities = extract_capabilities(repo)
        if desc:
            entry = f"- {desc}"
            if capabilities:
                ids = ", ".join(c["id"] for c in capabilities if "id" in c)
                entry += f" *(capacidades declaradas: {ids})*"
            entries.append(entry)
        remote = repo_remote(repo)
        if remote:
            url, branch = remote
            repos[repo.name] = {
                "name": extract_title(readme) or repo.name,
                "description": desc or "",
                "repo_url": url,
                "repo_branch": branch,
                "capabilities": capabilities,
            }
    header = "# Proyectos actuales\n\nGenerado automáticamente a partir de los README en ~/code. No editar a mano.\n\n"
    return header + "\n".join(entries) + "\n", repos


if __name__ == "__main__":
    projects_md, repos = generate()
    OUTPUT.write_text(projects_md, encoding="utf-8")
    REPOS_OUTPUT.write_text(json.dumps(repos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Escrito {OUTPUT} ({OUTPUT.stat().st_size} bytes)")
    print(f"Escrito {REPOS_OUTPUT} ({REPOS_OUTPUT.stat().st_size} bytes, {len(repos)} repos con remoto)")
