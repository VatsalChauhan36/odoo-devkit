'use strict';

// ── Theme ─────────────────────────────────────────────────────────────────────

(function initTheme() {
    const saved = localStorage.getItem('odoo-devkit-theme') || 'light';
    applyTheme(saved, true);
})();

function applyTheme(theme, silent) {
    document.documentElement.setAttribute('data-theme', theme);
    const btn = document.getElementById('theme-toggle');
    btn.textContent = theme === 'dark' ? '☀' : '🌙';
    btn.title = theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';
    if (!silent) localStorage.setItem('odoo-devkit-theme', theme);
}

document.getElementById('theme-toggle').addEventListener('click', function () {
    const current = document.documentElement.getAttribute('data-theme') || 'light';
    const next = current === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    localStorage.setItem('odoo-devkit-theme', next);
});

// ── Tab switching ─────────────────────────────────────────────────────────────
// Future tabs: add <a class="tab" data-tab="your-id"> in the header and
// <div id="tab-your-id" class="tab-content"> in main — no JS changes needed.

document.querySelectorAll('.header-tabs .tab').forEach(function (link) {
    link.addEventListener('click', function (e) {
        e.preventDefault();
        const target = this.getAttribute('data-tab');
        document.querySelectorAll('.header-tabs .tab').forEach(function (t) { t.classList.remove('active'); });
        document.querySelectorAll('.tab-content').forEach(function (c) { c.classList.remove('active'); });
        this.classList.add('active');
        const content = document.getElementById('tab-' + target);
        if (content) content.classList.add('active');
    });
});

// ── Toast ─────────────────────────────────────────────────────────────────────

let _toastTimer = null;

function showToast(msg, type) {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.className = 'toast ' + (type || 'ok');
    el.style.display = 'block';
    if (_toastTimer) clearTimeout(_toastTimer);
    _toastTimer = setTimeout(function () { el.style.display = 'none'; }, 3500);
}

// ── Path validation ───────────────────────────────────────────────────────────

function validatePath(path, statusId, expectDir) {
    const el = document.getElementById(statusId);
    if (!path || !path.trim()) { el.textContent = ''; return; }
    fetch('/api/validate_path', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: path })
    })
    .then(function (r) { return r.json(); })
    .then(function (d) {
        const ok = expectDir ? d.is_dir : (d.is_file || d.is_dir);
        el.textContent = ok ? '✓' : '✗';
        el.style.color = ok ? 'var(--status-ok)' : 'var(--status-err)';
    })
    .catch(function () { el.textContent = ''; });
}

function addValidation(inputId, statusId, expectDir) {
    let timer = null;
    document.getElementById(inputId).addEventListener('input', function () {
        clearTimeout(timer);
        const val = this.value;
        timer = setTimeout(function () { validatePath(val, statusId, expectDir); }, 400);
    });
}

addValidation('python-path', 'python-path-status', false);
addValidation('odoo-bin',    'odoo-bin-status',    false);
addValidation('odoo-config', 'odoo-config-status', false);
addValidation('docs-path',   'docs-path-status',   true);

// ── Native browse helper ──────────────────────────────────────────────────────
// Calls the Flask backend which opens a native tkinter file/dir dialog.

function browsePath(opts, callback) {
    fetch('/api/browse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(opts)
    })
    .then(function (r) { return r.json(); })
    .then(function (d) { if (d.path) callback(d.path); })
    .catch(function (err) { showToast('Browse failed: ' + err, 'err'); });
}

// Addons root browse
document.getElementById('browse-root-btn').addEventListener('click', function () {
    browsePath({ mode: 'dir', title: 'Select addons root directory' }, function (p) {
        document.getElementById('new-root-input').value = p;
    });
});

// Python browse
document.getElementById('browse-python-btn').addEventListener('click', function () {
    browsePath({
        mode: 'file',
        title: 'Select Python executable',
        filetypes: [['Python executables', 'python*'], ['All files', '*']],
        initial_dir: '/usr/bin'
    }, function (p) {
        document.getElementById('python-path').value = p;
        document.getElementById('python-path').dispatchEvent(new Event('input'));
    });
});

