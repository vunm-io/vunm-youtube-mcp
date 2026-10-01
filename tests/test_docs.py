"""The README's tool catalog matches what the server registers in each mode."""

import re
from pathlib import Path

from fastmcp import Client

from vunm_youtube_mcp.config import Mode

README = Path(__file__).resolve().parents[1] / "README.md"
ROW = re.compile(r"^\| `(youtube_\w+)` \| [^|]+ \| ([^|]+) \|")


def _catalog() -> dict[str, set[str]]:
    """Tool name -> the modes its README row lists."""
    rows = {}
    for line in README.read_text(encoding="utf-8").splitlines():
        match = ROW.match(line)
        if match:
            rows[match.group(1)] = {mode.strip() for mode in match.group(2).split(",")}
    return rows


async def _registered(make_server, mode: Mode) -> set[str]:
    async with Client(make_server(mode)) as client:
        return {tool.name for tool in await client.list_tools()}


async def test_catalog_lists_every_full_mode_tool(make_server):
    assert set(_catalog()) == await _registered(make_server, Mode.FULL)


async def test_catalog_modes_match_the_registration(make_server):
    catalog = _catalog()

    for mode in Mode:
        documented = {name for name, modes in catalog.items() if mode.value in modes}
        assert documented == await _registered(make_server, mode), mode
