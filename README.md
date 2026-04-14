# odoo-devkit

A token-efficient [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for Odoo 17/18/19 development. Gives AI assistants (Claude, Cursor, etc.) fast, structured access to your Odoo codebase — module discovery, model analysis, view navigation, XML validation, and code scaffolding — without loading entire files into context.

## Features

- **Module & model discovery** — find models, fields, methods, views, actions, menus, and security rules
- **Custom-first ranking** — discovery tools prefer matches from your custom addons root before standard Odoo code
- **View navigation with inheritance awareness** — trace inheritance chains and resolve inherited view models more accurately
- **Token-efficient search flows** — bounded file reads, compact response keys, module-scoped search, and optional inline context
- **Code scaffolding** — generate ready-to-apply unified diff patches for models, views, wizards, reports, menus, and security
- **XML validation** — validate view XML syntax and field names against model definitions, including inherited views
- **Read-only by default** — safe to use in automated workflows; no writes to your codebase

---

## Requirements

Before installing, make sure you have:

| Requirement | Version | Install |
|---|---|---|
| Python | 3.10+ | [python.org](https://www.python.org/downloads/) |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| ripgrep | any | `sudo apt install ripgrep` / `brew install ripgrep` |
| Git | any | [git-scm.com](https://git-scm.com/) |

> **Windows users:** ripgrep can be installed via `winget install BurntSushi.ripgrep.MSVC`

---

## Installation

### Step 1 — Clone the repository

```bash
git clone https://github.com/VatsalChauhan36/odoo-devkit.git
cd odoo-devkit
```

### Step 2 — Install dependencies

```bash
uv sync
```

This creates a virtual environment and installs all dependencies automatically.

### Step 3 — Verify it works

```bash
uv run odoo-devkit --help
```

You should see the CLI help output. If you get a `No valid roots found` error, that's expected — you need to configure your addons paths in the next step.

---

## Configuration

The server needs to know where your Odoo addons directories are.

### What paths to provide

A typical Odoo 18 setup has three roots:

| Path | What it contains |
|---|---|
| `/path/to/your/custom-addons` | Your own modules (put this **first**) |
| `/path/to/odoo/server/addons` | Odoo community modules |
| `/path/to/odoo/server/odoo/addons` | Odoo base modules |

> **Order matters** — the first root is treated as your custom addons directory (used by `list_custom_modules`).

### Option A — Environment variable (recommended)

**Linux / macOS:**
```bash
export ODOO_MCP_ROOTS="/path/to/your/addons:/path/to/odoo/server/addons:/path/to/odoo/server/odoo/addons"
```

**Windows (PowerShell):**
```powershell
$env:ODOO_MCP_ROOTS = "C:\your\addons;C:\odoo\server\addons;C:\odoo\server\odoo\addons"
```

> Use `:` as separator on Linux/macOS, `;` on Windows.

### Option B — CLI flags (deprecated, no-op)

```bash
uv run odoo-devkit \
  --roots /path/to/your/addons \
  --roots /path/to/odoo/server/addons \
  --roots /path/to/odoo/server/odoo/addons
```

`--roots` is kept only for backward compatibility and is ignored. Use `ODOO_MCP_ROOTS` or the saved config file instead.

### Optional — Odoo docs search

Set `ODOO_MCP_DOCS_PATH` to enable the `search_odoo_docs` tool. This should point to a locally cloned copy of the [Odoo documentation](https://github.com/odoo/documentation) repository.

```bash
# Clone the docs (one time)
git clone https://github.com/odoo/documentation.git /path/to/odoo/documentation

# Set the env var
export ODOO_MCP_DOCS_PATH="/path/to/odoo/documentation"
```

**Windows (PowerShell):**
```powershell
$env:ODOO_MCP_DOCS_PATH = "C:\odoo\documentation"
```

### Dashboard behavior (Serena-style flow)

The web dashboard starts with the MCP server by default.

- `open_browser` (saved config): controls auto-open on startup
- `enable_dashboard` (saved config): controls whether dashboard starts at all
- `dashboard_host` (saved config): bind address (default `127.0.0.1`)

CLI overrides:

```bash
uv run odoo-devkit --no-dashboard
uv run odoo-devkit --dashboard-host 0.0.0.0
uv run odoo-devkit --no-open-browser
```

If auto-open is disabled or unavailable (for example headless Linux), use the `open_dashboard` MCP tool to trigger browser opening manually.

---

## MCP Client Setup

### Claude Code

Add to your `.claude/settings.json`:

```json
{
  "mcpServers": {
    "odoo-devkit": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "run",
        "--directory", "/path/to/odoo-devkit",
        "odoo-devkit",
        "--roots", "/path/to/your/addons",
        "--roots", "/path/to/odoo/server/addons",
        "--roots", "/path/to/odoo/server/odoo/addons"
      ]
    }
  }
}
```

Or using the environment variable:

```json
{
  "mcpServers": {
    "odoo-devkit": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "/path/to/odoo-devkit", "odoo-devkit"],
      "env": {
        "ODOO_MCP_ROOTS": "/path/to/your/addons:/path/to/odoo/server/addons:/path/to/odoo/server/odoo/addons",
        "ODOO_MCP_DOCS_PATH": "/path/to/odoo/documentation"
      }
    }
  }
}
```

### Cursor

Add to your Cursor MCP config (`~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "odoo-devkit": {
      "command": "uv",
      "args": [
        "run",
        "--directory", "/path/to/odoo-devkit",
        "odoo-devkit",
        "--roots", "/path/to/your/addons",
        "--roots", "/path/to/odoo/server/addons",
        "--roots", "/path/to/odoo/server/odoo/addons"
      ]
    }
  }
}
```

### Other MCP clients

Use `command: "uv"` with the args pattern above. Refer to your client's MCP documentation for the exact config file location.

---

## Verifying the Setup

Once your MCP client is running, you can ask your AI assistant:

- *"List all custom Odoo modules"* → calls `list_custom_modules`
- *"Find the definition of sale.order model"* → calls `find_model_definition`
- *"Show me all views for product.template"* → calls `find_view_by_model`
- *"Inspect the full development surface for stock.picking"* → calls `inspect_model_surface`
- *"Where should I override the confirm button in sale.order form?"* → calls `locate_view_override`

---

## Tools Reference

### Discovery

| Tool | Description |
|------|-------------|
| `list_modules` | List all modules across all configured roots |
| `list_custom_modules` | List modules from your custom addons root only |
| `get_module_manifest` | Parse `__manifest__.py` fields for a module |
| `get_module_structure` | Return a module file tree for one or more modules |
| `glob_odoo_files` | Find files by glob pattern across addons roots |
| `read_file_lines` | Read a bounded line range from any allowed file |
| `search_odoo_code` | Token-bounded ripgrep search across all roots |
| `search_odoo_docs` | Search local Odoo documentation (requires `ODOO_MCP_DOCS_PATH`) |

### Workflow Tools

| Tool | Description |
|------|-------------|
| `inspect_model_surface` | One-call model summary: definitions, fields, methods, views, actions, menus, security, related files |
| `locate_view_override` | Find the best XML views and files to inspect or override for a field, button, xml_id, or text target |

### Model & Field Analysis

| Tool | Description |
|------|-------------|
| `find_model_definition` | Find files defining a model by `_name` or `_inherit` |
| `get_model_fields` | List all field declarations for a model |
| `find_method_definition` | Find Python method definitions, optionally with inline body context |
| `find_xml_id_definition` | Find XML records by external ID |
| `find_security_access_for_model` | Find `ir.model.access` and `ir.rule` records for a model |

### View Navigation

| Tool | Description |
|------|-------------|
| `find_view_definition` | Find a view by XML ID, name, or model |
| `find_inherited_views` | Find all views that inherit from a given view |
| `find_view_by_model` | Find all views registered for a model |
| `find_view_chain` | Resolve the full inheritance chain for a view |
| `find_field_in_views` | Find which views reference a specific field |
| `validate_view_xml` | Validate view XML syntax and field names |

### Action & Menu Discovery

| Tool | Description |
|------|-------------|
| `find_action_by_model` | Find `ir.actions.act_window` records for a model |
| `find_menu_hierarchy` | Find menu items and their parent/child chains |

### Code Scaffolding (generate unified diff patches)

| Tool | Description |
|------|-------------|
| `scaffold_model_patch` | New model with optional views and security access |
| `scaffold_inherit_model_patch` | Extend an existing model with fields/methods |
| `scaffold_view_inherit_patch` | Inherit and modify an existing view with XPath |
| `scaffold_views_patch` | Full set of views (form/list/search/kanban) for a model |
| `scaffold_action_patch` | `ir.actions.act_window` XML |
| `scaffold_menu_patch` | Menu item XML linked to an action |
| `scaffold_security_access_patch` | `ir.model.access.csv` entries |
| `scaffold_record_rule_patch` | `ir.rule` XML for record-level security |
| `scaffold_wizard_patch` | `TransientModel` + wizard view |
| `scaffold_report_patch` | Report Python model + QWeb template + action |

### Module Maintenance

| Tool | Description |
|------|-------------|
| `manifest_update_patch` | Add data file entries to `__manifest__.py` |
| `init_update_patch` | Add import statements to `__init__.py` |
| `run_module_upgrade` | Run `odoo-bin -u <module> --stop-after-init` (requires `odoo_bin` path) |

### Runtime UI

| Tool | Description |
|------|-------------|
| `open_dashboard` | Open the running dashboard in the default browser |

---

## Recommended Low-Token Workflows

These tool combinations are the fastest path to good answers without flooding the model context.

### 1. Start narrow, then read

Use:

- `list_custom_modules`
- `get_module_structure`
- `glob_odoo_files`
- `read_file_lines`

Example flow:

1. List the custom module.
2. Inspect only that module's tree.
3. Glob for likely targets such as `models/*.py` or `views/*.xml`.
4. Read only the exact line ranges you need.

This avoids loading full files or scanning all addons roots too early.

### 2. Prefer scoped search over global grep

Use `search_odoo_code` with:

- `module_filter` when you already know the module
- a specific `glob` such as `models/*.py`, `views/*.xml`, or `security/*`
- `context_lines` only when inline context will save a follow-up file read

This keeps both ripgrep output and assistant context much smaller.

### 3. Use method search instead of broad code search

If you know the Python method name, prefer `find_method_definition` over `search_odoo_code`.

It can:

- filter by model
- return only method definitions
- include the method body inline with `context_lines`

That is usually the best token-to-signal ratio for Python debugging.

### 4. Let view tools do the inheritance work

When exploring XML, prefer:

- `find_view_definition`
- `find_inherited_views`
- `find_view_by_model`
- `find_view_chain`
- `find_field_in_views`
- `validate_view_xml`

These tools now handle inherited view/model resolution better than a plain XML text search.

### 5. Lean on custom-first ranking

Most discovery tools return custom-module matches before standard Odoo ones. In mixed codebases, this usually surfaces the right answer sooner and reduces wasted follow-up calls.

### 6. Use workflow tools for common Odoo tasks

Prefer these when you want an answer, not just raw building blocks:

- `inspect_model_surface` for "show me everything important about this model"
- `locate_view_override` for "where should I edit or inherit this field/button/view target"

They compose the lower-level tools for you and usually save several MCP round trips.

---

## Troubleshooting

**`No valid roots found` error**
→ You haven't configured any roots. Set `ODOO_MCP_ROOTS` or configure roots in `~/.odoo-devkit/config.json`.

**`rg: command not found`**
→ Install ripgrep: `sudo apt install ripgrep` (Ubuntu) / `brew install ripgrep` (macOS)

**MCP server not connecting in Claude Code**
→ Check the `--directory` path in your config points to where you cloned the repo.
→ Run `uv sync` again inside the repo directory.

**Dashboard did not open automatically**
→ Check `open_browser` is enabled in config, or pass `--open-browser`.
→ On headless Linux (no `DISPLAY`/`WAYLAND_DISPLAY`), auto-open is skipped; use `open_dashboard` or open the dashboard URL manually.

**`uv: command not found`**
→ Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh` then restart your terminal.

→ On Ubuntu/Linux, uv installs to `~/.local/bin` which may not be in your `PATH`. Fix it by creating a symlink:
```bash
sudo ln -s ~/.local/bin/uv /usr/local/bin/uv
```
Then verify with `uv --version`. If you prefer not to use sudo, add `~/.local/bin` to your PATH instead:
```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
```

---

## License

MIT — see [LICENSE](LICENSE)