// odoo-bin browse
document.getElementById('browse-odoo-bin-btn').addEventListener('click', function () {
    browsePath({
        mode: 'file',
        title: 'Select odoo-bin executable',
        filetypes: [['All files', '*']]
    }, function (p) {
        document.getElementById('odoo-bin').value = p;
        document.getElementById('odoo-bin').dispatchEvent(new Event('input'));
    });
});

// odoo.conf browse
document.getElementById('browse-odoo-config-btn').addEventListener('click', function () {
    browsePath({
        mode: 'file',
        title: 'Select odoo.conf',
        filetypes: [['Config files', '*.conf'], ['All files', '*']]
    }, function (p) {
        document.getElementById('odoo-config').value = p;
        document.getElementById('odoo-config').dispatchEvent(new Event('input'));
    });
});

// Docs path browse
document.getElementById('browse-docs-btn').addEventListener('click', function () {
    browsePath({ mode: 'dir', title: 'Select Odoo documentation directory' }, function (p) {
        document.getElementById('docs-path').value = p;
        document.getElementById('docs-path').dispatchEvent(new Event('input'));
    });
});

// ── Detect Python ─────────────────────────────────────────────────────────────

document.getElementById('detect-python-btn').addEventListener('click', function () {
    const container = document.getElementById('python-detected');
    container.style.display = 'block';
    container.innerHTML = '<div class="detected-loading">Scanning for Python installations…</div>';

    fetch('/api/detect_python')
    .then(function (r) { return r.json(); })
    .then(function (data) {
        container.innerHTML = '';
        const pythons = data.pythons || [];
        if (pythons.length === 0) {
            container.innerHTML = '<div class="detected-loading">No Python installations found.</div>';
            return;
        }
        const current = document.getElementById('python-path').value.trim();
        pythons.forEach(function (py) {
            const item = document.createElement('div');
            item.className = 'detected-item' + (py.path === current ? ' selected' : '');

            const pathSpan = document.createElement('span');
            pathSpan.className = 'detected-path';
            pathSpan.textContent = py.path;
            item.appendChild(pathSpan);

            const verSpan = document.createElement('span');
            verSpan.className = 'detected-version';
            verSpan.textContent = py.version;
            item.appendChild(verSpan);

            item.addEventListener('click', function () {
                document.getElementById('python-path').value = py.path;
                document.getElementById('python-path').dispatchEvent(new Event('input'));
                // update selected highlight
                container.querySelectorAll('.detected-item').forEach(function (el) { el.classList.remove('selected'); });
                item.classList.add('selected');
            });

            container.appendChild(item);
        });
    })
    .catch(function (err) {
        container.innerHTML = '<div class="detected-loading">Detection failed: ' + err + '</div>';
    });
});

// ── RPC connection test ───────────────────────────────────────────────────────

document.getElementById('check-rpc-btn').addEventListener('click', function () {
    const btn = this;
    const statusEl = document.getElementById('rpc-status');
    btn.disabled = true;
    btn.textContent = '…';
    statusEl.style.display = 'none';

    const payload = {
        url:      document.getElementById('odoo-url').value.trim() || 'http://localhost:8069',
        database: document.getElementById('database').value.trim(),
        username: document.getElementById('odoo-username').value.trim() || 'admin',
        password: document.getElementById('odoo-password').value,
    };

    fetch('/api/check_rpc', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
        btn.disabled = false;
        btn.textContent = 'Test';
        statusEl.style.display = 'block';
        if (data.ok) {
            statusEl.className = 'rpc-status rpc-ok';
            statusEl.textContent = '✓ Connected — Odoo ' + (data.server_version || '') + ' (uid ' + data.uid + ')';
        } else {
            statusEl.className = 'rpc-status rpc-err';
            statusEl.textContent = '✗ ' + (data.error || 'Connection failed');
        }
    })
    .catch(function (err) {
        btn.disabled = false;
        btn.textContent = 'Test';
        statusEl.style.display = 'block';
        statusEl.className = 'rpc-status rpc-err';
        statusEl.textContent = '✗ ' + err;
    });
});

