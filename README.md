[🇬🇧 English](README.md) · [🇪🇸 Castellano](README.es.md)

---

# 🗒️ obsidian-ideas

A Telegram bot that turns links and half-formed ideas into searchable Obsidian notes — and, when an idea concretely matches something one of your own projects can act on, dispatches an autonomous task for it.

## What it does

1. **Capture** — paste a link or a thought into the bot. It fetches/summarizes it (via an LLM) and saves it as a Markdown note in your Obsidian vault, tagged.
2. **Search** — `/buscar <term>` searches your saved notes.
3. **Match** — each note is checked against a list of your active projects (built from their `README.md`, plus an optional `AGENTS.md` capability block — see below). If there's a concrete fit, you get a one-line explanation in Telegram.
4. **Dispatch** — if the project declares a matching capability, the bot opens an autonomous task against an orchestrator API (any service implementing the small contract below — [agent-loops](https://github.com/danifernandezs/agent-loops)-shaped, but not tied to it). If the orchestrator is unreachable (e.g. your machine is off), the note is queued and retried on a weekly digest.

## Quick start

```bash
cp .env.example .env
# fill in TELEGRAM_TOKEN, DEEPSEEK_API_KEY, VAULT_HOST_PATH, ...
docker compose up -d
```

## Declaring what a project can do

Drop an `AGENTS.md` in any of your repos with a fenced `capabilities` block:

```yaml
capabilities:
  - id: evaluate-llm-candidate
    when: "a note mentions a new open-weight LLM release that fits your hardware"
    action: "open a task benchmarking it against your current setup"
    constraints:
      - "never auto-promote — only produce a verdict for a human to review"
```

Run `python3 generate_projects.py` (reads every repo under a configured code directory) to rebuild `projects.md`/`repos.json` — the digest the matcher uses. A capability match is a much stronger signal than "the topic sounds related", and the matcher is instructed to prefer it.

## Orchestrator API contract

The bot expects, at `AGENT_LOOPS_URL`:

| Endpoint | Purpose |
|---|---|
| `GET /api/boards` | list boards (one per project slug) |
| `POST /api/boards` | create a board if missing |
| `POST /api/tasks` | create a task (`title`, `body`, `repo_url`, `repo_branch`, `board`, optional `tenant`) |

This is optional — without `AGENT_LOOPS_URL` set, the bot still captures and searches notes, it just never dispatches.

## Requirements

- A Telegram bot token (via [@BotFather](https://t.me/BotFather))
- A DeepSeek API key (summarization + fit matching)
- An Obsidian vault (or any folder of Markdown files) reachable from the host running Docker

## Security

- Telegram user ID allowlist (`TELEGRAM_ALLOWED_USERS`)
- `.env` excluded via `.gitignore` — never commit secrets
- The bot only ever opens tasks on a feature branch (`task/<id>`), never touches `main` directly
