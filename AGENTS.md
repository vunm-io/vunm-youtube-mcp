# AGENTS.md — vunm-youtube-mcp

Source of truth for AI agents working in this repository. This is an independent public open-source project (`vunm-io/vunm-youtube-mcp`).

## What this repo is

An MCP server, written in Python with FastMCP, that connects AI assistants to the YouTube Data API v3 and the YouTube Analytics API v2. It runs over stdio, authorizes with Google's OAuth 2.0 desktop flow (or an API key in `public` mode), and is installed with `uvx` from a git tag.

Layout: `src/vunm_youtube_mcp/` — `cli.py` (`serve`, `auth`), `server.py` (`build_server`, tool definitions per mode), `config.py` (settings from the environment), `auth.py` (tokens), `services.py` (Google clients behind `ServiceProvider`), `errors.py` (Google failures to `ToolError`), and one module per tool group: `studio.py`, `analytics.py`, `transcript.py`, `search.py`.

## Invariants

1. **Zero secret leakage**: `credentials/`, `client_secret*.json`, `token*.json` and `.env*` files must never be tracked or committed. Credentials live in the per-user config directory, outside the repository.
2. **Quota efficiency**, by Google's current model ([quota table](https://developers.google.com/youtube/v3/determine_quota_cost)): `search.list` and `videos.insert` each have their own bucket of 100 calls a day, one per call; every other method shares 10,000 units a day; `videos.update` costs 50 and list methods cost 1. Read the uploads playlist (`playlistItems.list`) rather than searching for the channel's own videos, keep writes behind a dry-run preview, and state each tool's cost in its description.
3. **stdout carries MCP messages only** while serving: log through `logging` (stderr), never `print` in server code. Only the interactive `auth` command prints.
4. **Errors are `ToolError`s** with a cause and a next step; never return `{"error": ...}`.
5. **Tests never reach the network**: build servers with `build_server(settings, provider, transcripts)` and the fakes in `tests/fakes.py`. Fixtures use synthetic IDs and names only.
6. **Public Git hygiene**: Conventional Commits in English, imperative mood. No merge commits, clean linear history.

## Development & testing

```bash
uv sync                      # Python, dependencies and dev tools
uv run pytest                # the test suite
uv run ruff check            # lint
uv run ruff format           # format (CI runs --check)
uv build                     # wheel and sdist
uv run vunm-youtube-mcp --help
```

CI (`.github/workflows/ci.yml`) runs the same steps on Python 3.10 and 3.14 and installs the built wheel into a clean venv. Pin new dependencies exactly and commit `uv.lock`.
