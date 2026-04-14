from __future__ import annotations

from pathlib import Path

# Default roots are intentionally empty — users must supply paths via:
#   saved config (global/project),
#   ODOO_MCP_ROOTS environment variable (colon-separated on Linux/macOS,
#   semicolon-separated on Windows), or
#   the web dashboard started with odoo-devkit
#
# Typical setup:
#   export ODOO_MCP_ROOTS="/path/to/your/addons:/odoo/server/addons:/odoo/server/odoo/addons"
DEFAULT_ROOTS: tuple[()] = ()

# Local Odoo documentation root used by the search_odoo_docs tool.
# Priority: ODOO_MCP_DOCS_PATH env var > saved config (global/project) > None
# If not set, search_odoo_docs will return a clear error message.
import os as _os

def get_odoo_docs_path() -> "Path | None":
    env = _os.getenv("ODOO_MCP_DOCS_PATH", "").strip()
    if env:
        return Path(env)
    # Try saved config as fallback (import lazily to avoid circular imports).
    try:
        from odoo_devkit.config import OdooDevkitConfig
        saved = OdooDevkitConfig.load()
        if saved.docs_path:
            return Path(saved.docs_path)
    except Exception:
        pass
    return None

# Backward-compatible snapshot for any legacy call sites.
ODOO_DOCS_PATH: "Path | None" = get_odoo_docs_path()
