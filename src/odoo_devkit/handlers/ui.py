from pathlib import Path
from typing import Any, Sequence

from mcp.types import TextContent

from ..dashboard import get_dashboard_url, open_dashboard
from ..utils import to_toon


def handle(
    name: str, arguments: dict[str, Any], roots: list[Path], modules: dict[str, Path]
) -> Sequence[TextContent] | None:
    del arguments, roots, modules

    if name != "open_dashboard":
        return None

    opened, url = open_dashboard()
    if not url:
        return [TextContent(type="text", text=to_toon({
            "ok": False,
            "error": "Dashboard is not running.",
        }))]

    return [TextContent(type="text", text=to_toon({
        "ok": opened,
        "url": url,
        "message": "Dashboard open requested." if opened else "Dashboard could not be opened automatically. Open the URL manually.",
    }))]
