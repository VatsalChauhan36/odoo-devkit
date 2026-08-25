#!/usr/bin/env bash
set -euo pipefail

SCRIPT_VERSION="1.0.0"
MCP_NAME="odoo-devkit"
PYTHON_VERSION="3.12"

SETUP_SUCCESSFUL="no"
SETUP_MODE=""
DOCS_PATH=""
CONFIGURED_RPC="no"

cleanup_on_exit() {
  local exit_code=$?
  if [[ "$SETUP_SUCCESSFUL" != "yes" && "$SETUP_MODE" != "5" ]]; then
    if [[ "$SETUP_MODE" == "1" || "$SETUP_MODE" == "2" || "$SETUP_MODE" == "4" ]]; then
      printf '\n\033[1;31m========================================\033[0m\n'
      printf '\033[1;31m Setup incomplete\033[0m\n'
      printf '\033[1;31m========================================\033[0m\n\n'
    fi
  fi
}
trap cleanup_on_exit EXIT

print_header() {
  printf '\n\033[1;36m========================================\033[0m\n'
  printf '\033[1;36m Odoo DevKit Setup (Linux)\033[0m\n'
  printf '\033[1;36m========================================\033[0m\n\n'
}
info() { printf '\033[1;34m[INFO]\033[0m %s\n' "$*" >&2; }
ok()   { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31m[ERR ]\033[0m %s\n' "$*" >&2; }
die()  { err "$*"; exit 1; }
need_command() { command -v "$1" >/dev/null 2>&1; }

prompt_default() {
  local prompt="$1"
  local default="$2"
  local value
  printf '\n' >&2
  read -r -p "$prompt [$default]: " value
  printf '%s' "${value:-$default}"
}

prompt_yes_no() {
  local prompt="$1"
  local default="${2:-y}"
  local answer
  printf '\n' >&2
  if [[ "$default" == "y" ]]; then
    read -r -p "$prompt [Y/n]: " answer
    answer="${answer:-y}"
  else
    read -r -p "$prompt [y/N]: " answer
    answer="${answer:-n}"
  fi
  [[ "$answer" =~ ^[Yy]$ ]]
}

find_python_cmd() {
  if need_command python3.12; then
    printf 'python3.12'
  elif need_command python3; then
    local py_ver
    py_ver="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
    if [[ "$py_ver" =~ ^3\.(1[0-9]|[2-9][0-9]) ]]; then
      printf 'python3'
    else
      return 1
    fi
  else
    return 1
  fi
}

realpath_fallback() {
  local py_cmd
  py_cmd="$(find_python_cmd || true)"
  if [[ -n "$py_cmd" ]]; then
    "$py_cmd" - "$1" <<'PY'
import os, sys
print(os.path.realpath(os.path.expanduser(sys.argv[1])))
PY
  elif need_command realpath; then
    realpath -m "$1"
  else
    printf '%s' "$1"
  fi
}

check_linux() {
  [[ "$(uname -s)" == "Linux" ]] || warn "Non-Linux OS detected ($(uname -s)). Continuing anyway..."
  if need_command lsb_release; then
    ok "Linux detected: $(lsb_release -ds 2>/dev/null || uname -s)"
  elif [[ -f /etc/os-release ]]; then
    local os_name
    os_name="$(grep -E '^PRETTY_NAME=' /etc/os-release | cut -d= -f2 | tr -d '\"' || uname -s)"
    ok "Linux detected: $os_name"
  else
    ok "Linux detected: $(uname -s)"
  fi
}

check_git() {
  need_command git || die "Git is required but was not found. Please install git (e.g. sudo apt install git / sudo dnf install git)."
  ok "Git: $(git --version)"
}

check_python() {
  local py_cmd
  py_cmd="$(find_python_cmd || true)"
  if [[ -z "$py_cmd" ]]; then
    die "Python 3.10+ is required but not found. Please install Python 3.12 or 3.10+ (e.g. sudo apt install python3 python3-venv / sudo dnf install python3)."
  fi
  local version
  version="$("$py_cmd" --version 2>&1)"
  ok "$version (using $py_cmd)"
}

check_uv() {
  if ! need_command uv; then
    info "uv not found. Attempting to install uv via standalone installer..."
    if need_command curl; then
      curl -LsSf https://astral.sh/uv/install.sh | sh
    elif need_command wget; then
      wget -qO- https://astral.sh/uv/install.sh | sh
    else
      die "uv is required. Install uv manually: https://docs.astral.sh/uv/getting-started/installation/"
    fi
    # Refresh PATH in current shell if installed to ~/.local/bin or ~/.cargo/bin
    export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"
    need_command uv || die "uv was installed but is not in PATH. Please restart your shell or add ~/.local/bin to PATH."
  fi
  ok "uv: $(uv --version)"
}

check_rg() {
  if ! need_command rg; then
    warn "ripgrep ('rg') is recommended for high-performance code searching. You can install it via: sudo apt install ripgrep / sudo dnf install ripgrep"
  else
    ok "ripgrep: $(rg --version | head -n 1)"
  fi
}

choose_mcp_dir() {
  local default_dir=""
  if [[ -f "$PWD/pyproject.toml" ]] && grep -q "odoo-devkit" "$PWD/pyproject.toml" 2>/dev/null; then
    default_dir="$PWD"
  elif [[ -n "${DETECTED_MCP:-}" && -d "$DETECTED_MCP" ]]; then
    default_dir="$DETECTED_MCP"
  fi

  while true; do
    local entered
    if [[ -n "$default_dir" ]]; then
      entered="$(prompt_default "MCP directory path" "$default_dir")"
    else
      printf '\n' >&2
      read -r -p "MCP directory path: " entered
    fi
    if [[ -z "$entered" ]]; then
      warn "MCP directory path is required."
      continue
    fi
    local resolved
    resolved="$(realpath_fallback "$entered")"
    if [[ ! -d "$resolved" ]]; then
      warn "Directory does not exist: $resolved"
      continue
    fi
    if [[ ! -f "$resolved/pyproject.toml" && ! -d "$resolved/.git" ]]; then
      warn "Path does not appear to be an odoo-devkit directory (missing pyproject.toml): $resolved"
      continue
    fi
    MCP_DIR="$resolved"
    break
  done
}

setup_mcp_repo() {
  if [[ -d "$MCP_DIR/.git" || -f "$MCP_DIR/pyproject.toml" ]]; then
    ok "Found odoo-devkit directory at $MCP_DIR"
  else
    die "odoo-devkit directory not found at: $MCP_DIR. Please make sure the path is correct and contains the downloaded files."
  fi
}

setup_mcp_env() {
  info "Creating/verifying MCP virtual environment with uv..."
  ( cd "$MCP_DIR" && uv venv --allow-existing && uv sync )
  ok "MCP dependencies installed with uv."
}

validate_mcp_cli() {
  info "Validating odoo-devkit CLI..."
  local help_output
  help_output="$(cd "$MCP_DIR" && uv run odoo-devkit --help)"
  grep -q "Odoo development MCP server" <<<"$help_output" || die "odoo-devkit CLI validation failed."
  ok "odoo-devkit CLI is working."
}

choose_custom_addons_root() {
  local default_dir="$PWD"
  if [[ -n "${DETECTED_ODOO:-}" && -d "$DETECTED_ODOO" ]]; then
    default_dir="$DETECTED_ODOO"
  fi
  while true; do
    local entered
    entered="$(prompt_default "Custom addons path" "$default_dir")"
    if [[ -z "$entered" ]]; then
      warn "Custom addons path is required."
      continue
    fi
    local resolved
    resolved="$(realpath_fallback "$entered")"
    if [[ ! -d "$resolved" ]]; then
      warn "Directory does not exist: $resolved"
      continue
    fi
    if ! is_valid_addon_root "$resolved"; then
      continue
    fi
    ODOO_ROOT="$resolved"
    break
  done
}

auto_detect_odoo_addons() {
  local candidates=(
    "${HOME}/ODOO/odoo19/odoo/addons"
    "${HOME}/ODOO/odoo18/odoo/addons"
    "${HOME}/ODOO/odoo17/odoo/addons"
    "${HOME}/ODOO/odoo16/odoo/addons"
    "${HOME}/odoo19/odoo/addons"
    "/opt/odoo/odoo19/odoo/addons"
    "/opt/odoo/odoo/addons"
    "$ODOO_ROOT/odoo/addons"
    "$ODOO_ROOT/addons"
  )
  local candidate
  for candidate in "${candidates[@]}"; do
    [[ -d "$candidate" ]] && { printf '%s' "$candidate"; return 0; }
  done
  return 1
}

is_valid_addon_root() {
  local path="$1"
  if [[ ! -d "$path" ]]; then
    warn "Path is not a directory: $path"
    return 1
  fi
  local abs_path
  local abs_mcp
  abs_path="$(realpath_fallback "$path")"
  abs_mcp="$(realpath_fallback "${MCP_DIR:-}")"

  if [[ -n "$abs_mcp" && "$abs_path" == "$abs_mcp" ]]; then
    warn "Cannot add the DevKit repository path ($abs_path) as an addon root."
    return 1
  fi
  if [[ -f "$abs_path/linux_odoo_devkit_setup.sh" || -f "$abs_path/mac_odoo_devkit_setup.sh" || -f "$abs_path/setup_odoo_devkit_linux.sh" || -f "$abs_path/setup_odoo_devkit.sh" ]]; then
    warn "Cannot add the directory containing the setup script ($abs_path) as an addon root."
    return 1
  fi
  return 0
}

choose_addon_root() {
  local label="$1"
  local default_value="$2"
  local required="$3"
  local value
  
  while true; do
    if [[ -n "$default_value" ]]; then
      info "Detected $label: $default_value"
      if prompt_yes_no "Use this path?" "y"; then
        value="$default_value"
      else
        value="$(prompt_default "$label path" "$default_value")"
      fi
    else
      if [[ "$required" == "required" ]]; then
        value="$(prompt_default "$label path" "")"
      else
        value="$(prompt_default "$label path (leave blank to skip)" "")"
      fi
    fi

    if [[ -z "$value" ]]; then
      if [[ "$required" == "required" ]]; then
        warn "This path is required."
        continue
      else
        break
      fi
    fi

    value="$(realpath_fallback "$value")"
    if ! is_valid_addon_root "$value"; then
      default_value=""
      continue
    fi

    if [[ "$value" == "$(realpath_fallback "$ODOO_ROOT")" ]]; then
      warn "This path is already configured as the custom addons root ($ODOO_ROOT)."
      default_value=""
      continue
    fi

    break
  done
  printf '%s' "$value"
}

collect_additional_roots() {
  if prompt_yes_no "Add another addons root (Enterprise/third-party/etc.)?" "n"; then
    while true; do
      local extra; printf '\n' >&2; read -r -p "Additional addons path (blank to stop): " extra
      [[ -z "$extra" ]] && break
      extra="$(realpath_fallback "$extra")"
      if ! is_valid_addon_root "$extra"; then
        continue
      fi
      if [[ "$extra" == "$(realpath_fallback "$ODOO_ROOT")" ]]; then
        warn "Path is already configured as the custom addons root."
        continue
      fi
      local duplicate="false"
      local existing
      for existing in "${ADDON_ROOTS[@]}"; do
        if [[ "$existing" == "$extra" ]]; then
          duplicate="true"
        fi
      done
      if [[ "$duplicate" == "false" ]]; then
        ADDON_ROOTS+=("$extra")
        ok "Added addon root: $extra"
      else
        warn "Path already exists; skipping."
      fi
    done
  fi
}

collect_addon_roots() {
  ADDON_ROOTS=("$ODOO_ROOT")
  ok "Custom addons root set to: $ODOO_ROOT"

  local standard_default
  standard_default="$(auto_detect_odoo_addons || true)"
  local standard_addons
  standard_addons="$(choose_addon_root "Odoo standard addons" "$standard_default" "optional")"
  
  if [[ -n "$standard_addons" && "$standard_addons" != "$ODOO_ROOT" ]]; then
    ADDON_ROOTS+=("$standard_addons")
    ok "Added standard addons root: $standard_addons"
  fi
  collect_additional_roots
}

validate_project_json_file() {
  local config_file="$1"
  if [[ ! -f "$config_file" ]]; then
    err "project.json file does not exist: $config_file"
    return 1
  fi
  local py_cmd
  py_cmd="$(find_python_cmd || echo "python3")"
  if ! "$py_cmd" -m json.tool "$config_file" >/dev/null 2>&1; then
    err "project.json is not valid JSON: $config_file"
    return 1
  fi
  return 0
}

read_existing_roots() {
  local config_file="$1"
  local py_cmd
  py_cmd="$(find_python_cmd || echo "python3")"
  "$py_cmd" - "$config_file" <<'PY'
import json, sys
from pathlib import Path
try:
    path = Path(sys.argv[1])
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        roots = data.get("roots", [])
        if isinstance(roots, list):
            for r in roots:
                print(r)
except Exception:
    pass
PY
}

detect_configured_paths() {
  local config_file="${HOME}/.gemini/config/mcp_config.json"
  local py_cmd
  py_cmd="$(find_python_cmd || true)"
  if [[ -f "$config_file" && -n "$py_cmd" ]]; then
    "$py_cmd" - "$config_file" <<'PY' 2>/dev/null
import json, sys
from pathlib import Path
try:
    path = Path(sys.argv[1])
    data = json.loads(path.read_text(encoding="utf-8"))
    server = data.get("mcpServers", {}).get("odoo-devkit", {})
    args = server.get("args", [])
    mcp_dir = ""
    project_root = ""
    for i, arg in enumerate(args):
        if arg == "--directory" and i + 1 < len(args):
            mcp_dir = args[i+1]
        elif arg == "--project-root" and i + 1 < len(args):
            project_root = args[i+1]
    if mcp_dir:
        print(f"MCP_DIR={mcp_dir}")
    if project_root:
        print(f"ODOO_ROOT={project_root}")
except Exception:
    pass
PY
  fi
}

write_project_config() {
  local config_dir="$ODOO_ROOT/.odoo-devkit"
  local config_file="$config_dir/project.json"
  mkdir -p "$config_dir"
  export CONFIG_FILE="$config_file"
  local py_cmd
  py_cmd="$(find_python_cmd || echo "python3")"
  "$py_cmd" - "${ADDON_ROOTS[@]}" <<'PY'
import json, os, sys
from pathlib import Path
path = Path(os.environ["CONFIG_FILE"])
roots = [str(Path(p).expanduser().resolve()) for p in sys.argv[1:]]
payload = {}
if path.exists():
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict): payload = loaded
    except Exception as exc:
        raise SystemExit(f"Existing project config is not valid JSON: {path}: {exc}")
payload["roots"] = roots
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
os.chmod(path, 0o600)
PY
  validate_project_json_file "$config_file" || die "Generated project.json is not valid JSON."
  ok "Project config written: $config_file"
}

configure_optional_runtime() {
  DOCS_PATH=""
  CONFIGURED_RPC="no"
  if prompt_yes_no "Configure local Odoo documentation search?" "n"; then
    local docs
    docs="$(prompt_default "Odoo documentation path" "$ODOO_ROOT/doc")"
    docs="$(realpath_fallback "$docs")"
    [[ -d "$docs" ]] || die "Documentation path does not exist: $docs"
    DOCS_PATH="$docs"
  fi
  if prompt_yes_no "Configure runtime RPC helpers (check_rpc_connection / execute_rpc / module upgrade)?" "n"; then
    CONFIGURED_RPC="yes"
    RPC_URL="$(prompt_default "Odoo URL" "http://localhost:8069")"
    RPC_DB="$(prompt_default "Odoo database name" "")"
    RPC_USER="$(prompt_default "Odoo username" "admin")"
    printf '\n'; warn "RPC password will be stored only in ~/.odoo-devkit/config.json, not project.json."; warn "Do not share that file."
    read -r -s -p "Odoo password (blank = skip saving): " RPC_PASSWORD; printf '\n'
    if [[ -z "$RPC_PASSWORD" ]]; then
      info "Odoo password was left blank. RPC credentials will not be saved."
      CONFIGURED_RPC="no"
    fi
  else
    RPC_URL=""
    RPC_DB=""
    RPC_USER=""
    RPC_PASSWORD=""
  fi
}

write_runtime_global_config() {
  [[ "$CONFIGURED_RPC" == "yes" ]] || return 0
  local global_dir="${HOME}/.odoo-devkit"
  local global_file="$global_dir/config.json"
  mkdir -p "$global_dir"; chmod 700 "$global_dir"
  export GLOBAL_FILE="$global_file"
  export RPC_URL RPC_DB RPC_USER RPC_PASSWORD
  local py_cmd
  py_cmd="$(find_python_cmd || echo "python3")"
  "$py_cmd" <<'PY'
import json, os
from pathlib import Path
path = Path(os.environ["GLOBAL_FILE"]); payload = {}
if path.exists():
    try:
        loaded = json.loads(path.read_text(encoding="utf-8")); payload = loaded if isinstance(loaded, dict) else {}
    except Exception as exc:
        raise SystemExit(f"Existing global config is not valid JSON: {path}: {exc}")
payload["url"] = os.environ["RPC_URL"]
payload["username"] = os.environ["RPC_USER"]
if os.environ["RPC_DB"].strip(): payload["database"] = os.environ["RPC_DB"].strip()
if os.environ["RPC_PASSWORD"]: payload["password"] = os.environ["RPC_PASSWORD"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8"); os.chmod(path, 0o600)
PY
  if ! "$py_cmd" -m json.tool "$global_file" >/dev/null 2>&1; then
    die "Generated global config config.json is not valid JSON."
  fi
  ok "Runtime RPC defaults saved to $global_file"
}

write_optional_project_settings() {
  if [[ -z "${DOCS_PATH:-}" ]]; then
    return 0
  fi

  local config_file="$ODOO_ROOT/.odoo-devkit/project.json"
  export CONFIG_FILE="$config_file"
  export DOCS_PATH

  local py_cmd
  py_cmd="$(find_python_cmd || echo "python3")"
  "$py_cmd" <<'PY'
import json, os
from pathlib import Path
path = Path(os.environ["CONFIG_FILE"]); payload = json.loads(path.read_text(encoding="utf-8"))
payload["docs_path"] = os.environ["DOCS_PATH"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8"); os.chmod(path, 0o600)
PY
  validate_project_json_file "$config_file" || die "Generated project.json is not valid JSON after adding docs path."
  ok "Local Odoo documentation path added to project config."
}

protect_local_project_config() {
  if [[ -d "$ODOO_ROOT/.git" ]]; then
    local exclude="$ODOO_ROOT/.git/info/exclude"; touch "$exclude"
    if ! grep -qxF ".odoo-devkit/" "$exclude"; then
      printf '\n# Local odoo-devkit machine/project configuration\n.odoo-devkit/\n' >> "$exclude"
      ok "Protected .odoo-devkit/ via git exclude."
    else ok ".odoo-devkit/ already protected via git exclude."; fi
  else warn "Odoo project is not a git worktree; skipping git exclude setup."; fi
}

configure_antigravity() {
  local config_file="${HOME}/.gemini/config/mcp_config.json"; mkdir -p "$(dirname "$config_file")"
  if [[ -e "$config_file" && ! -s "$config_file" ]]; then printf '{}\n' > "$config_file"; elif [[ ! -e "$config_file" ]]; then printf '{}\n' > "$config_file"; fi
  export MCP_CONFIG_FILE="$config_file"
  export MCP_DIR ODOO_ROOT
  local py_cmd
  py_cmd="$(find_python_cmd || echo "python3")"
  "$py_cmd" <<'PY'
import json, os
from pathlib import Path
path = Path(os.environ["MCP_CONFIG_FILE"])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception as exc:
    raise SystemExit(f"Antigravity MCP config is not valid JSON: {path}\nFix it manually before rerunning: {exc}")
if not isinstance(data, dict): raise SystemExit(f"Antigravity config must be a JSON object: {path}")
servers = data.get("mcpServers", {})
if not isinstance(servers, dict): raise SystemExit(f"'mcpServers' must be an object: {path}")
servers["odoo-devkit"] = {
    "command": "uv",
    "args": ["run", "--directory", str(Path(os.environ["MCP_DIR"]).expanduser().resolve()), "odoo-devkit", "--project-root", str(Path(os.environ["ODOO_ROOT"]).expanduser().resolve()), "--no-dashboard"]
}
data["mcpServers"] = servers
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8"); os.chmod(path, 0o600)
PY
  ok "Antigravity MCP config updated: $config_file"; warn "Refresh Antigravity's MCP servers after this script finishes."
}

validate_project_config() {
  local config_file="$ODOO_ROOT/.odoo-devkit/project.json"
  local py_cmd
  py_cmd="$(find_python_cmd || echo "python3")"
  "$py_cmd" - "$config_file" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1]); data = json.loads(path.read_text(encoding="utf-8")); roots = data.get("roots")
if not isinstance(roots, list) or not roots: raise SystemExit("Project config has no addon roots.")
missing = [p for p in roots if not Path(p).is_dir()]
if missing: raise SystemExit("Missing configured roots:\n" + "\n".join(missing))
print(f"Validated {len(roots)} addon root(s).")
PY
  ok "Project config and addon roots validated."
}

validate_antigravity_config() {
  local py_cmd
  py_cmd="$(find_python_cmd || echo "python3")"
  "$py_cmd" - "$HOME/.gemini/config/mcp_config.json" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1]); data = json.loads(path.read_text(encoding="utf-8")); server = data.get("mcpServers", {}).get("odoo-devkit")
