"""
Flask-based configuration dashboard for odoo-devkit.

The dashboard starts automatically in a background thread when the MCP server
starts (same pattern as Serena). It opens the browser on launch and keeps
running alongside the MCP server.
"""

from __future__ import annotations

import logging as _logging
import os
import platform
import socket
import subprocess
import sys
import threading
from pathlib import Path

from .config import CONFIG_FILE, OdooDevkitConfig

DASHBOARD_DIR = Path(__file__).parent / "resources" / "dashboard"

_log = _logging.getLogger(__name__)
_last_dashboard_url: str | None = None


def _find_free_port(host: str = "127.0.0.1", start: int = 24380) -> int:
    port = start
    while port <= 65535:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((host, port))
                return port
        except OSError:
            port += 1
    raise RuntimeError("No free port found")


def _system_has_usable_display() -> bool:
    system = platform.system()
    if system in {"Darwin", "Windows"}:
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _open_dashboard_in_browser(url: str) -> bool:
    if not _system_has_usable_display():
        _log.warning("Not opening dashboard automatically because no usable display was detected.")
        return False
    try:
        # Launch detached so browser-open side effects never write to MCP stdio streams.
        subprocess.Popen(
            [sys.executable, "-c", f"import webbrowser; webbrowser.open({url!r})"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except Exception as exc:
        _log.warning("Could not open dashboard automatically: %s", exc)
        return False


def _build_app():
    """Build and return the Flask app (import flask lazily)."""
    from flask import Flask, Response, jsonify, request, send_from_directory

    app = Flask(__name__)
    _logging.getLogger("werkzeug").setLevel(_logging.ERROR)

    def _resolve_project_root(raw: str | None) -> Path | None:
        if raw and raw.strip():
            candidate = Path(raw).expanduser().resolve()
            if candidate.is_dir():
                return candidate
        return OdooDevkitConfig.find_project_root()

    # ── static files ──────────────────────────────────────────────────
    @app.route("/dashboard/")
    def index() -> Response:
        return send_from_directory(str(DASHBOARD_DIR), "index.html")

    @app.route("/dashboard/<path:filename>")
    def static_files(filename: str) -> Response:
        return send_from_directory(str(DASHBOARD_DIR), filename)

    # ── API ───────────────────────────────────────────────────────────
    @app.route("/api/config", methods=["GET"])
    def get_config():
        project_root = _resolve_project_root(request.args.get("project_root"))
        cfg = OdooDevkitConfig.load(project_root=project_root)
        project_cfg_path = (
            OdooDevkitConfig.project_config_file_path(project_root=project_root)
            if project_root
            else None
        )
        active_scope = "project" if (project_cfg_path and project_cfg_path.exists()) else "global"
        return jsonify({
            "roots":        cfg.roots,
            "odoo_bin":     cfg.odoo_bin,
            "odoo_config":  cfg.odoo_config,
            "database":     cfg.database,
            "docs_path":    cfg.docs_path,
            "python_path":  cfg.python_path,
            "url":          cfg.url,
            "username":     cfg.username,
            "password":     cfg.password,
            "open_browser": cfg.open_browser,
            "enable_dashboard": cfg.enable_dashboard,
            "dashboard_host": cfg.dashboard_host,
            "global_config_file": str(CONFIG_FILE),
            "project_root": str(project_root) if project_root else None,
            "project_config_file": str(project_cfg_path) if project_cfg_path else None,
            "project_config_exists": bool(project_cfg_path and project_cfg_path.exists()),
            "default_save_scope": "project" if project_root else "global",
            "active_scope": active_scope,
            "active_config_file": str(project_cfg_path if active_scope == "project" else CONFIG_FILE),
        })

    @app.route("/api/config", methods=["POST"])
    def save_config():
        data = request.get_json() or {}
        project_root = _resolve_project_root(str(data.get("project_root") or ""))
        existing = OdooDevkitConfig.load(project_root=project_root)
        scope_raw = str(data.get("scope") or "").strip().lower()
        scope = scope_raw if scope_raw in {"global", "project"} else ("project" if project_root else "global")
        cfg = OdooDevkitConfig(
            roots=data.get("roots", existing.roots) or [],
            odoo_bin=data.get("odoo_bin", existing.odoo_bin) or "",
            odoo_config=data.get("odoo_config", existing.odoo_config) or "",
            database=data.get("database", existing.database) or "",
            docs_path=data.get("docs_path", existing.docs_path) or "",
            python_path=data.get("python_path", existing.python_path) or "",
            url=data.get("url", existing.url) or "http://localhost:8069",
            username=data.get("username", existing.username) or "admin",
            password=data.get("password", existing.password) or "",
            open_browser=bool(data.get("open_browser", existing.open_browser)),
            enable_dashboard=bool(data.get("enable_dashboard", existing.enable_dashboard)),
            dashboard_host=(data.get("dashboard_host", existing.dashboard_host) or "127.0.0.1"),
        )
        try:
            config_file = cfg.save(scope=scope, project_root=project_root)
            return jsonify({
                "status": "ok",
                "scope": scope,
                "config_file": str(config_file),
                "project_root": str(project_root) if project_root else None,
                "global_config_file": str(CONFIG_FILE),
            })
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc)}), 500

    @app.route("/api/validate_path", methods=["POST"])
    def validate_path():
        data = request.get_json() or {}
        p = Path(data.get("path", "")).expanduser()
        return jsonify({"exists": p.exists(), "is_dir": p.is_dir(), "is_file": p.is_file()})

    @app.route("/api/browse", methods=["POST"])
    def browse():
        """Open a native file/directory picker and return chosen path.

        Platform strategy:
          macOS   — osascript (AppleScript) native Finder dialog
          Windows — PowerShell System.Windows.Forms dialog
          Linux   — zenity (GTK) → kdialog (KDE) → tkinter fallback
        """
        import platform
        import shutil
        import subprocess

        data = request.get_json() or {}
        mode = data.get("mode", "file")   # "file" or "dir"
        title = data.get("title", "Select path")
        initial_dir = data.get("initial_dir", str(Path.home()))
        system = platform.system()

        # ── macOS — osascript ─────────────────────────────────────────
        if system == "Darwin":
            try:
                if mode == "dir":
                    script = (
                        f'tell application "Finder"\n'
                        f'  set d to choose folder with prompt "{title}" '
                        f'default location POSIX file "{initial_dir}"\n'
                        f'  POSIX path of d\n'
                        f'end tell'
                    )
                else:
                    script = (
                        f'tell application "Finder"\n'
                        f'  set f to choose file with prompt "{title}" '
                        f'default location POSIX file "{initial_dir}"\n'
                        f'  POSIX path of f\n'
                        f'end tell'
                    )
                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True, text=True, timeout=120
                )
                path = result.stdout.strip()
                return jsonify({"path": path})
            except Exception as exc:
                return jsonify({"path": "", "error": str(exc)}), 500

        # ── Windows — PowerShell ──────────────────────────────────────
        if system == "Windows":
            try:
                if mode == "dir":
                    ps_script = (
                        "Add-Type -AssemblyName System.Windows.Forms; "
                        "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
                        f"$d.Description = '{title}'; "
                        f"$d.SelectedPath = '{initial_dir}'; "
                        "$d.ShowNewFolderButton = $true; "
                        "if ($d.ShowDialog() -eq 'OK') { $d.SelectedPath }"
                    )
                else:
                    ps_script = (
                        "Add-Type -AssemblyName System.Windows.Forms; "
                        "$f = New-Object System.Windows.Forms.OpenFileDialog; "
                        f"$f.Title = '{title}'; "
                        f"$f.InitialDirectory = '{initial_dir}'; "
                        "$f.Filter = 'All files (*.*)|*.*'; "
                        "if ($f.ShowDialog() -eq 'OK') { $f.FileName }"
                    )
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps_script],
                    capture_output=True, text=True, timeout=120
                )
                path = result.stdout.strip()
                return jsonify({"path": path})
            except Exception as exc:
                return jsonify({"path": "", "error": str(exc)}), 500

        # ── Linux — zenity → kdialog → tkinter ───────────────────────
        if shutil.which("zenity"):
            try:
                cmd = ["zenity", "--file-selection", f"--title={title}",
                       f"--filename={initial_dir}/"]
                if mode == "dir":
                    cmd.append("--directory")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                path = result.stdout.strip()
                return jsonify({"path": path})
            except Exception:
                pass

        if shutil.which("kdialog"):
            try:
                if mode == "dir":
                    cmd = ["kdialog", "--getexistingdirectory", initial_dir, "--title", title]
                else:
                    cmd = ["kdialog", "--getopenfilename", initial_dir, "--title", title]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                path = result.stdout.strip()
                return jsonify({"path": path})
            except Exception:
                pass

        # tkinter last resort
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            if mode == "dir":
                path = filedialog.askdirectory(title=title, initialdir=initial_dir, parent=root)
            else:
                path = filedialog.askopenfilename(title=title, initialdir=initial_dir,
                                                   filetypes=[("All files", "*")], parent=root)
            root.destroy()
            return jsonify({"path": path or ""})
        except Exception as exc:
            return jsonify({"path": "", "error": str(exc)}), 500

    @app.route("/api/check_rpc", methods=["POST"])
    def check_rpc():
        """Quick XML-RPC connectivity check from the dashboard UI."""
        import xmlrpc.client
        data = request.get_json() or {}
        url      = (data.get("url") or "").rstrip("/") or "http://localhost:8069"
        db       = data.get("database") or ""
        username = data.get("username") or "admin"
        password = data.get("password") or ""

        if not db:
            return jsonify({"ok": False, "error": "database is required"})

        # Basic URL sanity check
        if not url.startswith(("http://", "https://")):
            return jsonify({"ok": False, "error": "URL must start with http:// or https://"})

        try:
            common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
            version = common.version()
            uid = common.authenticate(db, username, password, {})
            return jsonify({
                "ok":             bool(uid),
                "uid":            uid if uid else None,
                "server_version": version.get("server_version") if isinstance(version, dict) else str(version),
                "error":          None if uid else "Authentication failed — check username/password/database",
            })
        except ConnectionRefusedError:
            return jsonify({"ok": False, "error": f"Odoo is not running at {url}"})
        except OSError as exc:
            msg = str(exc)
            if "Name or service not known" in msg or "nodename nor servname" in msg:
                return jsonify({"ok": False, "error": f"Cannot resolve host — is Odoo running at {url}?"})
            return jsonify({"ok": False, "error": f"Connection failed: {msg}"})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)})

    @app.route("/api/detect_odoo_config", methods=["GET"])
    def detect_odoo_config():
        """
        Detect odoo.conf using the same priority order Odoo itself uses
        (from odoo/tools/config.py):
          1. ODOO_RC env var
          2. OPENERP_SERVER env var  (legacy)
          3. ~/.odoorc
          4. ~/.openerp_serverrc     (legacy fallback)
          5. Common system/project locations
        """
        candidates: list[tuple[str, str]] = []  # (path, source_label)

        # 1. Env vars — exactly as Odoo does
        odoo_rc = os.environ.get("ODOO_RC", "").strip()
        if odoo_rc:
            candidates.append((odoo_rc, "ODOO_RC env var"))

        openerp_server = os.environ.get("OPENERP_SERVER", "").strip()
        if openerp_server:
            candidates.append((openerp_server, "OPENERP_SERVER env var"))

        # 2. User home — Odoo default
        candidates.append((str(Path.home() / ".odoorc"), "~/.odoorc"))
        candidates.append((str(Path.home() / ".openerp_serverrc"), "~/.openerp_serverrc"))

        # 3. Common system locations
        for p in (
            "/etc/odoo/odoo.conf",
            "/etc/odoo.conf",
            "/etc/odoo-server.conf",
            "/opt/odoo/odoo.conf",
        ):
            candidates.append((p, "system"))

        # 4. Locations relative to configured roots (odoo-bin sibling / project root)
        cfg = OdooDevkitConfig.load()
        for root_str in cfg.roots:
            for rel in ("odoo.conf", "../odoo.conf", "../../odoo.conf"):
                candidates.append((str(Path(root_str) / rel), "near roots"))

        # 5. If odoo-bin is set, check its sibling directory (matches Windows logic in Odoo)
        if cfg.odoo_bin:
            bin_sibling = str(Path(cfg.odoo_bin).parent / "odoo.conf")
            candidates.append((bin_sibling, "near odoo-bin"))

        found = []
        seen: set[str] = set()
        for raw_path, source in candidates:
            try:
                p = Path(raw_path).expanduser()
                resolved = str(p.resolve())
                if resolved in seen or not p.is_file():
                    continue
                seen.add(resolved)
                found.append({"path": resolved, "source": source})
            except Exception:
                continue

        return jsonify({"configs": found})

    @app.route("/api/parse_odoo_config", methods=["POST"])
    def parse_odoo_config():
        """Parse an odoo.conf and return addons_path entries."""
        import configparser
        data = request.get_json() or {}
        path = data.get("path", "").strip()
        if not path:
            return jsonify({"error": "path required"}), 400

        p = Path(path).expanduser()
        if not p.is_file():
            return jsonify({"error": f"File not found: {path}"}), 404

        try:
            parser = configparser.ConfigParser()
            # odoo.conf uses [options] section; some lines start with ';' comments
            content = p.read_text(encoding="utf-8")
            # strip inline ; comments that configparser doesn't handle
            cleaned = "\n".join(
                line if not line.strip().startswith(";") else ""
                for line in content.splitlines()
            )
            parser.read_string(cleaned)

            addons_raw = ""
            for section in parser.sections():
                if parser.has_option(section, "addons_path"):
                    addons_raw = parser.get(section, "addons_path")
                    break

            addons = [a.strip() for a in addons_raw.split(",") if a.strip()]
            # validate which ones exist on disk
            result = [
                {"path": a, "exists": Path(a).expanduser().is_dir()}
                for a in addons
            ]
            return jsonify({"addons_path": result, "raw": addons_raw})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/detect_python", methods=["GET"])
    def detect_python():
        """Auto-detect Python executables on the system."""
        import shutil
        import subprocess

        found: list[dict] = []
        seen: set[str] = set()

        def _add(p: str) -> None:
            resolved = str(Path(p).expanduser().resolve())
            if resolved in seen or not Path(resolved).is_file():
                return
            seen.add(resolved)
            # get version string
            try:
                ver = subprocess.check_output(
                    [resolved, "--version"], stderr=subprocess.STDOUT,
                    timeout=3, text=True
                ).strip()
            except Exception:
                ver = ""
            found.append({"path": resolved, "version": ver})

        # well-known names
        for name in ("python3", "python", "python3.13", "python3.12", "python3.11", "python3.10"):
            which = shutil.which(name)
            if which:
                _add(which)

        # common fixed locations
        for p in (
            "/usr/bin/python3", "/usr/local/bin/python3",
            "/opt/homebrew/bin/python3",
        ):
            _add(p)

        # venvs in common project dirs
        search_dirs = [
            Path.home() / ".venv",
            Path.home() / "venv",
            Path("/odoo18") / ".venv",
        ]
        for d in search_dirs:
            for candidate in (d / "bin" / "python3", d / "bin" / "python"):
                if candidate.exists():
                    _add(str(candidate))

        # also scan direct parent dirs of configured roots for .venv/bin/python3
        cfg = OdooDevkitConfig.load()
        for root_str in cfg.roots:
            for candidate in (
                Path(root_str).parent / ".venv" / "bin" / "python3",
                Path(root_str) / ".venv" / "bin" / "python3",
            ):
                if candidate.exists():
                    _add(str(candidate))

        return jsonify({"pythons": found})

    return app


