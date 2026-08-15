"""Self-check mínimo: carga y formateo de notas para revisión."""
import json
from pathlib import Path
from unittest.mock import patch

from review import evaluate_fit, format_notes, load_notes, load_projects, load_repos


def test_load_notes(tmp_path: Path):
    (tmp_path / "a.md").write_text("Nota A", encoding="utf-8")
    (tmp_path / "b.md").write_text("Nota B", encoding="utf-8")
    notes = load_notes(tmp_path)
    assert notes == ["Nota A", "Nota B"]


def test_format_notes():
    assert format_notes(["Nota A", "Nota B"]) == "Nota A\n\n---\n\nNota B"


def test_load_projects_missing(tmp_path: Path):
    assert load_projects(tmp_path / "no-existe.md") == "(sin lista de proyectos configurada)"


def test_load_projects_present(tmp_path: Path):
    f = tmp_path / "projects.md"
    f.write_text("- proyecto X", encoding="utf-8")
    assert "proyecto X" in load_projects(f)


def test_load_repos_missing(tmp_path: Path):
    assert load_repos(tmp_path / "no-existe.json") == {}


def _mock_llm_response(content: dict):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": json.dumps(content)}}]}

    return FakeResponse()


def test_evaluate_fit_no_match():
    repos = {"ctxlint": {"name": "ctxlint", "repo_url": "x", "repo_branch": "main"}}
    with patch("review.httpx.post", return_value=_mock_llm_response({"matches": False})), \
         patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test"}):
        assert evaluate_fit("nota irrelevante", repos) is None


def test_evaluate_fit_unknown_slug_ignored():
    repos = {"ctxlint": {"name": "ctxlint", "repo_url": "x", "repo_branch": "main"}}
    fake = {"matches": True, "project_slug": "no-existe", "telegram_note": "x",
            "task_title": "x", "task_body": "x"}
    with patch("review.httpx.post", return_value=_mock_llm_response(fake)), \
         patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test"}):
        assert evaluate_fit("nota", repos) is None


def test_evaluate_fit_match():
    repos = {"ctxlint": {"name": "ctxlint", "repo_url": "x", "repo_branch": "main"}}
    fake = {"matches": True, "project_slug": "ctxlint", "telegram_note": "x",
            "task_title": "x", "task_body": "x"}
    with patch("review.httpx.post", return_value=_mock_llm_response(fake)), \
         patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test"}):
        assert evaluate_fit("nota", repos)["project_slug"] == "ctxlint"


def test_evaluate_fit_no_repos_short_circuits():
    assert evaluate_fit("nota", {}) is None


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        test_load_notes(Path(d))
        test_load_projects_missing(Path(d))
        test_load_projects_present(Path(d))
        test_load_repos_missing(Path(d))
    test_format_notes()
    test_evaluate_fit_no_match()
    test_evaluate_fit_unknown_slug_ignored()
    test_evaluate_fit_match()
    test_evaluate_fit_no_repos_short_circuits()
    print("OK")
