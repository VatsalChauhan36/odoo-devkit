import fnmatch
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import toons

from .constants import DEFAULT_ROOTS


# Short-key map: verbose response key -> compact key sent to the LLM.
# Keeps field names readable in code but token-efficient on the wire.
_KEY_MAP: dict[str, str] = {
    # Core
    "matches": "m",
    "count": "n",
    "total_matches": "tm",
    # File / location
    "path": "p",
    "line": "l",
    "module": "mo",
    "file": "fi",
    "files": "fs",
    "rel_path": "rp",
    "start": "st",
    "end": "ed",
    "lines": "ln",
    # Content
    "text": "t",
    "scope": "sc",
    "pattern": "pt",
    "module_filter": "mf",
    "match": "mt",
    "note": "nt",
    "hint": "ht",
    "context": "ctx",
    # Fields / structure
    "fields": "f",
    "field_count": "fc",
    "modules": "ms",
    "kind": "kd",
    "summary": "sm",
    "definitions": "df",
    "methods": "mth",
    "views": "vw",
    "menus": "mnu",
    "candidate_views": "cv",
    "custom_views": "cuv",
    "targets": "tg",
    "target_actions": "ta",
    "target": "tgt",
    "target_type": "tt",
    # Files
    "source_files": "sf",
    "related_files": "rf",
    "total_files": "tf",
    # Errors / warnings
    "errors": "e",
    "warnings": "w",
    "error_count": "ec",
    "warning_count": "wc",
    # Rules / access
    "rules": "rl",
    "access": "ax",
    "rule_count": "rc",
    "access_count": "ac",
    "group_id:id": "gid",
    "model_id:id": "mid",
    "res_model": "rm",
    "view_id": "vid",
    "view_mode": "vm",
    "action": "act",
    "parent": "pr",
    "name": "nm",
    # Execution
    "patch": "px",
    "returncode": "rcd",
    "stdout_tail": "out",
    "stderr_tail": "err",
    "truncated": "tr",
    # Directory / tree
    "directories": "ds",
    "chain": "ch",
    "depth": "dp",
    "ancestors": "an",
    "children": "kd",
    # XML / view
    "xml_id": "xid",
    "inherit_id": "inh",
    "view_ref": "vr",
    # Naming
    "field_name": "fn",
    "method_name": "mn",
    # Status
    "success": "ok",
    "valid": "v",
    # Target paths
    "target_xml_path": "txp",
    "target_python_path": "tpp",
    "target_csv_path": "tcp",
    # Rare (keep semi-readable)
    "manifest_path": "manifest",
    "init_path": "init",
}


def _compress_keys(data: Any) -> Any:
    if isinstance(data, dict):
        return {_KEY_MAP.get(key, key): _compress_keys(value) for key, value in data.items()}
    if isinstance(data, list):
        return [_compress_keys(item) for item in data]
    return data


def to_toon(data: Any) -> str:
    return toons.dumps(_compress_keys(data))


def load_roots(cli_roots: list[str] | None) -> list[Path]:
    # Priority: CLI args > ODOO_MCP_ROOTS env var > saved config file > built-in defaults.
    # Note: server CLI currently passes None because --roots is deprecated/no-op.
    env_roots = os.getenv("ODOO_MCP_ROOTS")
    if cli_roots:
        raw = cli_roots
    elif env_roots:
        raw = env_roots.split(os.pathsep)
    else:
        # Fall back to saved config — imported here to avoid circular imports at module load
        from .config import OdooDevkitConfig
        saved = OdooDevkitConfig.load()
        raw = saved.roots if saved.roots else list(DEFAULT_ROOTS)

    roots: list[Path] = []
    for item in raw:
        path = Path(item).expanduser().resolve()
        if path.exists() and path.is_dir():
            roots.append(path)

    unique: list[Path] = []
    seen = set()
    for root in roots:
        value = str(root)
        if value not in seen:
            seen.add(value)
            unique.append(root)

    if not unique:
        raise ValueError(
            "No valid roots found. Set ODOO_MCP_ROOTS env var or configure roots in ~/.odoo-devkit/config.json."
        )
    return unique


def assert_allowed_path(path: Path, roots: list[Path]) -> Path:
    resolved = path.expanduser().resolve()
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return resolved
        except ValueError:
            continue
    raise ValueError(f"Path not allowed: {resolved}")