if not isinstance(server, dict): raise SystemExit("odoo-devkit is missing from Antigravity mcp_config.json")
if server.get("command") != "uv": raise SystemExit("odoo-devkit command is not 'uv'")
args = server.get("args", []); required = {"--directory", "--project-root", "--no-dashboard"}; missing = [x for x in required if x not in args]
if missing: raise SystemExit("Missing expected MCP args: " + ", ".join(missing))
print("Antigravity MCP definition validated.")
PY
  ok "Antigravity MCP configuration validated."
}

show_full_summary() {
  printf '\n\033[1;32m========================================\033[0m\n'
  printf '\033[1;32m Setup completed successfully\033[0m\n'
  printf '\033[1;32m========================================\033[0m\n\n'
  printf 'MCP repository:\n  %s\n\n' "$MCP_DIR"
  printf 'MCP Python environment:\n  %s\n\n' "$MCP_DIR/.venv"
  printf 'Custom addons (Project root):\n  %s\n\n' "$ODOO_ROOT"
  printf 'Addon roots:\n'
  local root
  for root in "${ADDON_ROOTS[@]}"; do
    printf '  - %s\n' "$root"
  done
  printf '\nAntigravity config:\n  %s\n' "${HOME}/.gemini/config/mcp_config.json"
  printf '\nNext step:\n  Open/refresh Antigravity → MCP Servers and verify "odoo-devkit" is enabled.\n'
  printf '\nTest prompt:\n  Use the odoo-devkit MCP to list my custom Odoo modules.\n'
}

