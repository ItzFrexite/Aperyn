#!/usr/bin/env python3
"""Transparent Ollama-compatible proxy for Aperyn.

This process listens on a dedicated port (11435 by default), forwards normal
Ollama and OpenAI-compatible API paths to the configured Ollama server, and
feeds request/live-generation telemetry into the shared manager database.
"""

import json
import os
import time
import hmac
from urllib.parse import urljoin

import requests
from flask import Flask, Response, jsonify, request

import app as core

proxy_app = Flask(__name__)
DEFAULT_OLLAMA_API = os.environ.get('OLLAMA_API', 'http://127.0.0.1:11434').rstrip('/')

def _ollama_api():
    configured = core._configured_upstream()
    return configured or DEFAULT_OLLAMA_API
PROXY_LISTEN_PORT = int(os.environ.get('PROXY_LISTEN_PORT', '11435'))
HELPER_TOKEN = os.environ.get('OLLAMA_CONTROL_HELPER_TOKEN', '')
HELPER_URL = os.environ.get('OLLAMA_CONTROL_HELPER_URL', 'http://127.0.0.1:11436').rstrip('/')

HOP_BY_HOP = {
    'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
    'te', 'trailers', 'transfer-encoding', 'upgrade', 'host',
}
TRACKED_NATIVE = {'api/generate', 'api/chat'}
TRACKED_OPENAI = {'v1/chat/completions', 'v1/completions', 'v1/responses'}


def _clean_request_headers():
    return {k: v for k, v in request.headers if k.lower() not in HOP_BY_HOP | {'content-length'}}


def _clean_response_headers(upstream, streaming=False):
    blocked = HOP_BY_HOP | {'content-length', 'content-type'}
    # requests transparently decompresses encoded bodies while streaming, so
    # never forward the original encoding header with a decoded body.
    blocked.add('content-encoding')
    headers = [(k, v) for k, v in upstream.headers.items() if k.lower() not in blocked]
    if streaming:
        headers.append(('X-Ollama-Control-Telemetry', 'tracked'))
    return headers


def _extract_model(payload):
    return payload.get('model') if isinstance(payload, dict) else None


def _track_kind(subpath):
    clean = subpath.strip('/')
    if clean in TRACKED_NATIVE:
        return 'native'
    if clean in TRACKED_OPENAI:
        return 'openai'
    return None



def _effective_telemetry_mtp(model, payload, kind):
    pref = core._model_pref(model) if model else None
    if kind == 'native' and isinstance(payload, dict):
        options = payload.get('options')
        if isinstance(options, dict) and 'draft_num_predict' in options:
            try:
                depth = int(options.get('draft_num_predict') or 0)
            except (TypeError, ValueError):
                depth = 0
            return {
                'model': model,
                'mtp_enabled': depth > 0,
                'mtp_draft_n_max': depth if depth > 0 else 0,
                'source': 'request',
            }
    return pref

def _openai_text(obj):
    if not isinstance(obj, dict):
        return ''
    pieces = []
    for choice in obj.get('choices') or []:
        if not isinstance(choice, dict):
            continue
        delta = choice.get('delta') or {}
        message = choice.get('message') or {}
        if isinstance(delta, dict):
            pieces.append(str(delta.get('content') or ''))
        if isinstance(message, dict):
            pieces.append(str(message.get('content') or ''))
        pieces.append(str(choice.get('text') or ''))
    output = obj.get('output')
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get('content') or []
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        pieces.append(str(part.get('text') or part.get('content') or ''))
    return ''.join(pieces)


def _openai_final_metrics(obj):
    if not isinstance(obj, dict):
        return {}
    usage = obj.get('usage') or {}
    if not isinstance(usage, dict):
        return {}
    prompt = usage.get('prompt_tokens', usage.get('input_tokens', 0)) or 0
    output = usage.get('completion_tokens', usage.get('output_tokens', 0)) or 0
    try:
        prompt = int(prompt)
    except (TypeError, ValueError):
        prompt = 0
    try:
        output = int(output)
    except (TypeError, ValueError):
        output = 0
    return {'prompt_eval_count': prompt, 'eval_count': output, 'eval_duration': 0}