def resolve_allowed_path(path: Path, roots: list[Path]) -> Path:
    if path.is_absolute():
        return assert_allowed_path(path, roots)

    candidates: list[Path] = []
    for base in (Path.cwd(), *roots):
        candidate = (base / path).expanduser()
        if not candidate.exists():
            continue
        try:
            safe = assert_allowed_path(candidate, roots)
        except ValueError:
            continue
        if safe not in candidates:
            candidates.append(safe)

    if not candidates:
        raise ValueError(f"Path not found inside configured roots: {path}")
    if len(candidates) > 1:
        joined = ", ".join(str(item) for item in candidates[:5])
        raise ValueError(
            f"Path is ambiguous inside configured roots: {path}. Matches: {joined}"
        )
    return candidates[0]


def run_rg(
    pattern: str,
    roots: list[Path],
    globs: list[str],
    limit: int,
    fixed_strings: bool = False,
    context_lines: int = 0,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    if shutil.which("rg"):
        if context_lines > 0:
            cmd = ["rg", "--json", f"-C{context_lines}"]
        else:
            cmd = ["rg", "-n", "--no-heading", "--color", "never"]
        if fixed_strings:
            cmd.append("-F")
        all_files = all(path.is_file() for path in roots)
        if not all_files:
            for glob in globs:
                cmd.extend(["-g", glob])
        cmd.append(pattern)
        cmd.extend(str(path) for path in roots)

        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode not in (0, 1):
            raise ValueError(proc.stderr.strip() or "ripgrep failed")

        if context_lines > 0:
            rows = _parse_rg_json_context(proc.stdout, limit)
        else:
            for line in proc.stdout.splitlines():
                parts = line.split(":", 2)
                if len(parts) < 3:
                    continue
                rows.append(
                    {"path": parts[0], "line": int(parts[1]), "text": parts[2].strip()}
                )
                if len(rows) >= limit:
                    break
        return rows

    regex = None if fixed_strings else re.compile(pattern)
    for root in roots:
        if root.is_file():
            candidates = [root]
        else:
            candidates = (path for path in root.rglob("*") if path.is_file())
        for file_path in candidates:
            if root.is_dir():
                rel = str(file_path.relative_to(root)).replace("\\", "/")
                if globs and not any(fnmatch.fnmatch(rel, glob) for glob in globs):
                    continue
            try:
                with file_path.open("r", encoding="utf-8", errors="replace") as handle:
                    lines_buf = handle.readlines()

                for idx, raw_line in enumerate(lines_buf, start=1):
                    text = raw_line.rstrip("\n")
                    matched = (
                        pattern in text
                        if fixed_strings
                        else bool(regex.search(text))
                    )
                    if not matched:
                        continue
                    if context_lines > 0:
                        ctx_start = max(0, idx - 1 - context_lines)
                        ctx_end = min(len(lines_buf), idx + context_lines)
                        context = [
                            {
                                "line": ctx_start + offset + 1,
                                "text": lines_buf[ctx_start + offset].rstrip("\n"),
                                "match": (ctx_start + offset + 1) == idx,
                            }
                            for offset in range(ctx_end - ctx_start)
                        ]
                        rows.append(
                            {"path": str(file_path), "line": idx, "context": context}
                        )
                    else:
                        rows.append(
                            {"path": str(file_path), "line": idx, "text": text.strip()}
                        )
                    if len(rows) >= limit:
                        return rows
            except OSError:
                continue
    return rows


def _parse_rg_json_context(stdout: str, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    current_path = ""
    buffer: list[dict[str, Any]] = []
    last_match_line = -1

    def _flush() -> None:
        nonlocal buffer, last_match_line
        if buffer and last_match_line >= 0:
            rows.append(
                {
                    "path": current_path,
                    "line": last_match_line,
                    "context": buffer[:],
                }
            )
        buffer = []
        last_match_line = -1

    for raw in stdout.splitlines():
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        kind = obj.get("type")
        if kind == "begin":
            current_path = obj["data"]["path"]["text"]
        elif kind in ("match", "context"):
            line_no = obj["data"]["line_number"]
            text = obj["data"]["lines"]["text"].rstrip("\n")
            is_match = kind == "match"
            if is_match and last_match_line >= 0:
                _flush()
                if len(rows) >= limit:
                    return rows
            buffer.append({"line": line_no, "text": text, "match": is_match})
            if is_match:
                last_match_line = line_no
        elif kind == "end":
            _flush()
            if len(rows) >= limit:
                return rows

    _flush()
    return rows[:limit]