// ── Roots list ────────────────────────────────────────────────────────────────

let _roots = [];
let _projectRoot = '';

function renderRoots() {
    const list = document.getElementById('roots-list');
    list.innerHTML = '';

    if (_roots.length === 0) {
        const empty = document.createElement('p');
        empty.className = 'root-empty';
        empty.textContent = 'No paths added yet.';
        list.appendChild(empty);
        return;
    }

    _roots.forEach(function (root, i) {
        const item = document.createElement('div');
        item.className = 'root-item';

        // path text
        const pathSpan = document.createElement('span');
        pathSpan.className = 'root-path';
        pathSpan.textContent = root;
        item.appendChild(pathSpan);

        // validity indicator (async)
        const statusSpan = document.createElement('span');
        statusSpan.className = 'path-status';
        item.appendChild(statusSpan);
        fetch('/api/validate_path', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: root })
        })
        .then(function (r) { return r.json(); })
        .then(function (d) {
            statusSpan.textContent = d.is_dir ? '✓' : '✗';
            statusSpan.style.color = d.is_dir ? 'var(--status-ok)' : 'var(--status-err)';
        });

        // action buttons
        const actions = document.createElement('div');
        actions.className = 'root-actions';

        if (i > 0) {
            const up = _iconBtn('↑', 'Move up', function () { moveRoot(i, -1); });
            actions.appendChild(up);
        }
        if (i < _roots.length - 1) {
            const down = _iconBtn('↓', 'Move down', function () { moveRoot(i, 1); });
            actions.appendChild(down);
        }
        const del = _iconBtn('✕', 'Remove', function () { removeRoot(i); });
        del.classList.add('danger');
        actions.appendChild(del);

        item.appendChild(actions);
        list.appendChild(item);
    });
}

function _iconBtn(label, title, onClick) {
    const btn = document.createElement('button');
    btn.className = 'btn-icon';
    btn.title = title;
    btn.textContent = label;
    btn.addEventListener('click', onClick);
    return btn;
}

function addRoot(path) {
    path = (path || '').trim();
    if (!path) return;
    if (_roots.indexOf(path) !== -1) { showToast('Path already in list', 'err'); return; }
    _roots.push(path);
    renderRoots();
    document.getElementById('new-root-input').value = '';
}

function removeRoot(i) {
    _roots.splice(i, 1);
    renderRoots();
}

function moveRoot(i, dir) {
    const j = i + dir;
    if (j < 0 || j >= _roots.length) return;
    const tmp = _roots[i]; _roots[i] = _roots[j]; _roots[j] = tmp;
    renderRoots();
}

document.getElementById('add-root-btn').addEventListener('click', function () {
    addRoot(document.getElementById('new-root-input').value);
});
document.getElementById('new-root-input').addEventListener('keydown', function (e) {
    if (e.key === 'Enter') addRoot(this.value);
});

// ── Load / Save ───────────────────────────────────────────────────────────────

