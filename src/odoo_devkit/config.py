"""
Persistent configuration for odoo-devkit.

Global config is stored at ~/.odoo-devkit/config.json.

Optional project overrides can be stored in:
  <project-root>/.odoo-devkit/project.json

Effective settings are resolved as:
  global config + project override (if present).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

CONFIG_DIR = Path.home() / ".odoo-devkit"
CONFIG_FILE = CONFIG_DIR / "config.json"
PROJECT_CONFIG_DIR_NAME = ".odoo-devkit"
PROJECT_CONFIG_FILE_NAME = "project.json"
PROJECT_ROOT_ENV_VAR = "ODOO_MCP_PROJECT_ROOT"


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _iter_ancestors(start: Path) -> list[Path]:
    return [start, *start.parents]


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
    dashboard_host: str = "127.0.0.1"

    # ---------- persistence ----------

    @classmethod
    def _from_full_dict(cls, data: dict[str, Any]) -> "OdooDevkitConfig":
        roots_value = data.get("roots", [])
        if isinstance(roots_value, str):
            roots = [roots_value] if roots_value.strip() else []
        elif isinstance(roots_value, list):
            roots = [str(item).strip() for item in roots_value if str(item).strip()]
        else:
            roots = []

        return cls(
            roots=roots,
            docs_path=str(data.get("docs_path") or ""),
            odoo_config=str(data.get("odoo_config") or ""),
            odoo_bin=str(data.get("odoo_bin") or ""),
            database=str(data.get("database") or ""),
            python_path=str(data.get("python_path") or ""),
            url=str(data.get("url") or "http://localhost:8069"),
            username=str(data.get("username") or "admin"),
            password=str(data.get("password") or ""),
            open_browser=_coerce_bool(data.get("open_browser"), True),
            enable_dashboard=_coerce_bool(data.get("enable_dashboard"), True),
            dashboard_host=str(data.get("dashboard_host") or "127.0.0.1"),
        )

    @classmethod
    def _load_json_dict(cls, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    @classmethod
    def find_project_root(
        cls,
        start: str | Path | None = None,
        include_git: bool = True,
    ) -> Path | None:
        env_root = os.getenv(PROJECT_ROOT_ENV_VAR, "").strip()
        if env_root:
            env_root_path = Path(env_root).expanduser().resolve()
            if env_root_path.is_dir():
                return env_root_path

        start_path = Path(start).expanduser().resolve() if start else Path.cwd().resolve()
        if start_path.is_file():
            start_path = start_path.parent

        for directory in _iter_ancestors(start_path):
            marker = directory / PROJECT_CONFIG_DIR_NAME / PROJECT_CONFIG_FILE_NAME
            if marker.is_file():
                return directory

        if include_git:
            for directory in _iter_ancestors(start_path):
                if (directory / ".git").exists():
                    return directory

        return None

    @classmethod
    def project_config_file_path(
        cls,
        project_root: str | Path | None = None,
        include_git: bool = True,
    ) -> Path | None:
        root = Path(project_root).expanduser().resolve() if project_root else cls.find_project_root(include_git=include_git)
        if root is None or not root.is_dir():
            return None
        return root / PROJECT_CONFIG_DIR_NAME / PROJECT_CONFIG_FILE_NAME

    @classmethod
    def load_global(cls) -> "OdooDevkitConfig":
        data = cls._load_json_dict(CONFIG_FILE)
        if not data:
            return cls()
        return cls._from_full_dict(data)

    def _apply_overrides(self, overrides: dict[str, Any]) -> "OdooDevkitConfig":
        merged = asdict(self)
        for key, value in overrides.items():
            if key not in merged:
                continue
            if value is None:
                continue
            merged[key] = value
        return self._from_full_dict(merged)

    @classmethod
    def load(cls, project_root: str | Path | None = None) -> "OdooDevkitConfig":
        base = cls.load_global()
        project_path = cls.project_config_file_path(project_root=project_root, include_git=True)
        if project_path is None or not project_path.exists():
            return base
        project_overrides = cls._load_json_dict(project_path)
        if not project_overrides:
            return base
        return base._apply_overrides(project_overrides)

    def save(
        self,
        scope: Literal["global", "project"] = "global",
        project_root: str | Path | None = None,
    ) -> Path:
        payload = json.dumps(asdict(self), indent=2)
        if scope == "global":
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(payload, encoding="utf-8")
            return CONFIG_FILE

        if scope == "project":
            project_path = self.project_config_file_path(project_root=project_root, include_git=True)
            if project_path is None:
                raise ValueError(
                    "Could not resolve project root for project-scoped config. "
                    "Set ODOO_MCP_PROJECT_ROOT or run inside a project directory."
                )
            project_path.parent.mkdir(parents=True, exist_ok=True)
            project_path.write_text(payload, encoding="utf-8")
            return project_path

        raise ValueError(f"Invalid scope: {scope}. Expected 'global' or 'project'.")

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
