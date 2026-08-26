import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'chat'))
from provider_store import ProviderStore


class Response:
    def __init__(self, events, status=200):
        self.events = events
        self.status_code = status
        self.ok = 200 <= status < 300
        self.text = ''
    def iter_lines(self, decode_unicode=False):
        for event in self.events:
            yield 'data: ' + json.dumps(event)
    def close(self):
        pass


class ProviderStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        os.environ['APERYN_AGENT_UID'] = str(os.getuid())
        os.environ['APERYN_AGENT_GID'] = str(os.getgid())
        self.store = ProviderStore(root / 'providers.sqlite3', root)
    def tearDown(self):
        self.temp.cleanup()

    def test_openai_stream_is_translated_without_leaking_key(self):
        self.store.save('openai', 'sk-private', ['gpt-test'])
        events = [
            {'type': 'response.reasoning_summary_text.delta', 'delta': 'Think'},
            {'type': 'response.output_text.delta', 'delta': 'Hello'},
            {'type': 'response.completed', 'response': {'usage': {'output_tokens': 7}}},
        ]
        with patch('provider_store.requests.post', return_value=Response(events)) as request:
            rows = list(self.store.stream_chat('openai', 'gpt-test', [{'role': 'user', 'content': 'Hi'}]))
        self.assertEqual(rows[0]['message']['thinking'], 'Think')
        self.assertEqual(rows[1]['message']['content'], 'Hello')
        self.assertTrue(rows[-1]['done']); self.assertEqual(rows[-1]['eval_count'], 7)
        self.assertEqual(request.call_args.args[0], 'https://api.openai.com/v1/responses')
        self.assertNotIn('sk-private', json.dumps(self.store.summaries()))

    def test_anthropic_and_google_stream_translation(self):
        self.store.save('anthropic', 'ant-private', ['claude-test'])
        anthropic = [
            {'type': 'content_block_delta', 'delta': {'type': 'thinking_delta', 'thinking': 'Check'}},
            {'type': 'content_block_delta', 'delta': {'type': 'text_delta', 'text': 'Done'}},
            {'type': 'message_delta', 'usage': {'output_tokens': 4}},
        ]
        with patch('provider_store.requests.post', return_value=Response(anthropic)):
            rows = list(self.store.stream_chat('anthropic', 'claude-test', [{'role': 'user', 'content': 'Hi'}]))
        self.assertEqual(rows[0]['message']['thinking'], 'Check'); self.assertEqual(rows[-1]['eval_count'], 4)
        self.store.save('google', 'google-private', ['gemini-test'])
        google = [{'candidates': [{'content': {'parts': [{'text': 'Hello'}]}}], 'usageMetadata': {'candidatesTokenCount': 3}}]
        with patch('provider_store.requests.post', return_value=Response(google)):
            rows = list(self.store.stream_chat('google', 'gemini-test', [{'role': 'user', 'content': 'Hi'}]))
        self.assertEqual(rows[0]['message']['content'], 'Hello'); self.assertEqual(rows[-1]['eval_count'], 3)


if __name__ == '__main__':
    unittest.main()
