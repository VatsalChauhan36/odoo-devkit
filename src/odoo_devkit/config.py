"""
Persistent configuration for odoo-devkit.

Config is stored at ~/.odoo-devkit/config.json.
All fields are optional — the server falls back to CLI args and env vars
when they are absent, preserving full backward compatibility.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".odoo-devkit"
CONFIG_FILE = CONFIG_DIR / "config.json"


@dataclass
class OdooDevkitConfig:
    # Addons roots (same as --roots / ODOO_MCP_ROOTS)
    roots: list[str] = field(default_factory=list)
    # Path to local Odoo docs (same as ODOO_MCP_DOCS_PATH)
    docs_path: str = ""
    # Path to odoo.conf (used by run_module_upgrade as default config_file)
    odoo_config: str = ""
    # Path to odoo-bin executable (used by run_module_upgrade as default)
    odoo_bin: str = ""
    # Default database name
    database: str = ""
    # Python executable path (used to run odoo-bin)
    python_path: str = ""
    # Odoo XML-RPC connection (used by execute_rpc / check_rpc_connection)
    url: str = "http://localhost:8069"
    username: str = "admin"
    password: str = ""
    # Whether to auto-open the dashboard in the browser on MCP server startup
    open_browser: bool = True
    # Whether to start the web dashboard with the MCP server
    enable_dashboard: bool = True
    # Dashboard bind/listen address
    dashboard_host: str = "0.0.0.0"

    # ---------- persistence ----------

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(asdict(self), indent=2), encoding="utf-8"
        )

    @classmethod
    def load(cls) -> "OdooDevkitConfig":
        if not CONFIG_FILE.exists():
            return cls()
        try:
            data: dict[str, Any] = json.loads(
                CONFIG_FILE.read_text(encoding="utf-8")
            )
            return cls(
                roots=data.get("roots") or [],
                docs_path=data.get("docs_path") or "",
                odoo_config=data.get("odoo_config") or "",
                odoo_bin=data.get("odoo_bin") or "",
                database=data.get("database") or "",
                python_path=data.get("python_path") or "",
                url=data.get("url") or "http://localhost:8069",
                username=data.get("username") or "admin",
                password=data.get("password") or "",
                # default True — missing key means old config file, keep opening
                open_browser=data.get("open_browser", True),
                # default True — missing key means old config file, keep dashboard enabled
                enable_dashboard=data.get("enable_dashboard", True),
                # default localhost — missing key means old config file
                dashboard_host=data.get("dashboard_host") or "0.0.0.0",
            )
        except Exception:
            return cls()

    # ---------- helpers ----------

    def effective_roots(self, cli_roots: list[str] | None = None) -> list[str]:
        """Priority: CLI args > ODOO_MCP_ROOTS env var > saved config roots."""
        if cli_roots:
            return cli_roots
        env = os.getenv("ODOO_MCP_ROOTS", "").strip()
        if env:
            return env.split(os.pathsep)
        return self.roots

    def effective_docs_path(self) -> str:
        env = os.getenv("ODOO_MCP_DOCS_PATH", "").strip()
        return env if env else self.docs_path
