"""Self-check mínimo: enlaces y resumen de cola del dashboard."""
from dashboard import _links, _status_of, _summary_bar


def test_links_shows_pr_and_retry():
    html = _links({"task_id": "t1", "pr_url": "https://x/pull/1", "status": "pending", "_filename": "a.md"})
    assert "PR ↗" in html
    assert "/retry/a.md" in html


def test_links_no_retry_once_dispatched():
    html = _links({"task_id": "t1", "status": "dispatched", "_filename": "a.md"})
    assert "/retry/" not in html


def test_status_of_prefers_agent_loops_status():
    note = {"dispatch": {"status": "dispatched", "agent_loops_status": "running"}}
    assert _status_of(note) == "running"


def test_summary_bar_counts_and_filters():
    notes = [
        {"dispatch": {"status": "pending"}},
        {"dispatch": {"status": "pending"}},
        {"dispatch": {"status": "dispatched", "agent_loops_status": "done"}},
    ]
    html = _summary_bar(notes, "pending")
    assert "sin encolar · 2" in html
    assert "terminada · 1" in html


if __name__ == "__main__":
    test_links_shows_pr_and_retry()
    test_links_no_retry_once_dispatched()
    test_status_of_prefers_agent_loops_status()
    test_summary_bar_counts_and_filters()
    print("OK")
