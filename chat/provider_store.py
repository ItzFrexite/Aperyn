"""Persistent, encrypted external inference connections for Aperyn.

Provider credentials are encrypted in SQLite with a Fernet key generated under
the persistent data directory.  The browser only receives masked summaries.
The private Agent runtime gets provider keys through root-owned runtime files;
no credential is written to source, Compose, logs, or API responses.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import time

from cryptography.fernet import Fernet, InvalidToken
import requests


PROVIDERS = {
    'openai': {
        'name': 'OpenAI',
        'base_url': 'https://api.openai.com/v1',
        'model_path': '/models',
        'npm': '@ai-sdk/openai',
    },
    'anthropic': {
        'name': 'Anthropic',
        'base_url': 'https://api.anthropic.com/v1',
        'model_path': '/models',
        'npm': '@ai-sdk/anthropic',
    },
    'google': {
        'name': 'Google Gemini',
        'base_url': 'https://generativelanguage.googleapis.com/v1beta',
        'model_path': '/models',
        'npm': '@ai-sdk/google',
    },
}


class ProviderError(RuntimeError):
    pass


class ProviderStore:
    def __init__(self, database_path, data_dir=None):
        self.database_path = database_path
        self.data_dir = Path(data_dir or Path(database_path).parent)
        self.key_path = self.data_dir / 'provider-secrets.key'
        self.agent_dir = self.data_dir / 'agent'
        self.agent_uid = int(os.environ.get('APERYN_AGENT_UID', '1000'))
        self.agent_gid = int(os.environ.get('APERYN_AGENT_GID', '1000'))
        self._ensure()

    def db(self):
        conn = sqlite3.connect(self.database_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA busy_timeout=30000')
        return conn

    def _ensure(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.key_path.exists():
            temporary = self.key_path.with_suffix('.tmp')
            temporary.write_bytes(Fernet.generate_key())
            os.chmod(temporary, 0o600)
            temporary.replace(self.key_path)
        os.chmod(self.key_path, 0o600)
        with self.db() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS provider_connections (
                provider TEXT PRIMARY KEY,
                encrypted_api_key TEXT NOT NULL,
                models_json TEXT NOT NULL DEFAULT '[]',
                enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""")

    @property
    def cipher(self):
        return Fernet(self.key_path.read_bytes().strip())

    @staticmethod
    def validate_provider(provider):
        provider = str(provider or '').strip().lower()
        if provider not in PROVIDERS:
            raise ProviderError('Unsupported provider')
        return provider

    @staticmethod
    def clean_models(models):
        if isinstance(models, str):
            models = [part.strip() for part in models.replace('\r', '\n').replace(',', '\n').split('\n')]
        if not isinstance(models, list):
            raise ProviderError('Models must be a list or comma-separated text')
        result = []
        for value in models:
            model = str(value or '').strip()
            if not model:
                continue
            if len(model) > 180 or any(ch.isspace() for ch in model):
                raise ProviderError('Model IDs cannot contain spaces and must be 180 characters or fewer')
            if model not in result:
                result.append(model)
        if len(result) > 100:
            raise ProviderError('A provider can contain at most 100 model IDs')
        return result

    def _decrypt(self, encrypted):
        try:
            return self.cipher.decrypt(str(encrypted).encode('ascii')).decode('utf-8')
        except (InvalidToken, ValueError, UnicodeError) as exc:
            raise ProviderError('Stored provider credential could not be decrypted') from exc

    def connection(self, provider, require=True):
        provider = self.validate_provider(provider)
        with self.db() as conn:
            row = conn.execute('SELECT * FROM provider_connections WHERE provider=? AND enabled=1', (provider,)).fetchone()
        if not row:
            if require:
                raise ProviderError(f'{PROVIDERS[provider]["name"]} is not connected')
            return None
        value = dict(row)
        value['api_key'] = self._decrypt(value.pop('encrypted_api_key'))
        try:
            value['models'] = self.clean_models(json.loads(value.pop('models_json')))
        except (ValueError, TypeError, ProviderError):
            value['models'] = []
        value.update(PROVIDERS[provider])
        return value

    def summaries(self):
        with self.db() as conn:
            rows = {row['provider']: dict(row) for row in conn.execute('SELECT * FROM provider_connections')}
        result = []
        for provider, spec in PROVIDERS.items():
            row = rows.get(provider)
            models = []
            if row:
                try:
                    models = self.clean_models(json.loads(row['models_json']))
                except (ValueError, TypeError, ProviderError):
                    pass
            result.append({
                'id': provider,
                'name': spec['name'],
                'connected': bool(row and row.get('enabled')),
                'has_api_key': bool(row and row.get('encrypted_api_key')),
                'api_key_mask': '••••••••' if row and row.get('encrypted_api_key') else '',
                'models': models,
                'updated_at': row.get('updated_at') if row else None,
            })
        return result

    def save(self, provider, api_key, models):
        provider = self.validate_provider(provider)
        models = self.clean_models(models)
        api_key = str(api_key or '').strip()
        existing = self.connection(provider, require=False)
        if not api_key and existing:
            api_key = existing['api_key']
        if not api_key:
            raise ProviderError('API key is required')
        if len(api_key) > 4096 or any(ch in api_key for ch in '\r\n\0'):
            raise ProviderError('API key format is invalid')
        if not models:
            raise ProviderError('Enter at least one model ID')
        encrypted = self.cipher.encrypt(api_key.encode('utf-8')).decode('ascii')
        stamp = datetime.now(timezone.utc).isoformat()
        with self.db() as conn:
            conn.execute("""INSERT INTO provider_connections(provider,encrypted_api_key,models_json,enabled,created_at,updated_at)
                            VALUES(?,?,?,?,?,?) ON CONFLICT(provider) DO UPDATE SET
                            encrypted_api_key=excluded.encrypted_api_key,models_json=excluded.models_json,
                            enabled=1,updated_at=excluded.updated_at""",
                         (provider, encrypted, json.dumps(models), 1, stamp, stamp))
        self.write_agent_runtime()
        return next(item for item in self.summaries() if item['id'] == provider)

    def delete(self, provider):
        provider = self.validate_provider(provider)
        with self.db() as conn:
            conn.execute('DELETE FROM provider_connections WHERE provider=?', (provider,))
        self.write_agent_runtime()

    def headers(self, provider, key):
        if provider == 'openai':
            return {'Authorization': f'Bearer {key}'}
        if provider == 'anthropic':
            return {'x-api-key': key, 'anthropic-version': '2023-06-01'}
        return {}

    def discover_models(self, provider, api_key=None):
        provider = self.validate_provider(provider)
        key = str(api_key or '').strip() or self.connection(provider)['api_key']
        spec = PROVIDERS[provider]
        params = {'key': key} if provider == 'google' else None
        response = requests.get(spec['base_url'] + spec['model_path'], headers=self.headers(provider, key), params=params, timeout=(5, 25))
        if not response.ok:
            raise ProviderError(f'{spec["name"]} rejected the connection (HTTP {response.status_code})')
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError(f'{spec["name"]} returned an invalid response') from exc
        rows = payload.get('data') if provider in ('openai', 'anthropic') else payload.get('models')
        result = []
        for row in rows or []:
            model = str((row or {}).get('id') or (row or {}).get('name') or '').strip()
            if provider == 'google' and model.startswith('models/'):
                model = model[7:]
            if model and model not in result:
                result.append(model)
        return result[:250]

    def model_options(self, include_ollama=None):
        result = list(include_ollama or [])
        for summary in self.summaries():
            if not summary['connected']:
                continue
            result.extend({'provider': summary['id'], 'provider_name': summary['name'], 'name': model, 'value': f"{summary['id']}:{model}"} for model in summary['models'])
        return result

    @staticmethod
    def _text_messages(messages):
        result = []
        for message in messages[-120:]:
            role = str(message.get('role') or 'user')
            if role not in ('system', 'user', 'assistant'):
                role = 'user'
            content = str(message.get('content') or '')
            if content:
                result.append({'role': role, 'content': content})
        return result

    def stream_chat(self, provider, model, messages):
        """Yield Ollama-shaped streaming objects for the existing Chat frontend."""
        connection = self.connection(provider)
        if model not in connection['models']:
            raise ProviderError('That model is not enabled for this provider')
        started = time.perf_counter_ns()
        text_messages = self._text_messages(messages)
        if provider == 'openai':
            yield from self._stream_openai(connection, model, text_messages, started)
        elif provider == 'anthropic':
            yield from self._stream_anthropic(connection, model, text_messages, started)
        else:
            yield from self._stream_google(connection, model, text_messages, started)

    @staticmethod
    def _sse(response):
        for raw in response.iter_lines(decode_unicode=True):
            line = str(raw or '').strip()
            if not line.startswith('data:'):
                continue
            data = line[5:].strip()
            if data and data != '[DONE]':
                try:
                    yield json.loads(data)
                except ValueError:
                    continue

    def _stream_openai(self, connection, model, messages, started):
        response = requests.post(connection['base_url'] + '/responses', headers={**self.headers('openai', connection['api_key']), 'Content-Type': 'application/json'},
                                 json={'model': model, 'input': messages, 'stream': True}, stream=True, timeout=(10, 3600))
        if not response.ok:
            raise ProviderError(f'OpenAI rejected the request (HTTP {response.status_code})')
        output_tokens = 0
        try:
            for event in self._sse(response):
                kind = event.get('type')
                if kind == 'response.output_text.delta' and event.get('delta'):
                    yield {'message': {'role': 'assistant', 'content': event['delta']}, 'done': False}
                elif kind in ('response.reasoning_summary_text.delta', 'response.reasoning_text.delta') and event.get('delta'):
                    yield {'message': {'role': 'assistant', 'thinking': event['delta']}, 'done': False}
                elif kind == 'response.completed':
                    usage = (event.get('response') or {}).get('usage') or {}
                    output_tokens = int(usage.get('output_tokens') or 0)
        finally:
            response.close()
        yield {'message': {'role': 'assistant', 'content': ''}, 'done': True, 'eval_count': output_tokens,
               'eval_duration': max(1, time.perf_counter_ns() - started)}

    def _stream_anthropic(self, connection, model, messages, started):
        system = '\n\n'.join(item['content'] for item in messages if item['role'] == 'system')
        body = {'model': model, 'max_tokens': 8192, 'stream': True,
                'messages': [item for item in messages if item['role'] in ('user', 'assistant')]}
        if system:
            body['system'] = system
        response = requests.post(connection['base_url'] + '/messages', headers={**self.headers('anthropic', connection['api_key']), 'Content-Type': 'application/json'},
                                 json=body, stream=True, timeout=(10, 3600))
        if not response.ok:
            raise ProviderError(f'Anthropic rejected the request (HTTP {response.status_code})')
        output_tokens = 0
        try:
            for event in self._sse(response):
                if event.get('type') == 'content_block_delta':
                    delta = event.get('delta') or {}
                    if delta.get('type') == 'text_delta' and delta.get('text'):
                        yield {'message': {'role': 'assistant', 'content': delta['text']}, 'done': False}
                    elif delta.get('type') in ('thinking_delta', 'signature_delta') and delta.get('thinking'):
                        yield {'message': {'role': 'assistant', 'thinking': delta['thinking']}, 'done': False}
                elif event.get('type') == 'message_delta':
                    output_tokens = int((event.get('usage') or {}).get('output_tokens') or output_tokens)
        finally:
            response.close()
        yield {'message': {'role': 'assistant', 'content': ''}, 'done': True, 'eval_count': output_tokens,
               'eval_duration': max(1, time.perf_counter_ns() - started)}

    def _stream_google(self, connection, model, messages, started):
        contents = []
        system = []
        for item in messages:
            if item['role'] == 'system':
                system.append(item['content'])
            else:
                contents.append({'role': 'model' if item['role'] == 'assistant' else 'user', 'parts': [{'text': item['content']}]})
        body = {'contents': contents}
        if system:
            body['systemInstruction'] = {'parts': [{'text': '\n\n'.join(system)}]}
        endpoint = f"{connection['base_url']}/models/{model}:streamGenerateContent"
        response = requests.post(endpoint, params={'alt': 'sse', 'key': connection['api_key']}, json=body, stream=True, timeout=(10, 3600))
        if not response.ok:
            raise ProviderError(f'Google Gemini rejected the request (HTTP {response.status_code})')
        output_tokens = 0
        try:
            for event in self._sse(response):
                usage = event.get('usageMetadata') or {}
                output_tokens = int(usage.get('candidatesTokenCount') or output_tokens)
                for candidate in event.get('candidates') or []:
                    for part in ((candidate.get('content') or {}).get('parts') or []):
                        if part.get('text'):
                            yield {'message': {'role': 'assistant', 'content': part['text']}, 'done': False}
        finally:
            response.close()
        yield {'message': {'role': 'assistant', 'content': ''}, 'done': True, 'eval_count': output_tokens,
               'eval_duration': max(1, time.perf_counter_ns() - started)}

    def write_agent_runtime(self):
        """Write a runtime-only OpenCode provider fragment and separate key files."""
        provider_dir = self.agent_dir / 'providers'
        provider_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(provider_dir, 0o700)
        os.chown(provider_dir, self.agent_uid, self.agent_gid)
        configured = {}
        active = set()
        for provider in PROVIDERS:
            connection = self.connection(provider, require=False)
            if not connection:
                continue
            active.add(provider)
            key_path = provider_dir / f'{provider}.key'
            key_path.write_text(connection['api_key'], encoding='utf-8')
            os.chmod(key_path, 0o600)
            os.chown(key_path, self.agent_uid, self.agent_gid)
            configured[provider] = {
                'npm': connection['npm'],
                'name': connection['name'],
                'options': {'apiKey': f'{{file:/agent-data/providers/{provider}.key}}'},
                'models': {model: {'name': model} for model in connection['models']},
            }
        for key_path in provider_dir.glob('*.key'):
            if key_path.stem not in active:
                key_path.unlink(missing_ok=True)
        fragment = self.agent_dir / 'provider-connections.json'
        temporary = fragment.with_suffix('.tmp')
        temporary.write_text(json.dumps({'provider': configured}, indent=2), encoding='utf-8')
        os.chmod(temporary, 0o600)
        os.chown(temporary, self.agent_uid, self.agent_gid)
        temporary.replace(fragment)
        # OpenCode watches its active configuration. Merge the same fragment
        # immediately when the Agent has already started; entrypoint.sh repeats
        # this merge on every container start.
        active_config = self.agent_dir / 'opencode.json'
        if active_config.exists():
            try:
                payload = json.loads(active_config.read_text(encoding='utf-8'))
                providers = payload.get('provider') if isinstance(payload.get('provider'), dict) else {}
                for provider in PROVIDERS:
                    providers.pop(provider, None)
                providers.update(configured)
                payload['provider'] = providers
                active_temporary = active_config.with_suffix('.providers.tmp')
                active_temporary.write_text(json.dumps(payload, indent=2), encoding='utf-8')
                os.chmod(active_temporary, 0o600)
                os.chown(active_temporary, self.agent_uid, self.agent_gid)
                active_temporary.replace(active_config)
            except (OSError, ValueError, TypeError):
                pass