function loadConfig() {
    fetch('/api/config')
    .then(function (r) { return r.json(); })
    .then(function (cfg) {
        _roots = cfg.roots || [];
        _projectRoot = cfg.project_root || '';
        renderRoots();

        document.getElementById('python-path').value   = cfg.python_path || '';
        document.getElementById('odoo-bin').value      = cfg.odoo_bin    || '';
        document.getElementById('odoo-config').value   = cfg.odoo_config || '';
        document.getElementById('database').value      = cfg.database    || '';
        document.getElementById('docs-path').value     = cfg.docs_path   || '';
        document.getElementById('odoo-url').value      = cfg.url         || 'http://localhost:8069';
        document.getElementById('odoo-username').value = cfg.username    || 'admin';
        document.getElementById('odoo-password').value = cfg.password    || '';
        document.getElementById('open-browser').checked = cfg.open_browser !== false;
        document.getElementById('save-path').textContent = cfg.active_config_file || '';

        const scopeSelect = document.getElementById('save-scope');
        const projectOpt = scopeSelect.querySelector('option[value="project"]');
        const projectAvailable = !!cfg.project_root;
        projectOpt.disabled = !projectAvailable;
        scopeSelect.value = cfg.default_save_scope || (projectAvailable ? 'project' : 'global');
        if (!projectAvailable && scopeSelect.value === 'project') scopeSelect.value = 'global';

        const activeScopeText = cfg.active_scope
            ? ('Active config: ' + cfg.active_scope + (cfg.active_config_file ? (' (' + cfg.active_config_file + ')') : ''))
            : '';
        document.getElementById('active-scope').textContent = activeScopeText;
        document.getElementById('project-root').textContent = cfg.project_root
            ? ('Project root: ' + cfg.project_root)
            : 'Project root: not detected (global scope only)';

        // trigger path validation for pre-filled values
        ['python-path', 'odoo-bin', 'odoo-config', 'docs-path'].forEach(function (id) {
            const el = document.getElementById(id);
            if (el.value) el.dispatchEvent(new Event('input'));
        });
    })
    .catch(function (err) { showToast('Failed to load config: ' + err, 'err'); });
}

document.getElementById('save-btn').addEventListener('click', function () {
    const payload = {
        roots:        _roots,
        python_path:  document.getElementById('python-path').value.trim(),
        odoo_bin:     document.getElementById('odoo-bin').value.trim(),
        odoo_config:  document.getElementById('odoo-config').value.trim(),
        database:     document.getElementById('database').value.trim(),
        docs_path:    document.getElementById('docs-path').value.trim(),
        url:          document.getElementById('odoo-url').value.trim(),
        username:     document.getElementById('odoo-username').value.trim(),
        password:     document.getElementById('odoo-password').value,
        open_browser: document.getElementById('open-browser').checked,
        scope:        document.getElementById('save-scope').value,
        project_root: _projectRoot || null,
    };
    fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
        if (data.status === 'ok') {
            showToast('Configuration saved (' + (data.scope || 'global') + ')', 'ok');
            document.getElementById('save-path').textContent = data.config_file;
            loadConfig();
        } else {
            showToast('Error: ' + data.message, 'err');
        }
    })
    .catch(function (err) { showToast('Save failed: ' + err, 'err'); });
});

document.getElementById('discard-btn').addEventListener('click', function () {
    loadConfig();
    showToast('Changes discarded', 'ok');
});

// ── Run Command Parser ────────────────────────────────────────────────────────

/**
 * Tokenise a shell command into an array of tokens, respecting
 * single-quotes, double-quotes, and backslash escapes.
 */
function tokeniseCommand(cmd) {
    const tokens = [];
    let cur = '';
    let i = 0;
    while (i < cmd.length) {
        const ch = cmd[i];
        if (ch === '\\' && i + 1 < cmd.length) {
            cur += cmd[++i]; i++; continue;
        }
        if (ch === "'") {
            i++;
            while (i < cmd.length && cmd[i] !== "'") cur += cmd[i++];
            i++; continue;
        }
        if (ch === '"') {
            i++;
            while (i < cmd.length && cmd[i] !== '"') {
                if (cmd[i] === '\\' && i + 1 < cmd.length) { cur += cmd[++i]; i++; }
                else cur += cmd[i++];
            }
            i++; continue;
        }
        if (ch === ' ' || ch === '\t' || ch === '\n') {
            if (cur) { tokens.push(cur); cur = ''; }
            i++; continue;
        }
        cur += ch; i++;
    }
    if (cur) tokens.push(cur);
    return tokens;
}

/**
 * Parse tokens into a structured result:
 *   { python, odoo_bin, config, database, addons_paths, extra }
 *
 * Handles:
 *  - multi-line commands (source activate + actual command)
 *  - /usr/bin/env prefix
 *  - debugpy / pydevd launcher patterns (-- separator)
 *  - -c / --config, -d / --database, --addons-path, -r, -w, etc.
 */