def _parse_tracking_line(kind, line, live_id, final):
    text = line.decode('utf-8', errors='ignore').strip()
    if not text:
        return
    if kind == 'native':
        try:
            obj = json.loads(text)
        except Exception:
            return
        core._update_live_generation(live_id, obj)
        if obj.get('done'):
            final.update(obj)
        return

    # Ollama's OpenAI-compatible streaming endpoints use SSE data lines.
    if text.startswith('data:'):
        text = text[5:].strip()
    if text == '[DONE]':
        return
    try:
        obj = json.loads(text)
    except Exception:
        return
    chunk_text = _openai_text(obj)
    if chunk_text:
        core._update_live_generation(live_id, {'response': chunk_text, 'done': False})
    metrics = _openai_final_metrics(obj)
    if metrics.get('prompt_eval_count') or metrics.get('eval_count'):
        final.update(metrics)


@proxy_app.get('/__ollama_control/ping')
def proxy_ping():
    return jsonify({'status': 'ok', 'proxy': True, 'upstream': _ollama_api()})


@proxy_app.get('/__ollama_control/health')
def proxy_health():
    try:
        upstream_url = _ollama_api()
        response = requests.get(f'{upstream_url}/api/version', timeout=2)
        response.raise_for_status()
        return jsonify({'status': 'healthy', 'ollama': True, 'upstream': upstream_url, 'configured': bool(core._configured_upstream())})
    except Exception as exc:
        return jsonify({'status': 'degraded', 'ollama': False, 'upstream': _ollama_api(), 'error': str(exc)}), 503


@proxy_app.route('/__ollama_control/helper/<path:subpath>', methods=['GET','POST'])
def proxy_helper_relay(subpath):
    supplied=request.headers.get('X-Ollama-Control-Helper-Token','')
    if not HELPER_TOKEN or not hmac.compare_digest(supplied, HELPER_TOKEN):
        return jsonify({'error':'performance helper is not configured'}), 403
    try:
        payload=request.get_json(silent=True) if request.method=='POST' else None
        r=requests.request(request.method, f"{HELPER_URL}/v1/{subpath.strip('/')}", json=payload, headers={'Authorization':f'Bearer {HELPER_TOKEN}'}, timeout=60)
        try: data=r.json()
        except Exception: data={'error':r.text or f'helper returned {r.status_code}'}
        return jsonify(data), r.status_code
    except Exception as exc:
        return jsonify({'error':str(exc),'helper_url':HELPER_URL}), 503


@proxy_app.get('/__ollama_control/helper-state')
def proxy_helper_state():
    """Classify the localhost helper without exposing its token or capabilities."""
    try:
        ping = requests.get(f'{HELPER_URL}/v1/ping', timeout=2)
        ping.raise_for_status()
    except Exception as exc:
        state = 'installed_but_stopped' if HELPER_TOKEN else 'not_installed'
        return jsonify({'state': state, 'connected': False, 'detail': str(exc)}), 503
    if not HELPER_TOKEN:
        return jsonify({'state': 'authentication_mismatch', 'connected': False}), 409
    try:
        check = requests.get(f'{HELPER_URL}/v1/status', headers={'Authorization':f'Bearer {HELPER_TOKEN}'}, timeout=3)
        if check.status_code in (401, 403):
            return jsonify({'state': 'authentication_mismatch', 'connected': False}), 409
        check.raise_for_status()
        data = check.json()
        return jsonify({'state': 'connected', 'connected': True, 'service_state': data.get('service_state')})
    except Exception as exc:
        return jsonify({'state': 'unreachable', 'connected': False, 'detail': str(exc)}), 503


@proxy_app.get('/__ollama_control/live')
def proxy_live():
    now_perf = time.perf_counter()
    with core._live_lock:
        active = [core._live_snapshot(dict(entry), now_perf) for entry in core._active_generations.values()]
        recent = [dict(entry) for entry in list(core._recent_generations)[:8]]
    active.sort(key=lambda x: x.get('started_at') or '')
    return jsonify({'active': active, 'recent': recent})


