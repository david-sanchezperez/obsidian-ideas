"""Self-check mínimo: extracción de descripción desde un README."""
from pathlib import Path

from generate_projects import extract_capabilities, extract_description


def test_extract_description(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text(
        "[🇬🇧 English](README.md)\n\n---\n\n# Mi Proyecto\n\nUna línea.\nOtra línea.\n\n## Instalación\n",
        encoding="utf-8",
    )
    assert extract_description(readme) == "**Mi Proyecto** — Una línea. Otra línea."


def test_extract_description_skips_badges(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text("# Proyecto\n\n![CI](badge.svg)\n\nDescripción real.\n", encoding="utf-8")
    assert extract_description(readme) == "**Proyecto** — Descripción real."


def test_extract_description_no_title(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text("Solo texto, sin título.\n", encoding="utf-8")
    assert extract_description(readme) is None


def test_extract_capabilities(tmp_path: Path):
    (tmp_path / "AGENTS.md").write_text(
        "# AGENTS.md\n\n## Capacidades para dispatch automático\n\n"
        "```yaml\ncapabilities:\n  - id: evaluate-llm-candidate\n"
        "    when: algo\n    action: algo\n```\n",
        encoding="utf-8",
    )
    caps = extract_capabilities(tmp_path)
    assert len(caps) == 1
    assert caps[0]["id"] == "evaluate-llm-candidate"


def test_extract_capabilities_no_agents_md(tmp_path: Path):
    assert extract_capabilities(tmp_path) == []


def test_extract_capabilities_malformed_yaml(tmp_path: Path):
    (tmp_path / "AGENTS.md").write_text(
        "## Capacidades para dispatch automático\n\n```yaml\ncapabilities: [not: valid: yaml\n```\n",
        encoding="utf-8",
    )
    assert extract_capabilities(tmp_path) == []


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        test_extract_description(Path(d))
        test_extract_description_skips_badges(Path(d))
        test_extract_description_no_title(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_extract_capabilities(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_extract_capabilities_no_agents_md(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_extract_capabilities_malformed_yaml(Path(d))
    print("OK")
