import importlib, unittest
from pathlib import Path
from unittest.mock import Mock, patch

class HelperStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proxy=importlib.import_module('proxy')
        cls.client=cls.proxy.proxy_app.test_client()
    def test_reachable_without_shared_identity_is_mismatch(self):
        old=self.proxy.HELPER_TOKEN; self.proxy.HELPER_TOKEN=''
        try:
            with patch.object(self.proxy.requests,'get',return_value=Mock(raise_for_status=lambda:None)):
                response=self.client.get('/__ollama_control/helper-state')
            self.assertEqual(response.status_code,409); self.assertEqual(response.get_json()['state'],'authentication_mismatch')
        finally: self.proxy.HELPER_TOKEN=old
    def test_configured_but_unreachable_is_installed_stopped(self):
        old=self.proxy.HELPER_TOKEN; self.proxy.HELPER_TOKEN='configured'
        try:
            with patch.object(self.proxy.requests,'get',side_effect=ConnectionError('refused')):
                response=self.client.get('/__ollama_control/helper-state')
            self.assertEqual(response.status_code,503); self.assertEqual(response.get_json()['state'],'installed_but_stopped')
        finally: self.proxy.HELPER_TOKEN=old
    def test_wrong_host_token_is_mismatch(self):
        old=self.proxy.HELPER_TOKEN; self.proxy.HELPER_TOKEN='wrong'
        ping=Mock(raise_for_status=lambda:None)
        status=Mock(status_code=401)
        try:
            with patch.object(self.proxy.requests,'get',side_effect=[ping,status]):
                response=self.client.get('/__ollama_control/helper-state')
            self.assertEqual(response.status_code,409); self.assertEqual(response.get_json()['state'],'authentication_mismatch')
        finally: self.proxy.HELPER_TOKEN=old
    def test_launcher_verifies_identity_not_just_presence(self):
        launcher=(Path(__file__).resolve().parents[1]/'ollama-control').read_text()
        self.assertIn('helper_auth_ok',launcher)
        self.assertIn('Authorization: Bearer $token',launcher)
        self.assertIn('/var/lib/ollama-control/helper.token',launcher)
    def test_private_live_history_clear_preserves_active_generation(self):
        core=self.proxy.core
        with core._live_lock:
            core._recent_generations.appendleft({'id':'proxy-recent-test'})
            core._active_generations['proxy-active-test']={'id':'proxy-active-test'}
        self.assertEqual(self.client.post('/__ollama_control/live/clear',headers={'X-Aperyn-Internal-Token':'wrong'}).status_code,403)
        response=self.client.post('/__ollama_control/live/clear',headers={'X-Aperyn-Internal-Token':core._telemetry_clear_identity()})
        self.assertEqual(response.status_code,200); self.assertTrue(response.get_json()['cleared'])
        with core._live_lock:
            self.assertFalse(core._recent_generations); self.assertIn('proxy-active-test',core._active_generations); core._active_generations.pop('proxy-active-test',None)
if __name__=='__main__': unittest.main()
