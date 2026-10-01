# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [0.2.0] - Unreleased

### Breaking changes

- The entry point is the `vunm-youtube-mcp` command (`serve` by default), also
  `python -m vunm_youtube_mcp`; `src.server:mcp.run` and `python -m src.server`
  are gone.
- `authenticate.py` is removed; run `vunm-youtube-mcp auth`.
- Credentials live in the per-user config directory (`YOUTUBE_CREDENTIALS_DIR`
  overrides it) instead of `<checkout>/credentials/`.
- Failures are MCP tool errors instead of `{"error": ...}` results.
- A tool call no longer starts the browser flow; it asks you to run
  `vunm-youtube-mcp auth`.
- `youtube_update_video` previews by default; pass `dry_run=false` to write.
- `youtube_list_videos` returns `{videos, next_page_token}`.
- Analytics results use `rows` (channel report) and `metrics` (video report).
- `youtube_get_transcript` returns one `text` field instead of `raw_text` and
  `formatted_transcript`.
- Comments are returned as plain text.

### Added

- Modes through `YOUTUBE_MCP_MODE`: `full`, `read-only` (read-only scopes, no
  write tool) and `public` (an API key in `YOUTUBE_API_KEY`, public data only).
- `youtube_search_videos`, with its quota rule in its description.
- `youtube_list_videos` pages with `page_token`.
- Transcript fallback to yt-dlp, the optional `ytdlp` extra, when
  youtube-transcript-api is blocked; transcripts report `language_code`,
  `is_generated` and `source`, and `max_chars` cuts long ones.
- Write previews: the before and after of each field, warnings and the quota
  cost.
- Input validation (video IDs, dates, page sizes, title, description and tag
  limits) and tool annotations (read-only, destructive, idempotent) with titles.
- Tests with fake Google clients, CI on Python 3.10 and 3.14, Dependabot, and an
  installable package with exactly pinned dependencies and a `uv.lock`.

### Fixed

- Nothing but MCP messages reaches stdout while serving: logs and Python
  warnings go to stderr (`YOUTUBE_MCP_LOG_LEVEL`). v0.1 printed during token
  refresh, which broke the stdio transport.
- Writes keep every writable property of the parts they change; v0.1 could
  reset properties it did not send.
- Analytics default dates follow Pacific Time, the time zone YouTube Analytics
  reports in, and month reports use first-of-month dates as the API requires.

### Removed

- `requirements.txt` (use `uv sync`).

## [0.1.0] - 2026-09-05

- First release: eight tools for channel statistics, analytics, uploads, video
  metadata, transcripts and comments.

[0.2.0]: https://github.com/vunm-io/vunm-youtube-mcp/compare/1817840...v0.2.0
[0.1.0]: https://github.com/vunm-io/vunm-youtube-mcp/commit/1817840
