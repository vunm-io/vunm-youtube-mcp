"""Over the stdio transport, `serve` writes nothing but MCP messages to stdout.

Both tests start the real server as a subprocess with an empty credentials
directory and DEBUG logging, so any log record or print that reached stdout
would break them.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from mcp import types

from vunm_youtube_mcp.server import mcp

SERVE = [sys.executable, "-m", "vunm_youtube_mcp", "serve"]
TIMEOUT = 60


def _server_env(credentials_dir) -> dict[str, str]:
    return {
        "YOUTUBE_CREDENTIALS_DIR": str(credentials_dir),
        "YOUTUBE_MCP_LOG_LEVEL": "DEBUG",
        # Unbuffered, so a stray write shows up mid-session instead of at exit,
        # where the stdio client discards output without parsing it.
        "PYTHONUNBUFFERED": "1",
    }


async def _expected_tool_names() -> set[str]:
    async with Client(mcp) as client:
        return {tool.name for tool in await client.list_tools()}


async def test_stdio_client_lists_tools_without_parse_errors(tmp_path, caplog):
    transport_errors: list[Exception] = []

    async def on_message(message) -> None:
        if isinstance(message, Exception):
            transport_errors.append(message)

    stderr_log = tmp_path / "stderr.log"
    transport = StdioTransport(
        command=SERVE[0],
        args=SERVE[1:],
        env=_server_env(tmp_path / "credentials"),
        log_file=stderr_log,
    )
    with caplog.at_level(logging.ERROR, logger="mcp.client.stdio"):
        async with Client(transport, message_handler=on_message, timeout=TIMEOUT) as client:
            tools = await client.list_tools()
            result = await client.call_tool("youtube_channel_stats", {}, raise_on_error=False)

    assert {tool.name for tool in tools} == await _expected_tool_names()
    assert result.is_error
    assert transport_errors == []
    assert "Failed to parse JSONRPC message" not in caplog.text
    assert stderr_log.read_text(encoding="utf-8").strip(), "logs should reach stderr"


async def test_every_stdout_line_is_a_jsonrpc_message(tmp_path):
    env = {key: value for key, value in os.environ.items() if not key.startswith("YOUTUBE_")}
    env.update(_server_env(tmp_path / "credentials"))
    with open(tmp_path / "stderr.log", "wb") as stderr:  # noqa: ASYNC230 - small local file
        process = await asyncio.create_subprocess_exec(
            *SERVE,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=stderr,
            env=env,
        )
        lines: list[bytes] = []

        async def send(message: dict) -> None:
            process.stdin.write(json.dumps(message).encode() + b"\n")
            await process.stdin.drain()

        async def response(request_id: int) -> dict:
            while True:
                line = await asyncio.wait_for(process.stdout.readline(), TIMEOUT)
                assert line, f"stdout closed before the response to request {request_id}"
                lines.append(line)
                message = json.loads(line)
                if message.get("id") == request_id:
                    return message

        try:
            await send(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": types.LATEST_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "stdout-test", "version": "0"},
                    },
                }
            )
            await response(1)
            await send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            await send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            listed = await response(2)
            await send(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "youtube_channel_stats", "arguments": {}},
                }
            )
            called = await response(3)
            process.stdin.close()
            lines.extend((await asyncio.wait_for(process.stdout.read(), TIMEOUT)).splitlines())
            await asyncio.wait_for(process.wait(), TIMEOUT)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    for line in filter(None, (raw.strip() for raw in lines)):
        types.jsonrpc_message_adapter.validate_json(line, by_name=False)
    listed_names = {tool["name"] for tool in listed["result"]["tools"]}
    assert listed_names == await _expected_tool_names()
    assert called["result"]["isError"] is True
    assert process.returncode == 0