function parseRunCommand(cmd) {
    // Split multi-line: take the last non-empty line that contains odoo-bin
    // or fall back to the last non-empty line overall
    const lines = cmd.split('\n').map(function (l) { return l.trim(); }).filter(Boolean);
    let line = lines[lines.length - 1] || '';
    for (let li = lines.length - 1; li >= 0; li--) {
        if (lines[li].indexOf('odoo-bin') !== -1 || lines[li].indexOf('odoo_bin') !== -1) {
            line = lines[li]; break;
        }
    }

    const result = { python: '', odoo_bin: '', config: '', database: '', addons_paths: [], extra: [] };
    let tokens = tokeniseCommand(line);
    if (!tokens.length) return result;

    let i = 0;

    // Skip `source` lines and leading env var assignments
    if (tokens[i] === 'source') return result;

    // Skip /usr/bin/env
    if (tokens[i] === '/usr/bin/env') i++;

    // Skip env var assignments (VAR=val)
    while (i < tokens.length && /^\w+=/.test(tokens[i])) i++;

    // Identify python executable
    const maybePython = tokens[i] || '';
    if (/python/.test(maybePython)) {
        result.python = maybePython;
        i++;

        // Skip launcher tokens (debugpy, pydevd, etc.) until '--' separator or odoo-bin
        for (let j = i; j < tokens.length; j++) {
            if (tokens[j] === '--') {
                i = j + 1;  // skip past '--'
                break;
            }
            if (tokens[j].indexOf('odoo-bin') !== -1 || tokens[j].indexOf('odoo_bin') !== -1) {
                i = j;
                break;
            }
        }
    }

    // Skip env var assignments again (after any separator)
    while (i < tokens.length && /^\w+=/.test(tokens[i])) i++;

    // Next token should be odoo-bin
    if (i < tokens.length && !tokens[i].startsWith('-')) {
        result.odoo_bin = tokens[i];
        i++;
    }

    // Parse flags — Odoo accepts both --flag value and --flag=value forms
    // Flags that take a value argument (next token)
    const valueFlags = {
        '-c': 'config', '--config': 'config',
        '-d': 'database', '--database': 'database', '--db-name': 'database',
        '-r': null, '--db_user': null, '--db-user': null,   // skip db user/pass
        '-w': null, '--db_password': null, '--db-password': null,
        '--db_host': null, '--db-host': null,
        '--db_port': null, '--db-port': null,
        '--db-filter': null, '--db_filter': null,
        '--xmlrpc-port': null, '--xmlrpc_port': null,
        '--http-port': null,
        '--longpolling-port': null,
        '--log-level': null,
        '--log-handler': null,
        '--logfile': null,
        '--limit-memory-hard': null, '--limit-memory-soft': null,
        '--limit-time-cpu': null, '--limit-time-real': null,
        '--workers': null,
        '-u': null, '--update': null,
        '-i': null, '--init': null,
        '--dev': null,
        '--test-enable': null,
        '--stop-after-init': null,
    };

    while (i < tokens.length) {
        const tok = tokens[i];

        // --addons-path / --addons_path (= or space separated)
        if (tok === '--addons-path' || tok === '--addons_path' || tok === '--path') {
            if (i + 1 < tokens.length) {
                tokens[++i].split(',').forEach(function (p) {
                    const t = p.trim(); if (t) result.addons_paths.push(t);
                });
            }
            i++; continue;
        }
        if (tok.startsWith('--addons-path=') || tok.startsWith('--addons_path=')) {
            tok.slice(tok.indexOf('=') + 1).split(',').forEach(function (p) {
                const t = p.trim(); if (t) result.addons_paths.push(t);
            });
            i++; continue;
        }

        // --flag=value form for known flags
        const eqIdx = tok.indexOf('=');
        if (eqIdx !== -1) {
            const flagName = tok.slice(0, eqIdx);
            const flagVal  = tok.slice(eqIdx + 1);
            if (flagName in valueFlags) {
                const key = valueFlags[flagName];
                if (key) result[key] = flagVal;
                i++; continue;
            }
        }

        // --flag value form for known flags
        if (tok in valueFlags) {
            const key = valueFlags[tok];
            if (i + 1 < tokens.length) {
                if (key) result[key] = tokens[i + 1];
                i += 2;
            } else {
                i++;
            }
            continue;
        }

        result.extra.push(tok);
        i++;
    }

    return result;
}

