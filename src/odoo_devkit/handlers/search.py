from pathlib import Path
from typing import Any, Sequence

from mcp.types import TextContent

from ..constants import get_odoo_docs_path
from ..utils import resolve_allowed_path, run_rg, to_toon
from .helpers import _find_module_for_file, _read_file_lines, _scope_for_module, _sort_records


def handle(
    name: str, arguments: dict[str, Any], roots: list[Path], modules: dict[str, Path]
) -> Sequence[TextContent] | None:
    if name == "search_odoo_code":
        query = arguments.get("query")
        if not query:
            raise ValueError("query is required")
        glob = str(arguments.get("glob", "*.py"))
        limit = int(str(arguments.get("limit", 30)))
        fixed_strings = bool(arguments.get("fixed_strings", True))
        module_filter = (arguments.get("module_filter") or "").strip()
        context_lines = int(str(arguments.get("context_lines", 0)))
        search_roots = roots
        if module_filter:
            if module_filter not in modules:
                raise ValueError(f"Unknown module for module_filter: {module_filter}")
            search_roots = [modules[module_filter]]
        raw_matches = run_rg(
            query,
            search_roots,
            [glob],
            limit=limit,
            fixed_strings=fixed_strings,
            context_lines=context_lines,
        )
        matches = []
        for row in raw_matches:
            file_path = Path(row["path"])
            module_path = _find_module_for_file(file_path)
            module_name = module_path.name if module_path else None
            scope = _scope_for_module(module_path, roots) if module_path else "unknown"
            matches.append({**row, "module": module_name, "scope": scope})
        matches = _sort_records(matches)[:limit]
        return [
            TextContent(
                type="text",
                text=to_toon(
                    {
                        "query": query,
                        "glob": glob,
                        "module_filter": module_filter or None,
                        "count": len(matches),
                        "truncated": len(matches) == limit,
                        "matches": matches,
                    }
                ),
            )
        ]

    if name == "read_file_lines":
        path_arg = str(arguments.get("path", "")).strip()
        if not path_arg:
            raise ValueError("path is required")
        safe = resolve_allowed_path(Path(path_arg), roots)
        start = int(str(arguments.get("start_line", arguments.get("start", 1))))
        end = int(str(arguments.get("end_line", arguments.get("end", 300))))
        max_lines = int(str(arguments.get("max_lines", 300)))
        return [
            TextContent(
                type="text",
                text=to_toon(_read_file_lines(safe, start, end, max_lines)),
            )
        ]

    if name == "search_odoo_docs":
        query = arguments.get("query")
        if not query:
            raise ValueError("query is required")
        limit = int(str(arguments.get("limit", 20)))
        docs_path = get_odoo_docs_path()
        if docs_path is None:
            return [
                TextContent(
                    type="text",
                    text=to_toon(
                        {
                            "error": "ODOO_MCP_DOCS_PATH environment variable is not set.",
                            "hint": "Clone https://github.com/odoo/documentation and set ODOO_MCP_DOCS_PATH to its path.",
                        }
                    ),
                )
            ]
        if not docs_path.exists():
            return [
                TextContent(
                    type="text",
                    text=to_toon(
                        {
                            "error": f"Docs path does not exist: {docs_path}",
                            "hint": "Check that ODOO_MCP_DOCS_PATH points to a valid directory.",
                        }
                    ),
                )
            ]
        matches = run_rg(query, [docs_path.resolve()], ["*.rst", "*.md"], limit=limit)
        return [TextContent(type="text", text=to_toon({"query": query, "matches": matches}))]

    return None