def run_in_thread(open_browser: bool = True, host: str = "127.0.0.1") -> tuple[threading.Thread, int]:
    """
    Start the dashboard Flask server in a daemon thread.
    Called automatically on MCP server startup.

    Returns (thread, port).
    """
    try:
        app = _build_app()
    except ImportError as exc:
        _log.warning("odoo-devkit dashboard disabled: %s", exc)
        return threading.Thread(daemon=True), 0

    global _last_dashboard_url

    port = _find_free_port(host=host)
    url_host = "localhost" if host == "0.0.0.0" else host
    url = f"http://{url_host}:{port}/dashboard/"
    _last_dashboard_url = url

    def _serve():
        app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)

    thread = threading.Thread(target=_serve, daemon=True, name="odoo-devkit-dashboard")
    thread.start()

    _log.info("odoo-devkit dashboard started at %s", url)

    if open_browser:
        def _open():
            import time
            time.sleep(0.8)  # wait for Flask to be ready
            _open_dashboard_in_browser(url)
        threading.Thread(target=_open, daemon=True).start()

    return thread, port


def run_dashboard(host: str = "127.0.0.1", open_browser: bool = True) -> None:
    """Blocking dashboard entry-point (opens browser, blocks)."""
    try:
        app = _build_app()
    except ImportError as exc:
        raise ImportError(str(exc))

    global _last_dashboard_url

    port = _find_free_port(host=host)
    url_host = "localhost" if host == "0.0.0.0" else host
    url = f"http://{url_host}:{port}/dashboard/"
    _last_dashboard_url = url
    print(f"odoo-devkit config dashboard: {url}", flush=True)

    if open_browser:
        def _open():
            import time
            time.sleep(0.8)
            _open_dashboard_in_browser(url)

        threading.Thread(target=_open, daemon=True).start()
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)


def get_dashboard_url() -> str | None:
    return _last_dashboard_url


def open_dashboard() -> tuple[bool, str | None]:
    url = get_dashboard_url()
    if not url:
        return False, None
    return _open_dashboard_in_browser(url), url
