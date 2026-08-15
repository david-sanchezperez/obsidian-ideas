"""Self-check mínimo: generación de notas y slugs."""
from pathlib import Path

from notes import build_note, read_dispatch, slugify, write_dispatch


def test_slugify():
    assert slugify("¡Hola, Mundo! 123") == "hola-mundo-123"
    assert slugify("") == "nota"


def test_build_note_with_source():
    md = build_note("Título", "Un resumen.", ["ia", "memoria"], "https://example.com")
    assert "title: \"Título\"" in md
    assert "https://example.com" in md
    assert "#ia" in md and "#memoria" in md


def test_build_note_without_source():
    md = build_note("Idea suelta", "Resumen breve.", [], None)
    assert "source:" not in md
    assert "Idea suelta" in md


def test_dispatch_roundtrip(tmp_path: Path):
    path = tmp_path / "nota.md"
    path.write_text(build_note("T", "Resumen.", [], None), encoding="utf-8")
    assert read_dispatch(path) is None

    fit = {"project_slug": "ctxlint", "task_title": "x", "task_body": "y"}
    write_dispatch(path, "pending", fit)
    assert read_dispatch(path) == {"status": "pending", **fit}

    write_dispatch(path, "dispatched", fit)
    result = read_dispatch(path)
    assert result["status"] == "dispatched"
    assert "Resumen." in path.read_text(encoding="utf-8")  # el contenido original no se pierde


if __name__ == "__main__":
    import tempfile

    test_slugify()
    test_build_note_with_source()
    test_build_note_without_source()
    with tempfile.TemporaryDirectory() as d:
        test_dispatch_roundtrip(Path(d))
    print("OK")
