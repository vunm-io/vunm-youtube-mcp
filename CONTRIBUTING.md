# Contributing to vunm-youtube-mcp

Thank you for considering contributing to `vunm-youtube-mcp`! This project is open-source under the MIT license and aims to provide an ergonomic, secure, quota-efficient YouTube Model Context Protocol server.

## Code of Conduct

Please be respectful, constructive, and collaborative in all communications.

## Development Setup

1. Install [uv](https://docs.astral.sh/uv/) and clone the repository:
   ```bash
   git clone https://github.com/vunm-io/vunm-youtube-mcp.git
   cd vunm-youtube-mcp
   ```
2. Install Python, the dependencies and the dev tools:
   ```bash
   uv sync
   ```
3. Run the checks CI runs:
   ```bash
   uv run ruff check
   uv run ruff format --check
   uv run pytest
   uv build
   ```

Tests use the fakes in `tests/fakes.py` and never reach Google; please keep it that way, and use synthetic IDs and names in fixtures.

## Pull Request Guidelines

1. **Commit Messages**: Use [Conventional Commits](https://www.conventionalcommits.org/) in English and imperative mood:
   - `feat: add video playlist management tools`
   - `fix: handle missing transcript error gracefully`
   - `docs: update setup guide for Claude Desktop`
   - `chore: update dependencies`
2. **One Logical Change per PR**: Keep PRs scoped, focused, and rebased onto `main`. Avoid merge commits.
3. **No Secrets**: Never commit credentials, tokens, or personal identifiers. Ensure `.gitignore` remains intact.
4. **Dependencies**: Pin new dependencies exactly in `pyproject.toml` and commit the updated `uv.lock`.
5. **Security**: For private vulnerability reports, please refer to [SECURITY.md](SECURITY.md).
