# Contributing to vunm-youtube-mcp

Thank you for considering contributing to `vunm-youtube-mcp`! This project is open-source under the MIT license and aims to provide an ergonomic, secure, quota-efficient YouTube Model Context Protocol server.

## Code of Conduct

Please be respectful, constructive, and collaborative in all communications.

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/vunm-io/vunm-youtube-mcp.git
   cd vunm-youtube-mcp
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Verify server startup:
   ```bash
   python -c "import sys; sys.path.insert(0, '.'); from src.server import mcp; import asyncio; print('Tools:', len(asyncio.run(mcp.list_tools())))"
   ```

## Pull Request Guidelines

1. **Commit Messages**: Use [Conventional Commits](https://www.conventionalcommits.org/) in English and imperative mood:
   - `feat: add video playlist management tools`
   - `fix: handle missing transcript error gracefully`
   - `docs: update setup guide for Claude Desktop`
   - `chore: update dependencies`
2. **One Logical Change per PR**: Keep PRs scoped, focused, and rebased onto `main`. Avoid merge commits.
3. **No Secrets**: Never commit credentials, tokens, or personal identifiers. Ensure `.gitignore` remains intact.
4. **Security**: For private vulnerability reports, please refer to [SECURITY.md](SECURITY.md).
