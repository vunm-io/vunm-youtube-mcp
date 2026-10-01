# vunm-youtube-mcp

[![CI](https://github.com/vunm-io/vunm-youtube-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/vunm-io/vunm-youtube-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Model Context Protocol](https://img.shields.io/badge/MCP-stdio-green.svg)](https://modelcontextprotocol.io/)

An MCP server for your YouTube channel: channel statistics and analytics,
uploads, video metadata edits that preview before they write, comments,
transcripts and search. It is written in Python with
[FastMCP](https://gofastmcp.com) and talks to Google's official APIs.

> [!NOTE]
> [Bản tiếng Việt (Vietnamese translation)](README.vi.md).

## Tools

| Tool | What it does | Modes | YouTube Data API quota |
| :--- | :--- | :--- | :--- |
| `youtube_channel_stats` | Subscribers, total views, video count and profile of the authorized channel | full, read-only | 1 unit |
| `youtube_analytics_report` | Channel metrics (views, watch time, average view duration and percentage, subscribers gained and lost, likes, comments, shares) per day, month or country, or as totals | full, read-only | none (Analytics API) |
| `youtube_video_analytics` | The same metrics for one video, as totals | full, read-only | none (Analytics API) |
| `youtube_list_videos` | Uploads of the channel, newest first, including private and unlisted ones, a page at a time | full, read-only | 2 units a page, plus 1 on the first call |
| `youtube_get_video` | Title, description, tags, category, privacy, duration and statistics of a video | full, read-only, public | 1 unit |
| `youtube_get_comments` | Top-level comments on a video, as plain text | full, read-only, public | 1 unit |
| `youtube_update_video` | Change title, description, tags, category or privacy; previews by default | full | 1 unit to preview, 51 to write |
| `youtube_get_transcript` | The transcript of a public video, from its caption tracks | full, read-only, public | none |
| `youtube_search_videos` | Search YouTube for videos | full, read-only, public | 1 call of the search bucket |

Quota follows [Google's quota table](https://developers.google.com/youtube/v3/determine_quota_cost)
as checked on 2026-10-01: `search.list` and `videos.insert` each have their
own bucket of 100 calls a day, where each call counts as one; every other
method shares 10,000 units a day; `videos.update` costs 50 units and the list
methods cost 1. Quotas reset at midnight Pacific Time. Use
`youtube_list_videos` rather than search to list your own uploads.

## Modes

| Mode | Credentials | Tools |
| :--- | :--- | :--- |
| `full` (default) | OAuth, scopes `youtube` and `yt-analytics.readonly` | all 9 |
| `read-only` | OAuth, scopes `youtube.readonly` and `yt-analytics.readonly` | all but `youtube_update_video` (8) |
| `public` | an API key in `YOUTUBE_API_KEY`, no OAuth | `youtube_get_video`, `youtube_get_comments`, `youtube_get_transcript`, `youtube_search_videos` (4), public data only |

| Variable | Default | Meaning |
| :--- | :--- | :--- |
| `YOUTUBE_MCP_MODE` | `full` | `full`, `read-only` or `public` |
| `YOUTUBE_CREDENTIALS_DIR` | the per-user config directory (below) | where `client_secret.json` and `token.json` live |
| `YOUTUBE_API_KEY` | unset | the API key for `public` mode |
| `YOUTUBE_MCP_LOG_LEVEL` | `WARNING` | log level; logs go to stderr |

An invalid value stops the server with exit code 2 and a message on stderr.

## Install

You need [uv](https://docs.astral.sh/uv/). There is no PyPI package; install
a release tag from GitHub:

```bash
uvx --from "vunm-youtube-mcp[ytdlp] @ git+https://github.com/vunm-io/vunm-youtube-mcp@v0.2.0" vunm-youtube-mcp --help
```

The `ytdlp` extra adds the transcript fallback (see [Transcripts](#transcripts)).
Without it:

```bash
uvx --from git+https://github.com/vunm-io/vunm-youtube-mcp@v0.2.0 vunm-youtube-mcp --help
```

The command has two subcommands: `serve` (the default) runs the server over
stdio, and `auth` authorizes your channel.

## Set up OAuth (full and read-only modes)

1. In the [Google Cloud console](https://console.cloud.google.com/), create or
   pick a project and enable **YouTube Data API v3** and **YouTube Analytics API**.
2. Configure the OAuth consent screen. Its publishing status decides how long
   your authorization lasts:
   - **Testing**: add your Google account as a test user. Google expires a test
     user's authorization, refresh token included,
     [seven days after consent](https://support.google.com/cloud/answer/15549945),
     so you would run `auth` again every week.
   - **In production**: the authorization does not expire after seven days.
     YouTube scopes are sensitive (Google's
     [verification guide](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification)
     uses deleting a YouTube video as its example), so an app that Google has not
     verified shows Google's
     [unverified app screen](https://support.google.com/cloud/answer/7454865)
     before the consent screen, and is limited to 100 new users. For an app
     only you use, that screen is expected.
3. Create an OAuth client ID of type **Desktop app** and download its JSON file.
4. Run `vunm-youtube-mcp auth`. It creates the credentials directory and tells
   you where to save the file, as `client_secret.json` (the
   `client_secret_*.json` name Google downloads also works). Run it again: your
   browser opens Google's consent page, and the token is saved as `token.json`.
   For read-only mode, run `vunm-youtube-mcp auth --mode read-only`.

The credentials directory is the per-user config directory:
`~/Library/Application Support/vunm-youtube-mcp` on macOS,
`~/.config/vunm-youtube-mcp` on Linux and `%LOCALAPPDATA%\vunm-youtube-mcp` on
Windows; `auth` prints the exact path. The directory is created readable by you
only, and the token file is written with mode 0600.

Tools never open a browser. When the token is missing, has the wrong scopes for
the mode, or Google refuses to refresh it, a tool answers with an error that
names the `auth` command to run.

For **public** mode, create an API key in the same project instead and set
`YOUTUBE_API_KEY`.

## Use it from an MCP client

The server speaks MCP over stdio. Pass the variables above through the
client's `env` setting.

**Claude Code** (user scope):

```bash
claude mcp add --scope user vunm-youtube-mcp -- uvx --from "vunm-youtube-mcp[ytdlp] @ git+https://github.com/vunm-io/vunm-youtube-mcp@v0.2.0" vunm-youtube-mcp
```

Add `-e YOUTUBE_MCP_MODE=read-only` before `--` for read-only mode.

**Kiro** (`~/.kiro/settings/mcp.json`), **Antigravity CLI (`agy`)**
(`~/.gemini/config/mcp_config.json`) and **Claude Desktop**
(`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS)
use the same shape:

```json
{
  "mcpServers": {
    "vunm-youtube-mcp": {
      "command": "uvx",
      "args": [
        "--from",
        "vunm-youtube-mcp[ytdlp] @ git+https://github.com/vunm-io/vunm-youtube-mcp@v0.2.0",
        "vunm-youtube-mcp"
      ],
      "env": { "YOUTUBE_MCP_MODE": "full" }
    }
  }
}
```

A desktop app may not see your shell's `PATH`; if it cannot start `uvx`, use
the absolute path that `which uvx` prints.

## Safe writes

`youtube_update_video` previews by default (`dry_run` is true). The preview
reads the video and returns each field's value before and after, warnings (the
video becoming public, tags being dropped, a scheduled publish time being
cleared) and the 50 quota units the write would cost. Nothing is written until
the tool is called again with `dry_run=false`, and the server's instructions
tell the model to ask you first. A write sends only the parts that change, with
their other writable properties as they were, because `videos.update` resets
any property it is not sent. Titles (100 characters), descriptions
(5000 bytes) and tags (500 characters, counted the way YouTube counts them) are
checked before any request. MCP clients see the tool annotated as destructive.

## Transcripts

`youtube_get_transcript` reads caption tracks with
[youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api)
and uses no YouTube Data API quota. It prefers a manually created transcript
in your language order, then an auto-generated one, and says which it used
(`language_code`, `is_generated`, `source`). Long transcripts are cut at a line
boundary after `max_chars` characters (default 50,000), with `truncated` set.

YouTube often blocks these requests from cloud and VPN IP addresses. With the
`ytdlp` extra installed, the tool then falls back to
[yt-dlp](https://github.com/yt-dlp/yt-dlp). yt-dlp
[needs a JavaScript runtime](https://github.com/yt-dlp/yt-dlp/wiki/EJS),
Deno by default, for full YouTube support; without one it logs a warning and
some videos may fail.

## Security

- Credentials stay on your machine, in the credentials directory, never in the
  repository.
- The `youtube` scope of full mode lets whoever holds the token manage your
  YouTube account, not only edit metadata. If you only need to read, use
  read-only mode: the server then has no write tool, and its token cannot write
  either.
- Report vulnerabilities as described in [SECURITY.md](SECURITY.md).

## Migrating from 0.1

- The command is `vunm-youtube-mcp` (or `python -m vunm_youtube_mcp`);
  `python -m src.server` no longer exists, so update your client configuration.
- `python authenticate.py` is now `vunm-youtube-mcp auth`.
- Credentials moved from `<checkout>/credentials/` to the per-user directory.
  `vunm-youtube-mcp auth` notices old files and prints the command to move them;
  it does not move them itself.
- Failures are MCP tool errors instead of `{"error": ...}` results, and some
  results changed shape. See the [changelog](CHANGELOG.md).

## Development

```bash
uv sync                    # Python, dependencies and the dev tools
uv run pytest              # tests; no test reaches Google
uv run ruff check          # lint
uv run ruff format         # format
uv build                   # wheel and sdist in dist/
uv run python scripts/live_smoke.py --help   # live checks against your channel; not run in CI
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE).
