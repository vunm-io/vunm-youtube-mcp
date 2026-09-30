"""vunm-youtube-mcp: an MCP server for YouTube channel management, analytics and transcripts."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("vunm-youtube-mcp")
except PackageNotFoundError:  # a source tree that was never installed
    __version__ = "0.0.0"

__all__ = ["__version__"]