show_project_summary() {
  printf '\n\033[1;32m========================================\033[0m\n'
  printf '\033[1;32m Project configuration completed successfully\033[0m\n'
  printf '\033[1;32m========================================\033[0m\n\n'
  printf 'Custom addons (Project root):\n  %s\n\n' "$ODOO_ROOT"
  printf 'Project config:\n  %s\n\n' "$ODOO_ROOT/.odoo-devkit/project.json"
  printf 'Addon roots:\n'
  local root
  for root in "${ADDON_ROOTS[@]}"; do
    printf '  - %s\n' "$root"
  done
  local rpc_status="Not configured"
  if [[ "$CONFIGURED_RPC" == "yes" ]]; then
    rpc_status="Configured (to ${RPC_URL:-})"
  fi
  printf '\nRPC:\n  %s\n' "$rpc_status"
}

select_mode() {
  print_header
  printf '1. New / Complete Setup\n'
  printf '2. Configure Another Odoo Project\n'
  printf '3. Verify Existing Setup\n'
  printf '4. Repair / Update DevKit\n'
  printf '5. Exit\n\n'
  local choice
  read -r -p 'Select an option [1-5]: ' choice
  choice="${choice:-1}"
  case "$choice" in
    1|2|3|4|5) SETUP_MODE="$choice" ;;
    *) die "Invalid selection: $choice" ;;
  esac
}