function renderCmdPreview(parsed) {
    const preview = document.getElementById('run-cmd-preview');
    preview.innerHTML = '';

    function addRow(key, val, multi) {
        const row = document.createElement('div');
        row.className = 'run-cmd-row';
        const k = document.createElement('span');
        k.className = 'run-cmd-key';
        k.textContent = key;
        row.appendChild(k);
        const v = document.createElement('span');
        v.className = 'run-cmd-val' + (multi ? ' multi' : '');
        if (multi) {
            val.forEach(function (item) {
                const tag = document.createElement('span');
                tag.className = 'run-cmd-tag';
                tag.textContent = item;
                v.appendChild(tag);
            });
        } else {
            v.textContent = val;
        }
        row.appendChild(v);
        preview.appendChild(row);
    }

    let hasAny = false;
    if (parsed.python)              { addRow('Python',       parsed.python);            hasAny = true; }
    if (parsed.odoo_bin)            { addRow('odoo-bin',     parsed.odoo_bin);           hasAny = true; }
    if (parsed.config)              { addRow('Config',       parsed.config);             hasAny = true; }
    if (parsed.database)            { addRow('Database',     parsed.database);           hasAny = true; }
    if (parsed.addons_paths.length) { addRow('Addons paths', parsed.addons_paths, true); hasAny = true; }

    preview.style.display = hasAny ? 'block' : 'none';
    return parsed;
}

let _lastParsed = null;

document.getElementById('run-command').addEventListener('input', function () {
    const val = this.value.trim();
    if (!val) {
        document.getElementById('run-cmd-preview').style.display = 'none';
        _lastParsed = null;
        return;
    }
    _lastParsed = parseRunCommand(val);
    renderCmdPreview(_lastParsed);
});

document.getElementById('parse-cmd-btn').addEventListener('click', function () {
    const val = document.getElementById('run-command').value.trim();
    if (!val) { showToast('Paste a run command first', 'err'); return; }

    _lastParsed = parseRunCommand(val);
    renderCmdPreview(_lastParsed);

    if (!_lastParsed.python && !_lastParsed.odoo_bin && !_lastParsed.config
            && !_lastParsed.database && !_lastParsed.addons_paths.length) {
        showToast('Nothing recognised in that command', 'err');
        return;
    }

    // Fill fields
    if (_lastParsed.python) {
        document.getElementById('python-path').value = _lastParsed.python;
        document.getElementById('python-path').dispatchEvent(new Event('input'));
    }
    if (_lastParsed.odoo_bin) {
        document.getElementById('odoo-bin').value = _lastParsed.odoo_bin;
        document.getElementById('odoo-bin').dispatchEvent(new Event('input'));
    }
    if (_lastParsed.database) {
        document.getElementById('database').value = _lastParsed.database;
    }

    // Config — fill and trigger parse (fetches addons_path)
    if (_lastParsed.config) {
        document.getElementById('odoo-config').value = _lastParsed.config;
        document.getElementById('odoo-config').dispatchEvent(new Event('input'));
        parseOdooConfig(_lastParsed.config);
    }

    // Addons paths from --addons-path arg (add directly, no banner)
    if (_lastParsed.addons_paths.length) {
        let added = 0;
        _lastParsed.addons_paths.forEach(function (p) {
            if (_roots.indexOf(p) === -1) { _roots.push(p); added++; }
        });
        if (added) renderRoots();
    }

    const parts = [];
    if (_lastParsed.python)              parts.push('Python');
    if (_lastParsed.odoo_bin)            parts.push('odoo-bin');
    if (_lastParsed.config)              parts.push('config');
    if (_lastParsed.database)            parts.push('database');
    if (_lastParsed.addons_paths.length) parts.push(_lastParsed.addons_paths.length + ' addons path(s)');
    showToast('Filled: ' + parts.join(', '), 'ok');
});

