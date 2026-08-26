"""Authenticated Aperyn gateway for the private OpenCode agent service.

The browser never receives OpenCode credentials or talks to the engine directly.
Every remote session is mapped to one Aperyn administrator in SQLite.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import os
import sqlite3
import threading
import time
import uuid

import requests
from flask import Blueprint, abort, g, jsonify, render_template, request


def tool_change_groups(messages, workspace):
    """Associate structured file changes with the assistant response that made them."""
    root = Path(workspace).resolve(strict=False)
    groups = {}

    def normalized_file(value):
        if not value:
            return None
        raw = Path(str(value))
        resolved = raw.resolve(strict=False) if raw.is_absolute() else (root / raw).resolve(strict=False)
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError:
            return None

    def store(parent_id, item):
        if not isinstance(item, dict):
            return
        file_name = normalized_file(item.get('file') or item.get('filepath') or item.get('filePath') or item.get('relativePath'))
        if not file_name:
            return
        result = {
            'file': file_name,
            'status': str(item.get('status') or item.get('type') or 'modified'),
            'additions': int(item.get('additions') or 0),
            'deletions': int(item.get('deletions') or 0),
        }
        for key in ('patch', 'before', 'after'):
            if isinstance(item.get(key), str):
                result[key] = item[key]
        group_id = str(parent_id or '').strip()
        if not group_id:
            return
        groups.setdefault(group_id, {})[file_name] = result

    # Some OpenCode summaries are attached to the originating user turn. Map
    # those to its immediate assistant child before building cards, otherwise a
    # later refresh can make one summary appear beneath the wrong response.
    child_response = {}
    for message in messages or []:
        info = message.get('info') if isinstance(message, dict) and isinstance(message.get('info'), dict) else {}
        if str(info.get('role') or '') == 'assistant' and info.get('parentID') and info.get('id'):
            child_response.setdefault(str(info['parentID']), str(info['id']))

    for message in messages or []:
        if not isinstance(message, dict):
            continue
        info = message.get('info') if isinstance(message.get('info'), dict) else {}
        role = str(info.get('role') or '')
        # Keep a diff with the assistant response that performed the work. A
        # session may have several assistant turns under one user prompt, so
        # using only parentID makes old and new file summaries migrate to a
        # later response when the timeline refreshes.
        message_id = info.get('id') or info.get('parentID')
        summary = info.get('summary') if isinstance(info.get('summary'), dict) else {}
        if role == 'user':
            message_id = child_response.get(str(info.get('id') or ''), message_id)
            for item in summary.get('diffs') or []:
                store(message_id, item)
        for part in message.get('parts') or []:
            if not isinstance(part, dict) or part.get('type') != 'tool':
                continue
            state = part.get('state') if isinstance(part.get('state'), dict) else {}
            if state.get('status') != 'completed':
                continue
            metadata = state.get('metadata') if isinstance(state.get('metadata'), dict) else {}
            filediff = metadata.get('filediff')
            if isinstance(filediff, dict):
                store(message_id, filediff)
            for item in metadata.get('files') or []:
                store(message_id, item)
            tool = str(part.get('tool') or '').lower()
            payload = state.get('input') if isinstance(state.get('input'), dict) else {}
            if tool == 'write' and isinstance(payload.get('content'), str):
                content = payload['content']
                store(message_id, {
                    'file': payload.get('filePath') or metadata.get('filepath'),
                    'status': 'modified' if metadata.get('exists') else 'added',
                    'additions': len(content.splitlines()),
                    'deletions': 0,
                    'after': content,
                })
            elif tool in {'edit', 'apply_patch', 'patch'} and isinstance(metadata.get('diff'), str):
                store(message_id, {
                    'file': payload.get('filePath') or metadata.get('filepath'),
                    'status': 'modified',
                    'patch': metadata['diff'],
                    'additions': metadata.get('additions', 0),
                    'deletions': metadata.get('deletions', 0),
                })
    return [{'parent_id': parent_id, 'diff': list(changes.values())}
            for parent_id, changes in groups.items() if changes]


def tool_change_fallback(messages, workspace):
    """Flatten per-turn changes for the session-wide Activity panel fallback."""
    changes = {}
    for group in tool_change_groups(messages, workspace):
        for item in group['diff']:
            changes[item['file']] = item
    return list(changes.values())


class AgentEngineError(RuntimeError):
    def __init__(self, message, status=502, state='unreachable'):
        super().__init__(message)
        self.status = status
        self.state = state


def create_agent_blueprint(database_path, current_user, ollama_api, external_models=None):
    bp = Blueprint('agent', __name__)
    engine_url = os.environ.get('OPENCODE_URL', 'http://agent:4096').rstrip('/')
    engine_username = os.environ.get('OPENCODE_USERNAME', 'aperyn')
    secret_path = Path(os.environ.get('OPENCODE_SECRET_PATH', '/data/agent/server.password'))
    workspace = os.environ.get('OPENCODE_WORKSPACE', '/workspace').rstrip('/') or '/workspace'
    workspace_root = Path(workspace).resolve()
    workspace_display = os.environ.get('OPENCODE_WORKSPACE_DISPLAY', workspace).strip().rstrip('/') or '/'
    mnt_workspace = os.environ.get('OPENCODE_MNT_WORKSPACE', '/mnt').rstrip('/') or '/mnt'
    mnt_root = Path(mnt_workspace).resolve()
    mnt_display = os.environ.get('OPENCODE_MNT_DISPLAY', '/mnt').strip().rstrip('/') or '/mnt'
    workspace_roots = (
        {'key': 'home', 'token': '.', 'path': workspace_root, 'display': workspace_display},
        {'key': 'mnt', 'token': '@mnt', 'path': mnt_root, 'display': mnt_display},
    )
    provider_cache = {'expires': 0.0, 'limits': {}}
    provider_cache_lock = threading.Lock()

    def db():
        conn = sqlite3.connect(database_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA busy_timeout=30000')
        return conn

    def now():
        return datetime.now(timezone.utc).isoformat()

    def admin(api=True):
        user = current_user()
        if user and user.get('role') == 'admin':
            return user
        if api:
            abort(403, description='Administrator access is required for Agent workspaces')
        abort(403)

    def secret():
        try:
            value = secret_path.read_text(encoding='utf-8').strip()
        except OSError:
            value = ''
        if not value:
            raise AgentEngineError('Agent engine is still starting', 503, 'starting')
        return value

    def root_for_path(path):
        resolved = Path(path).resolve(strict=False)
        for item in sorted(workspace_roots, key=lambda row: len(str(row['path'])), reverse=True):
            try:
                resolved.relative_to(item['path'])
                return item
            except ValueError:
                continue
        return None

    def safe_workspace(value=None, *, require_existing=True):
        raw = str(value or '.').strip().replace('\\', '/') or '.'
        root = workspace_roots[0]
        if raw == '@mnt' or raw.startswith('@mnt/'):
            root = workspace_roots[1]
            candidate = Path(raw.removeprefix('@mnt').lstrip('/') or '.')
        elif Path(raw).is_absolute():
            absolute = Path(raw).resolve(strict=False)
            root = root_for_path(absolute)
            if root is None:
                abort(400, description='Working directory must stay inside an available Agent workspace')
            candidate = absolute.relative_to(root['path'])
        else:
            candidate = Path(raw)
        resolved = (root['path'] / candidate).resolve(strict=False)
        try:
            resolved.relative_to(root['path'])
        except ValueError:
            abort(400, description='Working directory must stay inside an available Agent workspace')
        if require_existing and (not resolved.exists() or not resolved.is_dir()):
            abort(400, description='Working directory does not exist')
        return str(resolved)

    def workspace_value(path):
        resolved = Path(path).resolve()
        root = root_for_path(resolved)
        if root is None:
            abort(400, description='Working directory is outside the available Agent workspaces')
        relative = resolved.relative_to(root['path'])
        if root['token'] == '.':
            return '.' if str(relative) == '.' else relative.as_posix()
        return root['token'] if str(relative) == '.' else f"{root['token']}/{relative.as_posix()}"

    def workspace_label(path):
        resolved = Path(path).resolve()
        root = root_for_path(resolved)
        if root is None:
            return str(resolved)
        relative = resolved.relative_to(root['path'])
        return root['display'] if str(relative) == '.' else f"{root['display']}/{relative.as_posix()}"

    def derived_status(row, engine_state=None, *, permissions=None, questions=None, messages=None):
        if permissions or questions:
            return 'waiting'
        state = str((engine_state or {}).get('type') or '').lower() if isinstance(engine_state, dict) else ''
        if state in {'busy', 'running', 'retry'}:
            return 'running'
        if state in {'error', 'failed'}:
            return 'error'
        previous = str(row.get('status') or 'idle').lower()
        if previous in {'completed', 'stopped', 'error'}:
            return previous
        if messages:
            roles = [str((item.get('info') or {}).get('role') or '') for item in messages if isinstance(item, dict)]
            if roles and roles[-1] == 'user':
                return 'running'
            if 'assistant' in roles:
                return 'completed'
        if previous in {'running', 'busy', 'waiting'}:
            return 'completed'
        return 'idle'

    def approval_mode(value):
        return value if value in ('ask', 'safe', 'full') else 'ask'

    def safe_automatic_permission(item):
        permission = str(item.get('permission') or '').lower()
        if permission in {'read', 'glob', 'grep', 'list', 'todoread', 'todowrite'}:
            return True
        command = str((item.get('metadata') or {}).get('command') or '').strip().lower()
        return bool(command) and any(command == base or command.startswith(base + ' ')
                                     for base in ('pwd', 'ls', 'find', 'git status', 'git diff', 'cat', 'head', 'tail', 'wc'))

    def apply_automatic_permissions(remote_id, directory, mode, permissions):
        if mode == 'ask':
            return permissions
        remaining = []
        for item in permissions:
            if not isinstance(item, dict) or not item.get('id'):
                continue
            if mode == 'full' or safe_automatic_permission(item):
                try:
                    engine('POST', f"/permission/{item['id']}/reply", body={'reply': 'always' if mode == 'full' else 'once'}, timeout=10, directory=directory)
                except AgentEngineError:
                    remaining.append(item)
            else:
                remaining.append(item)
        return remaining

    def engine(method, path, *, body=None, timeout=20, allow_404=False, directory=None):
        try:
            response = requests.request(
                method,
                f"{engine_url}/{path.lstrip('/')}",
                params={'directory': safe_workspace(directory or workspace)},
                json=body,
                auth=(engine_username, secret()),
                timeout=(3, timeout),
            )
        except requests.RequestException as exc:
            raise AgentEngineError('Agent engine is unreachable', 503, 'unreachable') from exc
        if response.status_code == 401:
            raise AgentEngineError('Agent engine authentication mismatch', 502, 'authentication_mismatch')
        if allow_404 and response.status_code == 404:
            return None
        if not response.ok:
            message = 'Agent engine request failed'
            try:
                upstream = response.json()
                detail = upstream.get('message') or upstream.get('error')
                if isinstance(detail, str) and detail.strip():
                    message = detail.strip()[:240]
            except Exception:
                pass
            raise AgentEngineError(message, 409 if response.status_code in (400, 409) else 502, 'error')
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    def session_row(public_id, user_id):
        with db() as conn:
            row = conn.execute('SELECT * FROM agent_sessions WHERE id=? AND user_id=?', (public_id, user_id)).fetchone()
        if not row:
            abort(404, description='Agent session not found')
        return dict(row)

    def optional(path, default, directory=None):
        try:
            value = engine('GET', path, timeout=8, directory=directory)
            return default if value is None else value
        except AgentEngineError:
            return default

    def installed_models():
        try:
            response = requests.get(f"{ollama_api.rstrip('/')}/api/tags", timeout=(3, 12))
            response.raise_for_status()
            rows = response.json().get('models') or []
        except (requests.RequestException, ValueError) as exc:
            raise AgentEngineError('Could not read installed Ollama models', 503, 'ollama_unreachable') from exc
        result = []
        seen = set()
        for item in rows:
            name = str(item.get('name') or item.get('model') or '').strip()
            if name and name not in seen:
                seen.add(name)
                result.append({'provider': 'ollama', 'provider_name': 'Ollama', 'name': name, 'value': f'ollama:{name}',
                               'size': int(item.get('size') or 0), 'modified_at': item.get('modified_at')})
        if external_models:
            result.extend(external_models())
        return result

    def pending_for(remote_id, kind, directory):
        values = optional(kind, [], directory)
        return [item for item in values if isinstance(item, dict) and item.get('sessionID') == remote_id]

    def provider_limits(directory):
        current_time = time.monotonic()
        with provider_cache_lock:
            if provider_cache['expires'] > current_time:
                return provider_cache['limits']
            payload = optional('/config/providers', {}, directory)
            limits = {}
            for provider in payload.get('providers', []) if isinstance(payload, dict) else []:
                provider_id = str(provider.get('id') or '')
                models = provider.get('models') or {}
                if not provider_id or not isinstance(models, dict):
                    continue
                for model_id, model in models.items():
                    limit = (model or {}).get('limit') or {} if isinstance(model, dict) else {}
                    try:
                        context = int(limit.get('context') or 0)
                    except (TypeError, ValueError):
                        context = 0
                    limits[(provider_id, str(model_id))] = max(0, context)
            provider_cache['limits'] = limits
            # OpenCode can briefly return no providers while its runtime is
            # starting. Do not turn that transient empty response into five
            # minutes without a context limit.
            provider_cache['expires'] = current_time + (300 if limits else 5)
            return limits

    def context_usage(messages, model_value, directory):
        def has_usage(item):
            if not isinstance(item, dict):
                return False
            info = item.get('info') if isinstance(item.get('info'), dict) else {}
            tokens = info.get('tokens') if isinstance(info.get('tokens'), dict) else {}
            cache = tokens.get('cache') if isinstance(tokens.get('cache'), dict) else {}
            values = (tokens.get('total'), tokens.get('input'), tokens.get('output'),
                      cache.get('read'), cache.get('write'))
            try:
                return info.get('role') == 'assistant' and any(int(value or 0) > 0 for value in values)
            except (TypeError, ValueError):
                return False

        # A newly streaming OpenCode assistant message initially contains a
        # zero-filled token object. Keep the latest real OpenCode counter on
        # screen until that message reports usage instead of flashing 0%.
        latest = next((item for item in reversed(messages) if has_usage(item)), None)
        info = (latest or {}).get('info') or {}
        provider_id = str(info.get('providerID') or '')
        model_id = str(info.get('modelID') or '')
        if (not provider_id or not model_id) and model_value and ':' in model_value:
            fallback_provider, fallback_model = str(model_value).split(':', 1)
            provider_id = provider_id or fallback_provider
            model_id = model_id or fallback_model
        tokens = info.get('tokens') or {}
        cache = tokens.get('cache') or {} if isinstance(tokens, dict) else {}
        def token_value(value):
            try:
                return max(0, int(value or 0))
            except (TypeError, ValueError):
                return 0
        input_tokens = token_value(tokens.get('input'))
        output_tokens = token_value(tokens.get('output'))
        reasoning_tokens = token_value(tokens.get('reasoning'))
        cache_read = token_value(cache.get('read')) if isinstance(cache, dict) else 0
        cache_write = token_value(cache.get('write')) if isinstance(cache, dict) else 0
        # This mirrors OpenCode's own overflow accounting; reasoning is already
        # represented within output and must not be added a second time.
        calculated_used = input_tokens + cache_read + output_tokens
        reported_total = token_value(tokens.get('total'))
        used = reported_total or calculated_used
        limit = provider_limits(directory).get((provider_id, model_id), 0) if provider_id and model_id else 0
        return {
            'source': 'opencode', 'used': used, 'limit': limit,
            'percent': round((used / limit) * 100, 1) if limit else None,
            'input': input_tokens, 'output': output_tokens, 'reasoning': reasoning_tokens,
            'cache_read': cache_read, 'cache_write': cache_write,
            'provider_id': provider_id, 'model_id': model_id,
        }

    def owned_pending(request_id, kind, user_id):
        """Find a pending request inside the directory-scoped engine view.

        OpenCode scopes permission and question queues to the request's working
        directory. Querying only the root workspace silently hides approvals
        raised by sessions in child folders.
        """
        with db() as conn:
            rows = [dict(row) for row in conn.execute(
                'SELECT remote_id,workspace FROM agent_sessions WHERE user_id=? ORDER BY updated_at DESC',
                (user_id,),
            ).fetchall()]
        for row in rows:
            values = optional(kind, [], row['workspace'])
            target = next((item for item in values if isinstance(item, dict) and item.get('id') == request_id
                           and item.get('sessionID') == row['remote_id']), None)
            if target:
                return target, row
        return None, None

    @bp.errorhandler(AgentEngineError)
    def engine_error(error):
        return jsonify({'error': str(error), 'state': error.state}), error.status

    @bp.errorhandler(403)
    def forbidden(error):
        if request.path.startswith('/api/'):
            return jsonify({'error': getattr(error, 'description', 'Forbidden')}), 403
        return error

    @bp.errorhandler(404)
    def not_found(error):
        if request.path.startswith('/api/'):
            return jsonify({'error': getattr(error, 'description', 'Not found')}), 404
        return error

    @bp.get('/agent')
    def agent_page():
        admin(api=False)
        return render_template('agent.html')

    @bp.get('/api/agent/status')
    def agent_status():
        admin()
        try:
            value = engine('GET', '/global/health', timeout=4) or {}
            return jsonify({'state': 'connected', 'connected': True, 'version': value.get('version', ''), 'workspace': workspace_display})
        except AgentEngineError as error:
            return jsonify({'state': error.state, 'connected': False, 'error': str(error), 'workspace': workspace_display})

    @bp.get('/api/agent/workspaces')
    def agent_workspaces():
        admin()
        current = safe_workspace(request.args.get('path') or '.')
        current_path = Path(current)
        current_root = root_for_path(current_path)
        directories = []
        try:
            for child in sorted(current_path.iterdir(), key=lambda item: item.name.casefold()):
                if child.is_symlink() or not child.is_dir():
                    continue
                resolved = child.resolve()
                try:
                    resolved.relative_to(current_root['path'])
                except ValueError:
                    continue
                directories.append({'name': child.name, 'path': workspace_value(resolved)})
                if len(directories) >= 250:
                    break
        except OSError:
            abort(400, description='Working directory cannot be read')
        relative = workspace_value(current)
        if current_root['key'] == 'home' and relative == '.' and mnt_root.exists() and mnt_root.is_dir():
            directories.insert(0, {'name': '/mnt', 'path': '@mnt', 'root': True})
        if current_path == current_root['path']:
            parent = '.' if current_root['key'] != 'home' else None
        else:
            parent = workspace_value(current_path.parent)
        return jsonify({'root': workspace_display, 'current': relative, 'display': workspace_label(current),
                        'parent': parent, 'directories': directories})

    @bp.get('/api/agent/models')
    def agent_models():
        admin()
        return jsonify({'models': installed_models()})

    @bp.get('/api/agent/sessions')
    def agent_sessions():
        user = admin()
        with db() as conn:
            rows = [dict(row) for row in conn.execute(
                'SELECT * FROM agent_sessions WHERE user_id=? ORDER BY updated_at DESC LIMIT 250', (user['id'],)
            ).fetchall()]
            views = {}
            for row in rows:
                directory = row['workspace']
                if directory not in views:
                    views[directory] = {
                        'statuses': engine('GET', '/session/status', timeout=8, directory=directory) or {},
                        'permissions': optional('/permission', [], directory),
                        'questions': optional('/question', [], directory),
                    }
                view = views[directory]
                statuses = view['statuses']
                state = statuses.get(row['remote_id']) if isinstance(statuses, dict) else None
                permissions = [item for item in view['permissions'] if isinstance(item, dict) and item.get('sessionID') == row['remote_id']]
                questions = [item for item in view['questions'] if isinstance(item, dict) and item.get('sessionID') == row['remote_id']]
                status = derived_status(row, state, permissions=permissions, questions=questions)
                row['status'] = status
                row['workspace_value'] = workspace_value(row['workspace'])
                row['workspace'] = workspace_label(row['workspace'])
                conn.execute('UPDATE agent_sessions SET status=?,last_seen_at=? WHERE id=?', (status, now(), row['id']))
                row.pop('remote_id', None)
                row.pop('user_id', None)
        return jsonify({'sessions': rows, 'engine_connected': True})

    @bp.post('/api/agent/sessions')
    def agent_session_create():
        user = admin()
        data = request.get_json(silent=True) or {}
        title = str(data.get('title') or 'New agent task').strip()[:100] or 'New agent task'
        mode = str(data.get('agent') or 'build')
        permission_mode = approval_mode(str(data.get('approval_mode') or 'ask'))
        if mode not in ('build', 'plan'):
            return jsonify({'error': 'Unknown agent mode'}), 400
        selected_workspace = safe_workspace(data.get('workspace') or '.')
        remote = engine('POST', '/session', body={'title': title}, timeout=15, directory=selected_workspace) or {}
        remote_id = str(remote.get('id') or '')
        if not remote_id:
            raise AgentEngineError('Agent engine did not return a session identifier')
        public_id = uuid.uuid4().hex
        stamp = now()
        with db() as conn:
            conn.execute(
                'INSERT INTO agent_sessions(id,remote_id,user_id,title,agent_mode,approval_mode,status,workspace,created_at,updated_at,last_seen_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (public_id, remote_id, user['id'], title, mode, permission_mode, 'idle', selected_workspace, stamp, stamp, stamp),
            )
        return jsonify({'id': public_id, 'title': title, 'agent_mode': mode, 'approval_mode': permission_mode, 'status': 'idle',
                        'workspace': workspace_label(selected_workspace),
                        'workspace_value': workspace_value(selected_workspace), 'created_at': stamp})

    @bp.patch('/api/agent/sessions/<public_id>')
    def agent_session_update(public_id):
        user = admin()
        row = session_row(public_id, user['id'])
        data = request.get_json(silent=True) or {}
        title = str(data.get('title') or row['title']).strip()[:100] or row['title']
        engine('PATCH', f"/session/{row['remote_id']}", body={'title': title}, timeout=10, directory=row['workspace'])
        with db() as conn:
            conn.execute('UPDATE agent_sessions SET title=?,updated_at=? WHERE id=?', (title, now(), public_id))
        return jsonify({'success': True, 'title': title})

    @bp.delete('/api/agent/sessions/<public_id>')
    def agent_session_delete(public_id):
        user = admin()
        row = session_row(public_id, user['id'])
        engine('DELETE', f"/session/{row['remote_id']}", timeout=15, allow_404=True, directory=row['workspace'])
        with db() as conn:
            conn.execute('DELETE FROM agent_sessions WHERE id=? AND user_id=?', (public_id, user['id']))
        return jsonify({'success': True})

    @bp.get('/api/agent/sessions/<public_id>/snapshot')
    def agent_session_snapshot(public_id):
        user = admin()
        row = session_row(public_id, user['id'])
        remote_id = row['remote_id']
        with ThreadPoolExecutor(max_workers=7) as pool:
            tasks = {
                'session': pool.submit(engine, 'GET', f'/session/{remote_id}', timeout=8, directory=row['workspace']),
                'messages': pool.submit(engine, 'GET', f'/session/{remote_id}/message', timeout=12, directory=row['workspace']),
                'todos': pool.submit(lambda: optional(f'/session/{remote_id}/todo', [], row['workspace'])),
                'diff': pool.submit(lambda: optional(f'/session/{remote_id}/diff', [], row['workspace'])),
                'statuses': pool.submit(optional, '/session/status', {}, row['workspace']),
                'permissions': pool.submit(pending_for, remote_id, '/permission', row['workspace']),
                'questions': pool.submit(pending_for, remote_id, '/question', row['workspace']),
            }
            values = {key: future.result() for key, future in tasks.items()}
        values['permissions'] = apply_automatic_permissions(remote_id, row['workspace'], approval_mode(row.get('approval_mode')), values['permissions'])
        state = values['statuses'].get(remote_id) if isinstance(values['statuses'], dict) else None
        messages = values['messages'] if isinstance(values['messages'], list) else []
        context = context_usage(messages, row['model'], row['workspace'])
        status = derived_status(row, state, permissions=values['permissions'], questions=values['questions'], messages=messages)
        remote_session = values['session'] if isinstance(values['session'], dict) else {}
        title = str(remote_session.get('title') or row['title'])[:100]
        stamp = now()
        updated_at = stamp if status in {'running', 'waiting'} or status != row['status'] else row['updated_at']
        with db() as conn:
            conn.execute('UPDATE agent_sessions SET title=?,status=?,updated_at=?,last_seen_at=? WHERE id=?',
                         (title, status, updated_at, stamp, public_id))
        change_groups = tool_change_groups(messages, row['workspace'])
        session_diff = values['diff'] if isinstance(values['diff'], list) else []
        if not session_diff:
            session_diff = [item for group in change_groups for item in group['diff']]
        return jsonify({
            'session': {'id': public_id, 'title': title, 'model': row['model'], 'agent_mode': row['agent_mode'], 'approval_mode': approval_mode(row.get('approval_mode')), 'status': status,
                        'workspace': workspace_label(row['workspace']), 'workspace_value': workspace_value(row['workspace']),
                        'created_at': row['created_at'], 'updated_at': updated_at},
            'messages': messages,
            'todos': values['todos'] if isinstance(values['todos'], list) else [],
            'diff': session_diff,
            'change_groups': change_groups,
            'permissions': values['permissions'],
            'questions': values['questions'],
            'context': context,
        })

    @bp.post('/api/agent/sessions/<public_id>/prompt')
    def agent_session_prompt(public_id):
        user = admin()
        row = session_row(public_id, user['id'])
        data = request.get_json(silent=True) or {}
        text = str(data.get('message') or '').strip()
        model = str(data.get('model') or '').strip()
        mode = str(data.get('agent') or row['agent_mode'] or 'build')
        permission_mode = approval_mode(str(data.get('approval_mode') or row.get('approval_mode') or 'ask'))
        if not text:
            return jsonify({'error': 'Message is required'}), 400
        if len(text) > 100000:
            return jsonify({'error': 'Message is too long'}), 400
        if mode not in ('build', 'plan'):
            return jsonify({'error': 'Unknown agent mode'}), 400
        options = {item['value']: item for item in installed_models()}
        selected = options.get(model) or options.get(f'ollama:{model}')
        if not selected:
            return jsonify({'error': 'Select an available Agent model'}), 400
        provider_id, model_id = selected['provider'], selected['name']
        model_value = selected['value']
        body = {'agent': mode, 'model': {'providerID': provider_id, 'modelID': model_id}, 'parts': [{'type': 'text', 'text': text}]}
        engine('POST', f"/session/{row['remote_id']}/prompt_async", body=body, timeout=15, directory=row['workspace'])
        stamp = now()
        title = row['title']
        if title == 'New agent task':
            title = ' '.join(text.split())[:72] or title
            try:
                engine('PATCH', f"/session/{row['remote_id']}", body={'title': title}, timeout=6, directory=row['workspace'])
            except AgentEngineError:
                pass
        with db() as conn:
            conn.execute('UPDATE agent_sessions SET title=?,model=?,agent_mode=?,approval_mode=?,status=?,updated_at=?,last_seen_at=? WHERE id=?',
                         (title, model_value, mode, permission_mode, 'running', stamp, stamp, public_id))
        return jsonify({'accepted': True, 'id': public_id, 'title': title, 'status': 'running'})

    @bp.post('/api/agent/sessions/<public_id>/abort')
    def agent_session_abort(public_id):
        user = admin()
        row = session_row(public_id, user['id'])
        result = engine('POST', f"/session/{row['remote_id']}/abort", timeout=10, directory=row['workspace'])
        with db() as conn:
            conn.execute('UPDATE agent_sessions SET status=?,updated_at=? WHERE id=?', ('stopped', now(), public_id))
        return jsonify({'success': bool(result is None or result)})

    @bp.post('/api/agent/permissions/<permission_id>')
    def agent_permission_reply(permission_id):
        user = admin()
        data = request.get_json(silent=True) or {}
        reply = str(data.get('reply') or '')
        if reply not in ('once', 'always', 'reject'):
            return jsonify({'error': 'Invalid permission response'}), 400
        target, owner = owned_pending(permission_id, '/permission', user['id'])
        if not target:
            return jsonify({'error': 'Permission request is no longer pending'}), 404
        engine('POST', f'/permission/{permission_id}/reply', body={'reply': reply}, timeout=10, directory=owner['workspace'])
        return jsonify({'success': True})

    @bp.post('/api/agent/questions/<question_id>/reply')
    def agent_question_reply(question_id):
        user = admin()
        data = request.get_json(silent=True) or {}
        answers = data.get('answers')
        if not isinstance(answers, list) or any(not isinstance(answer, list) for answer in answers):
            return jsonify({'error': 'Answers must be a list of selections'}), 400
        target, owner = owned_pending(question_id, '/question', user['id'])
        if not target:
            return jsonify({'error': 'Question is no longer pending'}), 404
        engine('POST', f'/question/{question_id}/reply', body={'answers': answers}, timeout=10, directory=owner['workspace'])
        return jsonify({'success': True})

    @bp.post('/api/agent/questions/<question_id>/reject')
    def agent_question_reject(question_id):
        user = admin()
        target, owner = owned_pending(question_id, '/question', user['id'])
        if not target:
            return jsonify({'error': 'Question is no longer pending'}), 404
        engine('POST', f'/question/{question_id}/reject', timeout=10, directory=owner['workspace'])
        return jsonify({'success': True})

    return bp