common_prereqs() {
  check_linux; check_git; check_python; check_uv; check_rg
}

setup_or_repair_mcp() {
  choose_mcp_dir; setup_mcp_repo; setup_mcp_env; validate_mcp_cli
}

configure_project_flow() {
  choose_custom_addons_root
  
  local config_file="$ODOO_ROOT/.odoo-devkit/project.json"
  local existing_roots=()
  ADDON_ROOTS=()
  
  if [[ -f "$config_file" ]]; then
    while IFS= read -r line; do
      [[ -n "$line" ]] && existing_roots+=("$line")
    done < <(read_existing_roots "$config_file" 2>/dev/null)
  fi
  
  if [[ ${#existing_roots[@]} -gt 0 ]]; then
    warn "Existing project configuration found at: $config_file"
    info "Existing addon roots:"
    local idx=1
    local r
    for r in "${existing_roots[@]}"; do
      info "  $idx) $r"
      ((idx++))
    done
    printf '\n'
    info "Choose action:"
    info "  1) Keep existing roots"
    info "  2) Replace roots (reconfigure from scratch)"
    info "  3) Add additional roots"
    local re_choice
    re_choice="$(prompt_default "Selection" "1")"
    case "$re_choice" in
      1)
        ADDON_ROOTS=("${existing_roots[@]}")
        ;;
      2)
        collect_addon_roots
        ;;
      3)
        ADDON_ROOTS=("${existing_roots[@]}")
        collect_additional_roots
        ;;
      *)
        info "Invalid choice; keeping existing roots."
        ADDON_ROOTS=("${existing_roots[@]}")
        ;;
      esac
  else
    collect_addon_roots
  fi
  
  configure_optional_runtime
  write_project_config
  write_optional_project_settings
  write_runtime_global_config
  protect_local_project_config
  validate_project_config
}

