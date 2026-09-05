# vunm-youtube-mcp

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Model Context Protocol](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io/)

A custom, quota-efficient Model Context Protocol (MCP) server that empowers AI assistants (Antigravity, Claude Desktop, Cursor, Cline) to interact directly with your YouTube channel.

Built with **Python** and **FastMCP**, it supports **channel analytics**, **video metadata updates (SEO)**, **high-speed subtitle/transcript extraction**, and **comment management** via official Google APIs with OAuth 2.0.

> [!NOTE]
> [Bản tiếng Việt có tại đây (Vietnamese translation available)](README.vi.md).

---

## Key Capabilities

- **Channel Analytics**: Query private metrics directly via YouTube Analytics API v2 (watch time, viewer retention, subscriber gain/loss, demographics).
- **Video Management**: Update titles, descriptions, keyword tags, category, and privacy status (`public`, `unlisted`, `private`) on YouTube Studio.
- **Quota Efficiency**: Uses channel upload playlist indexing (1 API unit) instead of expensive global searches (100 API units).
- **Zero-Quota Transcripts**: Extracts timestamped captions across multiple languages without consuming YouTube Data API quota.
- **Audience Feedback**: Fetches and evaluates recent video comments for sentiment analysis and drafting responses.

---

## Tools Catalog

| Tool | Category | Description |
| :--- | :--- | :--- |
| `youtube_channel_stats` | Channel Overview | Retrieve subscriber count, view count, total videos, and channel metadata. |
| `youtube_analytics_report` | Analytics | Query detailed performance metrics by date range (watch time, retention, views, subs). |
| `youtube_video_analytics` | Video Analytics | Fetch deep performance metrics for a specific video ID. |
| `youtube_list_videos` | Video Management | List uploaded videos (including unlisted/private) with 1-unit quota usage. |
| `youtube_get_video` | Video Management | Read full video snippet (title, description, tags, category, privacy, stats). |
| `youtube_update_video` | Video Studio | Update title, description, tags, category, and/or privacy status. |
| `youtube_get_transcript` | Content / SEO | Extract formatted subtitles with timestamps `[MM:SS]` for summarization. |
| `youtube_get_comments` | Community | Retrieve recent comments on a video for evaluation or reply drafting. |

---

## Quick Start

### 1. Prerequisites
- Python 3.10 or higher.
- A Google Cloud Project with:
  - **YouTube Data API v3** enabled.
  - **YouTube Analytics API** enabled.

### 2. Google OAuth 2.0 Credentials Setup
1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select a project.
3. Enable **YouTube Data API v3** and **YouTube Analytics API** under **APIs & Services $\rightarrow$ Library**.
4. Configure **OAuth consent screen** (User type: *External*, add your channel email under *Test users*).
5. Go to **Credentials $\rightarrow$ Create Credentials $\rightarrow$ OAuth client ID** (Application type: **Desktop app**).
6. Download the client secret JSON, rename it to `client_secret.json`, and place it in:
   ```bash
   vunm-youtube-mcp/credentials/client_secret.json
   ```
   *(Note: The `credentials/` folder is strictly ignored by `.gitignore` and will never be committed).*

### 3. Installation & First-Time Authentication
```bash
# Clone the repository
git clone https://github.com/vunm-io/vunm-youtube-mcp.git
cd vunm-youtube-mcp

# Create virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run initial authorization (opens browser to grant permissions)
python authenticate.py
```
Upon successful login, `credentials/token.json` is generated and automatically refreshed on subsequent runs.

---

## Integration with AI Clients

### Antigravity (Gemini CLI / Antigravity IDE)
Add the server to `~/.gemini/config/mcp_config.json`:
```json
{
  "mcpServers": {
    "vunm-youtube-mcp": {
      "command": "/absolute/path/to/vunm-youtube-mcp/.venv/bin/python",
      "args": ["-m", "src.server"],
      "cwd": "/absolute/path/to/vunm-youtube-mcp"
    }
  }
}
```

### Claude Desktop
Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "vunm-youtube-mcp": {
      "command": "/absolute/path/to/vunm-youtube-mcp/.venv/bin/python",
      "args": ["-m", "src.server"],
      "cwd": "/absolute/path/to/vunm-youtube-mcp"
    }
  }
}
```

---

## Security & Privacy

- All credentials (`client_secret.json`, `token.json`) remain 100% local on your machine.
- Scopes requested are strictly limited to YouTube management and read-only analytics.
- For security questions or vulnerability reports, please see [SECURITY.md](SECURITY.md).

---

## Contributing & License

Contributions are welcome! Please review [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a pull request.

Released under the [MIT License](LICENSE).