document.getElementById('clear-cmd-btn').addEventListener('click', function () {
    document.getElementById('run-command').value = '';
    document.getElementById('run-cmd-preview').style.display = 'none';
    _lastParsed = null;
});

// ── Detect odoo.conf ──────────────────────────────────────────────────────────

let _pendingAddonsPaths = [];  // paths parsed from the last selected odoo.conf

function parseOdooConfig(configPath) {
    if (!configPath || !configPath.trim()) {
        document.getElementById('import-addons-banner').style.display = 'none';
        return;
    }
    fetch('/api/parse_odoo_config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: configPath })
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
        if (data.error) {
            document.getElementById('import-addons-banner').style.display = 'none';
            return;
        }
        _pendingAddonsPaths = data.addons_path || [];
        const existing = _pendingAddonsPaths.filter(function (a) { return a.exists; });
        const banner = document.getElementById('import-addons-banner');
        const info = document.getElementById('import-addons-info');
        if (_pendingAddonsPaths.length === 0) {
            banner.style.display = 'none';
            return;
        }
        info.textContent = 'Found ' + _pendingAddonsPaths.length + ' addons_path entries'
            + (existing.length < _pendingAddonsPaths.length
                ? ' (' + (existing.length) + ' exist on disk)'
                : '') + '.';
        banner.style.display = 'flex';
    })
    .catch(function () {
        document.getElementById('import-addons-banner').style.display = 'none';
    });
}

// Wire up detect-odoo-config button
document.getElementById('detect-odoo-config-btn').addEventListener('click', function () {
    const container = document.getElementById('odoo-config-detected');
    container.style.display = 'block';
    container.innerHTML = '<div class="detected-loading">Scanning for odoo.conf…</div>';

    fetch('/api/detect_odoo_config')
    .then(function (r) { return r.json(); })
    .then(function (data) {
        container.innerHTML = '';
        const configs = data.configs || [];
        if (configs.length === 0) {
            container.innerHTML = '<div class="detected-loading">No odoo.conf found.</div>';
            return;
        }
        const current = document.getElementById('odoo-config').value.trim();
        configs.forEach(function (cfg) {
            const item = document.createElement('div');
            item.className = 'detected-item' + (cfg.path === current ? ' selected' : '');

            const pathSpan = document.createElement('span');
            pathSpan.className = 'detected-path';
            pathSpan.textContent = cfg.path;
            item.appendChild(pathSpan);

            const srcSpan = document.createElement('span');
            srcSpan.className = 'detected-version';
            srcSpan.textContent = cfg.source;
            item.appendChild(srcSpan);

            item.addEventListener('click', function () {
                document.getElementById('odoo-config').value = cfg.path;
                document.getElementById('odoo-config').dispatchEvent(new Event('input'));
                container.querySelectorAll('.detected-item').forEach(function (el) { el.classList.remove('selected'); });
                item.classList.add('selected');
                parseOdooConfig(cfg.path);
            });

            container.appendChild(item);
        });
    })
    .catch(function (err) {
        container.innerHTML = '<div class="detected-loading">Detection failed: ' + err + '</div>';
    });
});

// Also parse when user manually types/changes the odoo-config input (debounced)
(function () {
    let timer = null;
    document.getElementById('odoo-config').addEventListener('input', function () {
        clearTimeout(timer);
        const val = this.value;
        timer = setTimeout(function () { parseOdooConfig(val); }, 600);
    });
})();

// Import addons_path button
document.getElementById('import-addons-btn').addEventListener('click', function () {
    const toImport = _pendingAddonsPaths.filter(function (a) { return a.exists; });
    let added = 0;
    toImport.forEach(function (a) {
        if (_roots.indexOf(a.path) === -1) {
            _roots.push(a.path);
            added++;
        }
    });
    renderRoots();
    document.getElementById('import-addons-banner').style.display = 'none';
    showToast(added + ' path' + (added !== 1 ? 's' : '') + ' added to Addons Roots', 'ok');
});

// ── Boot ──────────────────────────────────────────────────────────────────────
loadConfig();