verify_existing() {
  info "Starting verification of existing setup..."
  local errors=0

  # 1. Check Linux
  if [[ "$(uname -s)" == "Linux" ]]; then
    ok "Linux: Verified"
  else
    warn "OS: Non-Linux environment detected ($(uname -s))"
    ((errors++))
  fi

  # 2. Check Git
  if command -v git >/dev/null 2>&1; then
    ok "Git: $(git --version)"
  else
    warn "Git: Not found"
    ((errors++))
  fi

  # 3. Check Python
  local py_cmd
  py_cmd="$(find_python_cmd || true)"
  if [[ -n "$py_cmd" ]]; then
    local py_ver
    py_ver="$("$py_cmd" --version 2>&1)"
    ok "Python: $py_ver"
  else
    warn "Python 3.10+: Not found"
    ((errors++))
  fi

  # 4. Check uv
  if command -v uv >/dev/null 2>&1; then
    ok "uv: $(uv --version | head -n 1)"
  else
    warn "uv: Not found"
    ((errors++))
  fi

  # 5. Check ripgrep
  if command -v rg >/dev/null 2>&1; then
    ok "ripgrep: $(rg --version | head -n 1)"
  else
    warn "ripgrep: Not found (recommended)"
  fi

  # 6. Locate MCP Repo
  choose_mcp_dir
  if [[ -d "$MCP_DIR/.git" || -f "$MCP_DIR/pyproject.toml" ]]; then
    ok "MCP Repository: Verified at $MCP_DIR"
  else
    warn "MCP Repository: Not found at $MCP_DIR"
    ((errors++))
  fi

  # 7. Check MCP .venv
  if [[ -d "$MCP_DIR/.venv" ]]; then
    ok "MCP Python Environment (.venv): Verified"
  else
    warn "MCP Python Environment (.venv): Not found"
    ((errors++))
  fi

  # 8. Check CLI
  local cli_ok="false"
  if [[ -d "$MCP_DIR" ]]; then
    local help_output
    if help_output="$(cd "$MCP_DIR" && uv run odoo-devkit --help 2>/dev/null)"; then
      if grep -q "Odoo development MCP server" <<<"$help_output"; then
        cli_ok="true"
      fi
    fi
  fi
  if [[ "$cli_ok" == "true" ]]; then
    ok "odoo-devkit CLI: Verified"
  else
    warn "odoo-devkit CLI: FAILED validation"
    ((errors++))
  fi

  # 9. Choose Custom Addons / Project Root
  choose_custom_addons_root
  if [[ -f "$ODOO_ROOT/.odoo-devkit/project.json" ]]; then
    ok "Odoo Project Config: Found at $ODOO_ROOT/.odoo-devkit/project.json"
    
    # 10. Validate project.json structure and roots
    local config_file="$ODOO_ROOT/.odoo-devkit/project.json"
    local roots_ok="true"
    local existing_roots=()
    while IFS= read -r line; do
      [[ -n "$line" ]] && existing_roots+=("$line")
    done < <(read_existing_roots "$config_file" 2>/dev/null)

    if [[ ${#existing_roots[@]} -eq 0 ]]; then
      warn "Odoo Project Roots: No addon roots configured in project.json"
      ((errors++))
    else
      local r
      for r in "${existing_roots[@]}"; do
        if [[ -d "$r" ]]; then
          ok "  Addon Root (Exists): $r"
        else
          warn "  Addon Root (MISSING/INVALID): $r"
          roots_ok="false"
          ((errors++))
        fi
      done
      if [[ "$roots_ok" == "true" ]]; then
        ok "Odoo Project Roots: All configured roots verified"
      else
        warn "Odoo Project Roots: Some configured roots are missing"
      fi
    fi
  else
    warn "Odoo Project Config: Not found/configured for $ODOO_ROOT"
    ((errors++))
  fi

  # 11. Check Antigravity MCP Config
  local mcp_config_file="${HOME}/.gemini/config/mcp_config.json"
  local mcp_def_ok="false"
  if [[ -f "$mcp_config_file" && -n "$py_cmd" ]]; then
    if "$py_cmd" - "$mcp_config_file" <<'PY' >/dev/null 2>&1
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
server = data.get("mcpServers", {}).get("odoo-devkit")
if not isinstance(server, dict) or server.get("command") != "uv":
    sys.exit(1)
PY
    then
      mcp_def_ok="true"
    fi
  fi
  if [[ "$mcp_def_ok" == "true" ]]; then
    ok "Antigravity MCP Configuration: Verified in $mcp_config_file"
  else
    warn "Antigravity MCP Configuration: Missing or invalid in $mcp_config_file"
    ((errors++))
  fi

  # 12. Check optional RPC Configuration
  local global_file="${HOME}/.odoo-devkit/config.json"
  local rpc_configured="false"
  if [[ -f "$global_file" ]]; then
    rpc_configured="true"
    ok "RPC Configuration: Found at $global_file"
    
    # Optionally test connection
    if prompt_yes_no "Test Odoo RPC connection?" "y"; then
      info "Testing RPC connection..."
      if "$py_cmd" - "$global_file" <<'PY' 2>/dev/null
import json, sys, xmlrpc.client
from pathlib import Path
try:
    config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    url = config.get("url")
    db = config.get("database")
    user = config.get("username")
    password = config.get("password")
    if not all([url, db, user, password]):
        sys.exit(1)
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    uid = common.authenticate(db, user, password, {})
    if uid:
        sys.exit(0)
    else:
        sys.exit(2)
except Exception:
    sys.exit(3)
PY
      then
        ok "RPC Connection: Successful"
      else
        warn "RPC Connection: Failed to authenticate or connect"
        ((errors++))
      fi
    fi
  else
    info "RPC Configuration: Not configured (Optional)"
  fi

  if [[ $errors -eq 0 ]]; then
    ok "Verification Completed: All critical components are verified and functional."
  else
    warn "Verification Completed: Found $errors issue(s). Please run Option 4 (Repair) or Option 1 to resolve them."
  fi
}

repair_devkit() {
  info "Starting Repair / Update of DevKit..."
  
  common_prereqs
  
  choose_mcp_dir
  if [[ ! -d "$MCP_DIR/.git" && ! -f "$MCP_DIR/pyproject.toml" ]]; then
    die "MCP Repository not found at $MCP_DIR. Please run Option 1 (New / Complete Setup) first."
  fi
  
  # Check if user wants a clean rebuild of .venv
  local clean_rebuild="n"
  if [[ -d "$MCP_DIR/.venv" ]]; then
    if prompt_yes_no "A virtual environment already exists. Delete and recreate it for a clean rebuild?" "n"; then
      clean_rebuild="y"
    fi
  fi
  
  if [[ "$clean_rebuild" == "y" ]]; then
    info "Deleting existing virtual environment..."
    rm -rf "$MCP_DIR/.venv"
    ok "Virtual environment deleted."
  fi
  
  setup_mcp_env
  validate_mcp_cli
  
  # Repair Antigravity MCP config if missing or broken
  choose_custom_addons_root
  configure_antigravity
  validate_antigravity_config
  
  ok "Repair and update completed successfully."
}

main() {
  # Initialize detected paths from Antigravity configuration
  DETECTED_MCP=""
  DETECTED_ODOO=""
  while IFS= read -r line; do
    if [[ "$line" =~ ^MCP_DIR=(.*)$ ]]; then
      DETECTED_MCP="${BASH_REMATCH[1]}"
    elif [[ "$line" =~ ^ODOO_ROOT=(.*)$ ]]; then
      DETECTED_ODOO="${BASH_REMATCH[1]}"
    fi
  done < <(detect_configured_paths)

  select_mode
  case "$SETUP_MODE" in
    1)
      common_prereqs
      setup_or_repair_mcp
      configure_project_flow
      configure_antigravity
      validate_antigravity_config
      SETUP_SUCCESSFUL="yes"
      show_full_summary
      ;;
    2)
      common_prereqs
      choose_mcp_dir
      if [[ ! -d "$MCP_DIR/.git" && ! -f "$MCP_DIR/pyproject.toml" ]]; then
        die "MCP repository not found: $MCP_DIR. Run Option 1 first."
      fi
      configure_project_flow
      configure_antigravity
      validate_antigravity_config
      SETUP_SUCCESSFUL="yes"
      show_project_summary
      ;;
    3)
      verify_existing
      ;;
    4)
      repair_devkit
      SETUP_SUCCESSFUL="yes"
      ;;
    5)
      info "Exiting setup utility."
      exit 0
      ;;
  esac
}
main "$@"
