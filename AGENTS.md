# AGENTS.md — vunm-youtube-mcp

Source of truth for AI agents working in this repository. This is an independent public open-source project (`vunm-io/vunm-youtube-mcp`).

## What this repo is

A high-performance, quota-efficient Model Context Protocol (MCP) server written in Python using FastMCP. It connects AI assistants (Antigravity, Claude Desktop, Cursor, etc.) directly to YouTube Data API v3 and YouTube Analytics API v2 using Google OAuth 2.0 Desktop authentication.

## Invariants

1. **Zero Secret Leakage**: The `credentials/` folder, `client_secret*.json`, `token*.json`, and `.env` files must NEVER be tracked or committed to Git.
2. **Quota Efficiency**: Always prefer minimal-cost API calls (e.g. `playlistItems` costing 1 unit instead of `search().list` costing 100 units).
3. **Public Git Hygiene**: Conventional Commits in English, imperative mood. No merge commits, clean linear history.

## Development & Testing

```bash
# Set up environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Verify tool registration
python -c "import sys; sys.path.insert(0, '.'); from src.server import mcp; import asyncio; print('Tools:', len(asyncio.run(mcp.list_tools())))"
```