@proxy_app.post('/__ollama_control/live/clear')
def proxy_clear_live_history():
    supplied = request.headers.get('X-Aperyn-Internal-Token', '')
    expected = core._telemetry_clear_identity()
    if not expected or not hmac.compare_digest(supplied, expected):
        return jsonify({'error': 'private telemetry identity mismatch'}), 403
    with core._live_lock:
        cleared = len(core._recent_generations)
        core._recent_generations.clear()
    return jsonify({'cleared': True, 'cleared_recent': cleared, 'active_generations_preserved': True})


@proxy_app.route('/', defaults={'subpath': ''}, methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD'])
@proxy_app.route('/<path:subpath>', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD'])
def transparent_proxy(subpath):
    upstream_url = _ollama_api()
    target = f"{upstream_url}/{subpath}" if subpath else f"{upstream_url}/"
    kind = _track_kind(subpath)
    content_type = request.headers.get('Content-Type', '')
    payload = request.get_json(silent=True) if 'json' in content_type.lower() else None
    model = _extract_model(payload or {})
    request_meta = core._request_meta_from_payload(payload or {}) if kind else None
    if kind == 'native' and isinstance(payload, dict):
        is_generate_lifecycle = subpath.strip('/') == 'api/generate' and not str(payload.get('prompt') or '')
        is_chat_lifecycle = subpath.strip('/') == 'api/chat' and payload.get('messages') == []
        if is_generate_lifecycle or is_chat_lifecycle:
            kind = None
    mtp_pref = _effective_telemetry_mtp(model, payload, kind)

    # Do not rewrite generation options here. Model defaults (including
    # draft_num_predict/MTP and num_ctx) are persisted in Ollama by the manager.
    # Keeping this listener transparent also means an API caller can override a
    # model default naturally using Ollama's normal request options.

    headers = _clean_request_headers()
    if payload is not None:
        body = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    elif request.method in {'POST', 'PUT', 'PATCH'} and request.content_length:
        # Stream large binary requests (notably /api/blobs uploads) instead of
        # buffering multi-gigabyte GGUF files in the proxy container's memory.
        body = request.stream
        headers['Content-Length'] = str(request.content_length)
    else:
        body = request.get_data(cache=False)

    start = time.perf_counter()
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    live_id = core._start_live_generation(model, '/' + subpath.strip('/'), mtp_pref) if kind else None

    try:
        upstream = requests.request(
            request.method,
            target,
            params=request.args,
            data=body,
            headers=headers,
            stream=True,
            timeout=3600,
            allow_redirects=False,
        )
    except Exception as exc:
        if kind:
            latency_ms = (time.perf_counter() - start) * 1000
            core._log_request('/' + subpath.strip('/'), model, 502, latency_ms, {}, client_ip, request_meta)
            core._finish_live_generation(live_id, 502, {}, exc)
        return jsonify({'error': str(exc)}), 502

    response_headers = _clean_response_headers(upstream, streaming=bool(kind))
    upstream_type = upstream.headers.get('Content-Type', 'application/octet-stream')

    if not kind:
        def raw_stream():
            try:
                for chunk in upstream.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        yield chunk
            finally:
                upstream.close()
        return Response(raw_stream(), status=upstream.status_code, headers=response_headers, content_type=upstream_type)

    def tracked_stream():
        final = {}
        stream_error = None
        try:
            for line in upstream.iter_lines():
                if line is None:
                    continue
                if line:
                    _parse_tracking_line(kind, line, live_id, final)
                # Preserve NDJSON/SSE line framing. Empty SSE lines are also
                # forwarded so OpenAI-compatible clients keep event boundaries.
                yield line + b'\n'
        except Exception as exc:
            stream_error = exc
            raise
        finally:
            latency_ms = (time.perf_counter() - start) * 1000
            core._log_request('/' + subpath.strip('/'), model, upstream.status_code, latency_ms, final, client_ip, request_meta)
            core._finish_live_generation(live_id, upstream.status_code, final, stream_error)
            upstream.close()

    return Response(tracked_stream(), status=upstream.status_code, headers=response_headers, content_type=upstream_type)


if __name__ == '__main__':
    proxy_app.run(host='0.0.0.0', port=PROXY_LISTEN_PORT, debug=False, threaded=True)
