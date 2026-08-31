"""Self-check mínimo: reintento de tareas pendientes."""
from pathlib import Path
from unittest.mock import MagicMock, patch

from dispatch import dispatch_task, retry_pending, sync_dispatch_statuses
from notes import build_note, read_dispatch, write_dispatch

REPOS = {"ctxlint": {"name": "ctxlint", "repo_url": "x", "repo_branch": "main"}}
FIT = {"project_slug": "ctxlint", "task_title": "t", "task_body": "b"}


def test_retry_pending_success(tmp_path: Path):
    note = tmp_path / "a.md"
    note.write_text(build_note("T", "R", [], None), encoding="utf-8")
    write_dispatch(note, "pending", FIT)

    with patch("dispatch.dispatch_task", return_value={"id": "t1"}):
        attempted, ok = retry_pending(tmp_path, REPOS)
    assert (attempted, ok) == (1, 1)

    from notes import read_dispatch
    assert read_dispatch(note)["status"] == "dispatched"


def test_retry_pending_keeps_pending_on_failure(tmp_path: Path):
    note = tmp_path / "a.md"
    note.write_text(build_note("T", "R", [], None), encoding="utf-8")
    write_dispatch(note, "pending", FIT)

    with patch("dispatch.dispatch_task", side_effect=RuntimeError("PC apagado")):
        attempted, ok = retry_pending(tmp_path, REPOS)
    assert (attempted, ok) == (1, 0)

    from notes import read_dispatch
    assert read_dispatch(note)["status"] == "pending"


def test_retry_pending_ignores_dispatched_and_no_fit(tmp_path: Path):
    dispatched = tmp_path / "b.md"
    dispatched.write_text(build_note("T", "R", [], None), encoding="utf-8")
    write_dispatch(dispatched, "dispatched", FIT)

    no_fit = tmp_path / "c.md"
    no_fit.write_text(build_note("T", "R", [], None), encoding="utf-8")

    with patch("dispatch.dispatch_task") as mock_dispatch:
        attempted, ok = retry_pending(tmp_path, REPOS)
    assert (attempted, ok) == (0, 0)
    mock_dispatch.assert_not_called()


def _mock_client():
    """Simula httpx.Client: /api/boards ya existe, /api/tasks devuelve {'id': 't1'}."""
    client = MagicMock()
    client.__enter__.return_value = client
    client.get.return_value = MagicMock(json=lambda: [{"slug": "ctxlint"}], raise_for_status=lambda: None)
    client.post.return_value = MagicMock(json=lambda: {"id": "t1"}, raise_for_status=lambda: None)
    return client


def test_dispatch_task_sets_tenant_and_skips_auto_decompose():
    client = _mock_client()
    fit = {**FIT, "tenant": "host_gpu"}
    with patch("dispatch.AGENT_LOOPS_URL", "http://x"), \
         patch("dispatch.httpx.Client", return_value=client):
        dispatch_task(fit, REPOS["ctxlint"])
    payload = client.post.call_args.kwargs["json"]
    assert payload["tenant"] == "host_gpu"
    assert payload["auto_decompose"] is False


def test_dispatch_task_without_tenant_keeps_auto_decompose():
    client = _mock_client()
    with patch("dispatch.AGENT_LOOPS_URL", "http://x"), \
         patch("dispatch.httpx.Client", return_value=client):
        dispatch_task(FIT, REPOS["ctxlint"])
    payload = client.post.call_args.kwargs["json"]
    assert "tenant" not in payload
    assert payload["auto_decompose"] is True


def _mock_status_client(status: str):
    client = MagicMock()
    client.__enter__.return_value = client
    client.get.return_value = MagicMock(
        json=lambda: {"id": "t1", "board_id": 1, "status": status},
        raise_for_status=lambda: None,
    )
    return client


def test_sync_reports_transition_to_terminal_status(tmp_path: Path):
    note = tmp_path / "a.md"
    note.write_text(build_note("T", "R", [], None), encoding="utf-8")
    write_dispatch(note, "dispatched", FIT, {"id": "t1", "board_id": 1, "status": "running"})

    with patch("dispatch.AGENT_LOOPS_URL", "http://x"), \
         patch("dispatch.httpx.Client", return_value=_mock_status_client("done")):
        changed = sync_dispatch_statuses(tmp_path)

    assert len(changed) == 1
    assert changed[0]["status"] == "done"
    assert read_dispatch(note)["agent_loops_status"] == "done"


def test_sync_ignores_unchanged_status(tmp_path: Path):
    note = tmp_path / "a.md"
    note.write_text(build_note("T", "R", [], None), encoding="utf-8")
    write_dispatch(note, "dispatched", FIT, {"id": "t1", "board_id": 1, "status": "running"})

    with patch("dispatch.AGENT_LOOPS_URL", "http://x"), \
         patch("dispatch.httpx.Client", return_value=_mock_status_client("running")):
        changed = sync_dispatch_statuses(tmp_path)

    assert changed == []


def test_sync_skips_notes_already_in_terminal_status(tmp_path: Path):
    note = tmp_path / "a.md"
    note.write_text(build_note("T", "R", [], None), encoding="utf-8")
    write_dispatch(note, "dispatched", FIT, {"id": "t1", "board_id": 1, "status": "done"})

    client = _mock_status_client("done")
    with patch("dispatch.AGENT_LOOPS_URL", "http://x"), \
         patch("dispatch.httpx.Client", return_value=client):
        changed = sync_dispatch_statuses(tmp_path)

    assert changed == []
    client.get.assert_not_called()  # ya terminal, ni se consulta


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        test_retry_pending_success(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_retry_pending_keeps_pending_on_failure(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_retry_pending_ignores_dispatched_and_no_fit(Path(d))
    test_dispatch_task_sets_tenant_and_skips_auto_decompose()
    test_dispatch_task_without_tenant_keeps_auto_decompose()
    with tempfile.TemporaryDirectory() as d:
        test_sync_reports_transition_to_terminal_status(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_sync_ignores_unchanged_status(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_sync_skips_notes_already_in_terminal_status(Path(d))
    print("OK")
