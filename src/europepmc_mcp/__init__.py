"""Europe PMC Evidence MCP — grounded literature evidence for agents."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("europepmc-mcp")
except PackageNotFoundError:  # pragma: no cover - editable / uninstalled
    __version__ = "0.1.0"

__all__ = ["__version__"]
