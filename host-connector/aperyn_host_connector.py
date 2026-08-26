#!/usr/bin/env python3
"""Outbound connector for a remotely managed Aperyn Ollama host.

The connector never listens on the network.  It polls the authenticated Aperyn
server, reads only the local loopback helper/Ollama APIs, and accepts three
fixed operations: helper status, GPU snapshot, and allow-listed helper apply.
"""
import argparse
import ipaddress
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.error import HTTPError
from urllib.request import Request, urlopen

DEFAULT_CONFIG = '/etc/aperyn-host-connector/config.json'


def http_json(url, method='GET', payload=None, headers=None, timeout=20):
    body = json.dumps(payload).encode('utf-8') if payload is not None else None
    request = Request(url, data=body, method=method, headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode('utf-8')
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode('utf-8', errors='replace')
        try:
            detail = json.loads(raw).get('error') or raw
        except Exception:
            detail = raw
        raise RuntimeError(detail or f'HTTP {exc.code}') from exc


def private_http_url(url):
    parsed = urlparse(url)
    if parsed.scheme != 'http' or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if host == 'localhost' or host.endswith('.ts.net'):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private or address in ipaddress.ip_network('100.64.0.0/10')


def read_config(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    for key in ('server_url', 'host_id', 'connector_token'):
        if not str(data.get(key) or '').strip():
            raise RuntimeError(f'Missing {key} in connector config')
    url = str(data['server_url']).rstrip('/')
    if not (url.startswith('https://') or private_http_url(url)):
        raise RuntimeError('Aperyn server URL must use HTTPS, unless HTTP is a private LAN or Tailscale address.')
    data['server_url'] = url
    data.setdefault('helper_url', 'http://127.0.0.1:11436')
    data.setdefault('helper_token_file', '/var/lib/ollama-control/helper.token')
    data.setdefault('ollama_url', 'http://127.0.0.1:11434')
    return data


def helper_headers(config):
    token = Path(config['helper_token_file']).read_text(encoding='utf-8').strip()
    return {'Authorization': f'Bearer {token}'}


def helper_get(config, path):
    try:
        return http_json(f"{config['helper_url'].rstrip('/')}/v1/{path}", headers=helper_headers(config), timeout=6)
    except Exception as exc:
        return {'error': str(exc)}


def snapshot(config):
    helper = helper_get(config, 'status')
    gpu = helper_get(config, 'gpu')
    ollama = {'reachable': False}
    try:
        data = http_json(f"{config['ollama_url'].rstrip('/')}/api/version", timeout=5)
        ollama = {'reachable': True, 'version': data.get('version')}
    except Exception as exc:
        ollama['error'] = str(exc)
    mem = {}
    try:
        for line in Path('/proc/meminfo').read_text(encoding='utf-8').splitlines():
            key, value = line.split(':', 1)
            mem[key] = int(value.strip().split()[0]) * 1024
    except Exception:
        pass
    return {'helper': helper, 'gpu': gpu, 'ollama': ollama,
            'system': {'total_bytes': int(mem.get('MemTotal') or 0), 'available_bytes': int(mem.get('MemAvailable') or mem.get('MemFree') or 0), 'cpu_count': os.cpu_count() or 0},
            'connector_version': '1.27.1'}


def run_action(config, action):
    op = action.get('operation')
    if op == 'helper.status':
        return True, helper_get(config, 'status')
    if op == 'helper.gpu':
        return True, helper_get(config, 'gpu')
    if op == 'helper.apply':
        payload = action.get('payload') or {}
        if not isinstance(payload, dict) or set(payload) - {'settings', 'clear_mtp_globals'}:
            return False, {'error': 'Invalid helper apply payload'}
        try:
            return True, http_json(f"{config['helper_url'].rstrip('/')}/v1/apply", method='POST', payload=payload, headers=helper_headers(config), timeout=70)
        except Exception as exc:
            return False, {'error': str(exc)}
    return False, {'error': 'Unsupported connector operation'}


def connector_headers(config):
    return {'Authorization': f"Bearer {config['connector_token']}", 'X-Aperyn-Host-ID': config['host_id']}


def pair(args):
    server = args.server_url.rstrip('/')
    if not (server.startswith('https://') or private_http_url(server)):
        raise SystemExit('Use HTTPS, unless the HTTP Aperyn URL is a private LAN or Tailscale address.')
    try:
        data = http_json(f'{server}/api/host-connector/register', method='POST', payload={'host_id': args.host_id, 'pairing_token': args.pairing_token}, timeout=20)
    except Exception as exc:
        raise SystemExit(f'Pairing failed: {exc}') from exc
    target = Path(args.config)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({'server_url': server, 'host_id': args.host_id, 'connector_token': data['connector_token']}, indent=2) + '\n', encoding='utf-8')
    os.chmod(target, 0o600)
    print(f'Paired host connector configuration written to {target}')


def serve(args):
    config = read_config(args.config)
    delay = 2
    while True:
        try:
            response = http_json(f"{config['server_url']}/api/host-connector/poll", method='POST', payload={'snapshot': snapshot(config)}, headers=connector_headers(config), timeout=25) or {}
            delay = max(1, min(10, int(response.get('poll_seconds') or 2)))
            action = response.get('action')
            if action:
                ok, result = run_action(config, action)
                http_json(f"{config['server_url']}/api/host-connector/actions/{action['id']}/result", method='POST', payload={'ok': ok, 'result': result}, headers=connector_headers(config), timeout=25)
                delay = 1
        except KeyboardInterrupt:
            return
        except Exception:
            delay = min(30, max(2, delay * 2))
        time.sleep(delay)


def main():
    parser = argparse.ArgumentParser(description='Aperyn outbound remote-host connector')
    parser.add_argument('--config', default=DEFAULT_CONFIG)
    sub = parser.add_subparsers(dest='command', required=True)
    pair_cmd = sub.add_parser('pair')
    pair_cmd.add_argument('--server-url', required=True)
    pair_cmd.add_argument('--host-id', required=True)
    pair_cmd.add_argument('--pairing-token', required=True)
    sub.add_parser('serve')
    args = parser.parse_args()
    pair(args) if args.command == 'pair' else serve(args)


if __name__ == '__main__':
    main()
