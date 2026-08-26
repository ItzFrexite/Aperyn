import importlib, io, json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import Mock, patch

class AuthIntegrationTests(unittest.TestCase):
    def test_agent_write_change_fallback_without_vcs(self):
        from agent_gateway import tool_change_fallback, tool_change_groups
        root=Path(self.tmp.name)/'workspace'; root.mkdir(exist_ok=True)
        messages=[{'info':{'id':'user-turn-1','role':'user'},'parts':[{'type':'text','text':'Create the files'}]},
        {'info':{'id':'assistant-1','parentID':'user-turn-1','role':'assistant'},'parts':[
            {'type':'tool','tool':'write','state':{'status':'completed','input':{'filePath':str(root/'test.cs'),'content':'one\ntwo\n'},'metadata':{'exists':False,'filepath':str(root/'test.cs')}}},
            {'type':'tool','tool':'write','state':{'status':'completed','input':{'filePath':str(root/'test.csproj'),'content':'<Project />\n'},'metadata':{'exists':False}}},
            {'type':'tool','tool':'write','state':{'status':'running','input':{'filePath':str(root/'ignored.txt'),'content':'no'}}},
            {'type':'tool','tool':'write','state':{'status':'completed','input':{'filePath':'/etc/outside','content':'no'},'metadata':{'exists':False}}},
        ]},
        {'info':{'id':'user-turn-2','role':'user'},'parts':[{'type':'text','text':'Create another'}]},
        {'info':{'id':'assistant-2','parentID':'user-turn-2','role':'assistant'},'parts':[
            {'type':'tool','tool':'write','state':{'status':'completed','input':{'filePath':str(root/'later.txt'),'content':'later\n'},'metadata':{'exists':False}}},
        ]}]
        groups=tool_change_groups(messages,root)
        self.assertEqual([group['parent_id'] for group in groups],['assistant-1','assistant-2'])
        self.assertEqual([item['file'] for item in groups[0]['diff']],['test.cs','test.csproj'])
        self.assertEqual([item['file'] for item in groups[1]['diff']],['later.txt'])
        changes=tool_change_fallback(messages,root)
        self.assertEqual([item['file'] for item in changes],['test.cs','test.csproj','later.txt'])
        self.assertEqual(changes[0]['additions'],2)
        self.assertEqual(changes[0]['status'],'added')
        self.assertEqual(changes[0]['after'],'one\ntwo\n')

    def test_agent_gateway_contract(self):
        class Response:
            def __init__(self, value=None, status=200):
                self.value=value; self.status_code=status; self.ok=200 <= status < 300
                self.content=b'' if status == 204 else json.dumps(value).encode()
            def json(self): return self.value
            def raise_for_status(self):
                if not self.ok: raise self.module.requests.HTTPError(str(self.status_code))

        m=self.module
        with m._db() as db:
            admin_id=db.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
            previous=db.execute('SELECT must_change_password FROM users WHERE id=?',(admin_id,)).fetchone()[0]
            db.execute('UPDATE users SET must_change_password=0 WHERE id=?',(admin_id,))
            db.execute("INSERT INTO users(username,password_hash,role,active,must_change_password,created_at,updated_at) VALUES('agent-reader','x','user',1,0,'now','now')")
            reader_id=db.execute("SELECT id FROM users WHERE username='agent-reader'").fetchone()[0]
        c=self.app.test_client()
        with c.session_transaction() as s: s['user_id']=reader_id; s['csrf_token']='reader-csrf'
        self.assertEqual(c.get('/agent').status_code,403)
        self.assertEqual(c.get('/api/agent/status').status_code,403)
        with c.session_transaction() as s: s['user_id']=admin_id; s['csrf_token']='admin-csrf'

        remote_messages=[
            {'info':{'role':'user'},'parts':[{'type':'text','text':'Inspect the project'}]},
            {'info':{'role':'assistant','providerID':'ollama','modelID':'qwen-test:latest','tokens':{'input':1024,'output':12,'reasoning':4,'cache':{'read':256,'write':8}}},'parts':[{'type':'reasoning','text':'Checking files'},{'type':'tool','tool':'read','state':{'status':'completed','input':{'filePath':'README.md'}}},{'type':'text','text':'Done'}]},
            {'info':{'role':'assistant','providerID':'ollama','modelID':'qwen-test:latest','tokens':{'total':0,'input':0,'output':0,'reasoning':0,'cache':{'read':0,'write':0}}},'parts':[{'type':'reasoning','text':'Starting the next step'}]},
        ]
        pending_permissions=[{'id':'per-1','sessionID':'remote-1','permission':'bash','patterns':['ls -d */'],'metadata':{'command':'ls -d */'}}]
        pending_questions=[{'id':'que-1','sessionID':'remote-1','questions':[{'question':'Continue?','options':[{'label':'Yes'},{'label':'No'}]}]}]
        remote_status={'type':'busy'}
        def engine_request(method,url,**kwargs):
            path=url.split(':4096',1)[-1]
            if method=='POST' and path=='/session': return Response({'id':'remote-1','title':'New agent task'})
            if method=='POST' and path.endswith('/prompt_async'): return Response(None,204)
            if method=='PATCH' and path.startswith('/session/'): return Response({'ok':True})
            if method=='GET' and path=='/global/health': return Response({'healthy':True,'version':'1.18.17'})
            if method=='GET' and path=='/config/providers':
                self.assertTrue(kwargs['params']['directory'].endswith('/workspace/project'))
                return Response({'providers':[{'id':'ollama','models':{'qwen-test:latest':{'limit':{'context':131072,'output':0}}}}]})
            if method=='GET' and path=='/session/status': return Response({'remote-1':dict(remote_status)})
            if method=='GET' and path=='/session/remote-1': return Response({'id':'remote-1','title':'Inspect the project'})
            if method=='GET' and path=='/session/remote-1/message': return Response(remote_messages)
            if method=='GET' and path.endswith('/todo'): return Response([{'content':'Review files','status':'pending'}])
            if method=='GET' and path.endswith('/diff'): return Response([{'file':'README.md','additions':2,'deletions':0}])
            if method=='GET' and path=='/permission':
                self.assertTrue(kwargs['params']['directory'].endswith('/workspace/project')); return Response(pending_permissions)
            if method=='GET' and path=='/question':
                self.assertTrue(kwargs['params']['directory'].endswith('/workspace/project')); return Response(pending_questions)
            if method=='POST' and path=='/permission/per-1/reply':
                self.assertTrue(kwargs['params']['directory'].endswith('/workspace/project')); pending_permissions.clear(); return Response(None,204)
            if method=='POST' and path=='/question/que-1/reply':
                self.assertTrue(kwargs['params']['directory'].endswith('/workspace/project')); pending_questions.clear(); return Response(None,204)
            if method=='POST' and path.endswith('/abort'): return Response(True)
            if method=='DELETE' and path.startswith('/session/'): return Response(True)
            raise AssertionError((method,path,kwargs))
        tags=Response({'models':[{'name':'qwen-test:latest','size':123}]})
        with patch('agent_gateway.requests.request',side_effect=engine_request),patch('agent_gateway.requests.get',return_value=tags):
            self.assertEqual(c.get('/agent').status_code,200)
            self.assertTrue(c.get('/api/agent/status').get_json()['connected'])
            folders=c.get('/api/agent/workspaces').get_json(); self.assertEqual(folders['current'],'.'); self.assertEqual(folders['display'],'/home/tester'); self.assertIn('project',[x['name'] for x in folders['directories']]); self.assertIn('.hidden-project',[x['name'] for x in folders['directories']]); self.assertIn('/mnt',[x['name'] for x in folders['directories']])
            nested=c.get('/api/agent/workspaces?path=project').get_json(); self.assertEqual(nested['parent'],'.'); self.assertEqual(nested['display'],'/home/tester/project')
            mounted=c.get('/api/agent/workspaces?path=@mnt').get_json(); self.assertEqual(mounted['current'],'@mnt'); self.assertEqual(mounted['display'],'/mnt'); self.assertEqual(mounted['parent'],'.'); self.assertIn('mounted-project',[x['name'] for x in mounted['directories']])
            mounted_nested=c.get('/api/agent/workspaces?path=@mnt/mounted-project').get_json(); self.assertEqual(mounted_nested['display'],'/mnt/mounted-project'); self.assertEqual(mounted_nested['parent'],'@mnt')
            self.assertEqual(c.get('/api/agent/workspaces?path=../').status_code,400)
            self.assertEqual(c.get('/api/agent/workspaces?path=@mnt/../workspace').status_code,400)
            self.assertEqual(c.get('/api/agent/workspaces?path=/etc').status_code,400)
            made=c.post('/api/agent/sessions',json={'agent':'build','workspace':'project'},headers={'X-CSRF-Token':'admin-csrf'})
            self.assertEqual(made.status_code,200,made.get_data(as_text=True)); public_id=made.get_json()['id']
            self.assertEqual(made.get_json()['workspace_value'],'project')
            self.assertEqual(made.get_json()['approval_mode'],'ask')
            accepted=c.post(f'/api/agent/sessions/{public_id}/prompt',json={'message':'Inspect the project','model':'qwen-test:latest','agent':'build'},headers={'X-CSRF-Token':'admin-csrf'})
            self.assertEqual(accepted.status_code,200,accepted.get_data(as_text=True)); self.assertTrue(accepted.get_json()['accepted'])
            snap=c.get(f'/api/agent/sessions/{public_id}/snapshot').get_json()
            self.assertEqual(snap['session']['status'],'waiting'); self.assertEqual(snap['messages'][1]['parts'][-1]['text'],'Done'); self.assertEqual(len(snap['todos']),1); self.assertEqual(snap['permissions'][0]['id'],'per-1'); self.assertEqual(snap['questions'][0]['id'],'que-1')
            self.assertEqual(snap['session']['approval_mode'],'ask')
            self.assertEqual(snap['context']['source'],'opencode'); self.assertEqual(snap['context']['used'],1292); self.assertEqual(snap['context']['limit'],131072); self.assertEqual(snap['context']['cache_read'],256); self.assertEqual(snap['context']['reasoning'],4)
            self.assertEqual(c.post('/api/agent/permissions/per-1',json={'reply':'once'},headers={'X-CSRF-Token':'admin-csrf'}).status_code,200)
            self.assertEqual(c.post('/api/agent/questions/que-1/reply',json={'answers':[['Yes']]},headers={'X-CSRF-Token':'admin-csrf'}).status_code,200)
            remote_status['type']='idle'
            completed=c.get(f'/api/agent/sessions/{public_id}/snapshot').get_json(); self.assertEqual(completed['session']['status'],'completed')
            self.assertEqual(c.post(f'/api/agent/sessions/{public_id}/abort',headers={'X-CSRF-Token':'admin-csrf'}).status_code,200)
            listed=c.get('/api/agent/sessions').get_json()['sessions']; self.assertEqual(listed[0]['status'],'stopped')
            stopped=c.get(f'/api/agent/sessions/{public_id}/snapshot').get_json(); self.assertEqual(stopped['session']['status'],'stopped')
            self.assertEqual(c.delete(f'/api/agent/sessions/{public_id}',headers={'X-CSRF-Token':'admin-csrf'}).status_code,200)
        with m._db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM agent_sessions WHERE id=?',(public_id,)).fetchone()[0],0)
            db.execute('DELETE FROM users WHERE id=?',(reader_id,)); db.execute('UPDATE users SET must_change_password=? WHERE id=?',(previous,admin_id))

    def test_chat_generation_metric_schema(self):
        with self.module._db() as db:
            cols={row[1] for row in db.execute('PRAGMA table_info(conversation_messages)')}
        self.assertIn('output_tokens',cols)
        self.assertIn('eval_duration_ns',cols)

    def test_hybrid_qwen_kv_estimator_counts_only_full_attention_layers(self):
        show={'model_info':{
            'qwen35.block_count':65, 'qwen35.embedding_length':5120,
            'qwen35.attention.head_count':24, 'qwen35.attention.head_count_kv':4,
            'qwen35.attention.key_length':256, 'qwen35.attention.value_length':256,
            'qwen35.context_length':262144, 'qwen35.full_attention_interval':4,
        }}
        estimate=self.module._model_memory_estimate(show,20*1024**3,131072,-1,
            hardware={'gpu':{'total_bytes':32*1024**3},'system':{'total_bytes':64*1024**3}},kv_cache_type='q4_0')
        self.assertEqual(estimate['kv_layer_count'],16)
        self.assertIn('hybrid full-attention',estimate['kv_attention_mode'])
        self.assertLess(estimate['kv_cache_bytes'],3.2*1024**3)
    def test_provider_credentials_are_admin_only_encrypted_and_masked(self):
        m=self.module
        with m._db() as db:
            admin=db.execute("SELECT id,must_change_password FROM users WHERE username='admin'").fetchone()
            db.execute('UPDATE users SET must_change_password=0 WHERE id=?',(admin['id'],))
            db.execute("INSERT INTO users(username,password_hash,role,active,must_change_password,created_at,updated_at) VALUES('provider-reader','x','user',1,0,'now','now')")
            reader=db.execute("SELECT id FROM users WHERE username='provider-reader'").fetchone()[0]
        c=self.app.test_client()
        with c.session_transaction() as s: s['user_id']=reader; s['csrf_token']='reader-provider'
        denied=c.put('/api/providers/openai',json={'api_key':'sk-denied','models':['test-model']},headers={'X-CSRF-Token':'reader-provider'})
        self.assertEqual(denied.status_code,403)
        with c.session_transaction() as s: s['user_id']=admin['id']; s['csrf_token']='admin-provider'
        saved=c.put('/api/providers/openai',json={'api_key':'sk-test-private-value','models':['test-model']},headers={'X-CSRF-Token':'admin-provider'})
        self.assertEqual(saved.status_code,200,saved.get_data(as_text=True)); self.assertNotIn('sk-test-private-value',saved.get_data(as_text=True))
        listed=c.get('/api/providers'); self.assertEqual(listed.status_code,200); self.assertNotIn('sk-test-private-value',listed.get_data(as_text=True)); self.assertEqual(listed.get_json()['providers'][0]['api_key_mask'],'••••••••')
        models=c.get('/api/inference/models').get_json()['models']; self.assertIn('openai:test-model',[x['value'] for x in models])
        self.assertNotIn(b'sk-test-private-value',Path(m.DATABASE_PATH).read_bytes())
        key_path=Path(m.DATABASE_PATH).parent/'agent/providers/openai.key'; self.assertEqual(key_path.read_text(),'sk-test-private-value'); self.assertEqual(key_path.stat().st_mode & 0o777,0o600)
        removed=c.delete('/api/providers/openai',headers={'X-CSRF-Token':'admin-provider'}); self.assertEqual(removed.status_code,200); self.assertFalse(key_path.exists())
        with m._db() as db:
            db.execute('DELETE FROM users WHERE id=?',(reader,)); db.execute('UPDATE users SET must_change_password=? WHERE id=?',(admin['must_change_password'],admin['id']))
    def test_dataset_converter_rewrite(self):
        m=self.module
        with m._db() as db:
            row=db.execute("SELECT id,must_change_password FROM users WHERE username='admin'").fetchone()
            db.execute('UPDATE users SET must_change_password=0 WHERE id=?',(row['id'],))
        c=self.app.test_client()
        with c.session_transaction() as s: s['user_id']=row['id']; s['csrf_token']='converter-csrf'
        sample=b'instruction,output\nHello,World\nQuestion,Answer\n'
        preview=c.post('/api/converter/preview',data={'file':(io.BytesIO(sample),'sample.csv')},headers={'X-CSRF-Token':'converter-csrf'},content_type='multipart/form-data')
        self.assertEqual(preview.status_code,200,preview.get_data(as_text=True)); self.assertEqual(preview.get_json()['columns'],['instruction','output'])
        converted=c.post('/api/converter/convert',data={'file':(io.BytesIO(sample),'sample.csv'),'instruction_col':'instruction','output_col':'output'},headers={'X-CSRF-Token':'converter-csrf'},content_type='multipart/form-data')
        self.assertEqual(converted.status_code,200,converted.get_data(as_text=True)); lines=[json.loads(line) for line in converted.get_data(as_text=True).splitlines()]; converted.close()
        self.assertEqual(lines,[{'instruction':'Hello','output':'World'},{'instruction':'Question','output':'Answer'}])
        with m._db() as db: db.execute('UPDATE users SET must_change_password=? WHERE id=?',(row['must_change_password'],row['id']))
    def test_dashboard_telemetry_clear_is_admin_only_and_scoped(self):
        m=self.module
        with m._db() as db:
            admin=db.execute("SELECT id,must_change_password FROM users WHERE username='admin'").fetchone()
            db.execute('UPDATE users SET must_change_password=0 WHERE id=?',(admin['id'],))
            db.execute("INSERT INTO users(username,password_hash,role,active,must_change_password,created_at,updated_at) VALUES('telemetry-reader','x','user',1,0,'now','now')")
            reader=db.execute("SELECT id FROM users WHERE username='telemetry-reader'").fetchone()[0]
            db.execute("INSERT INTO request_log(created_at,endpoint,model,status_code,latency_ms,prompt_tokens,output_tokens,eval_duration_ns,client_ip,client_name,request_meta_json) VALUES('now','/api/chat','test',200,1,2,3,4,'local','test','{}')")
        c=self.app.test_client()
        with c.session_transaction() as s: s['user_id']=reader; s['csrf_token']='telemetry-reader-csrf'
        denied=c.delete('/api/manager/telemetry',headers={'X-CSRF-Token':'telemetry-reader-csrf'}); self.assertEqual(denied.status_code,403)
        with c.session_transaction() as s: s['user_id']=admin['id']; s['csrf_token']='telemetry-admin-csrf'
        with m._live_lock:
            m._recent_generations.appendleft({'id':'recent-test'})
            m._active_generations['active-test']={'id':'active-test'}
        proxy_response=Mock(); proxy_response.raise_for_status=Mock(); proxy_response.json.return_value={'cleared':True}
        with patch.object(m.requests,'post',return_value=proxy_response):
            cleared=c.delete('/api/manager/telemetry',headers={'X-CSRF-Token':'telemetry-admin-csrf'})
        self.assertEqual(cleared.status_code,200,cleared.get_data(as_text=True)); result=cleared.get_json(); self.assertEqual(result['deleted_requests'],1); self.assertTrue(result['active_generations_preserved']); self.assertTrue(result['proxy_recent_cleared'])
        with m._db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM request_log').fetchone()[0],0)
            db.execute('DELETE FROM users WHERE id=?',(reader,)); db.execute('UPDATE users SET must_change_password=? WHERE id=?',(admin['must_change_password'],admin['id']))
        with m._live_lock:
            self.assertFalse(m._recent_generations); self.assertIn('active-test',m._active_generations); m._active_generations.pop('active-test',None)
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(); root=Path(cls.tmp.name)
        engine_secret=root/'agent.password'; engine_secret.write_text('test-engine-secret\n'); (root/'workspace/project').mkdir(parents=True); (root/'workspace/.hidden-project').mkdir(); (root/'mnt/mounted-project').mkdir(parents=True)
        os.environ['DATABASE_PATH']=str(root/'control.sqlite3'); os.environ['SESSION_SECRET_PATH']=str(root/'session.secret'); os.environ['SESSION_COOKIE_SECURE']='false'; os.environ['OPENCODE_SECRET_PATH']=str(engine_secret)
        os.environ['OPENCODE_WORKSPACE']=str(root/'workspace'); os.environ['OPENCODE_WORKSPACE_DISPLAY']='/home/tester'; os.environ['OPENCODE_MNT_WORKSPACE']=str(root/'mnt'); os.environ['OPENCODE_MNT_DISPLAY']='/mnt'; os.environ['APERYN_AGENT_UID']=str(os.getuid()); os.environ['APERYN_AGENT_GID']=str(os.getgid())
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'chat'))
        cls.module=importlib.import_module('app'); cls.app=cls.module.app; cls.app.config.update(TESTING=True)
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def csrf(self,c):
        with c.session_transaction() as s: return s['csrf_token']
    def login(self,c,u,p): return c.post('/login',data={'username':u,'password':p})
    def change(self,c,old,new): return c.post('/change-password',data={'csrf_token':self.csrf(c),'current_password':old,'new_password':new,'confirm_password':new})
    def api(self,c,method,path,payload=None): return c.open(path,method=method,json=payload,headers={'X-CSRF-Token':self.csrf(c)})
    def test_complete_lifecycle(self):
        m=self.module
        with m._db() as db:
            users=db.execute('SELECT * FROM users').fetchall(); self.assertEqual(len(users),1); self.assertEqual(users[0]['username'],'admin'); self.assertEqual(users[0]['must_change_password'],1); self.assertNotEqual(users[0]['password_hash'],'password'); original=users[0]['password_hash']
        m._init_db()
        with m._db() as db: self.assertEqual(db.execute('SELECT password_hash FROM users').fetchone()[0],original); self.assertEqual(db.execute('SELECT COUNT(*) FROM users').fetchone()[0],1)
        c=self.app.test_client(); self.assertEqual(c.get('/chat').status_code,302); self.assertEqual(self.login(c,'admin','wrong').status_code,401)
        first=self.login(c,'admin','password'); self.assertIn('/change-password',first.location); self.assertEqual(c.get('/chat').status_code,302); self.assertEqual(self.change(c,'password','correct-horse-23').status_code,302)
        c.post('/logout',data={'csrf_token':self.csrf(c)}); self.assertEqual(self.login(c,'admin','password').status_code,401); self.assertEqual(self.login(c,'admin','correct-horse-23').status_code,302)
        made=self.api(c,'POST','/api/auth/users',{'username':'purple','password':'temporary-23','role':'user'}); self.assertEqual(made.status_code,201,made.get_data(as_text=True)); uid=made.get_json()['id']
        self.assertEqual(self.api(c,'PATCH',f'/api/auth/users/{uid}',{'active':False}).status_code,200); c.post('/logout',data={'csrf_token':self.csrf(c)}); self.assertEqual(self.login(c,'purple','temporary-23').status_code,401)
        self.login(c,'admin','correct-horse-23'); self.assertEqual(self.api(c,'PATCH',f'/api/auth/users/{uid}',{'active':True}).status_code,200); aid=self.api(c,'GET','/api/auth/users').get_json()['primary_user_id']; self.assertEqual(self.api(c,'PATCH',f'/api/auth/users/{aid}',{'role':'user'}).status_code,409)
        c.post('/logout',data={'csrf_token':self.csrf(c)}); self.login(c,'purple','temporary-23'); self.assertEqual(self.change(c,'temporary-23','purple-password-23').status_code,302)
        theme={'accent':'#9b7cff','background':'#0e0a16','panel':'#171020','panel2':'#21162d','glass':'full'}; saved=self.api(c,'POST','/api/settings',{'theme':theme}); self.assertEqual(saved.status_code,200,saved.get_data(as_text=True)); self.assertEqual(saved.get_json()['theme'],theme)
        c.post('/logout',data={'csrf_token':self.csrf(c)}); self.login(c,'purple','purple-password-23'); self.assertEqual(c.get('/api/settings').get_json()['theme'],theme)
        c.post('/logout',data={'csrf_token':self.csrf(c)}); self.login(c,'admin','correct-horse-23'); self.assertNotEqual(c.get('/api/settings').get_json()['theme']['accent'],'#9b7cff'); self.assertEqual(c.post('/api/settings',json={'assistant_name':'x'}).status_code,400)

    def test_managed_host_pairing_and_allowlisted_connector_actions(self):
        m=self.module
        with m._db() as db:
            admin_id=db.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
            db.execute('UPDATE users SET must_change_password=0 WHERE id=?',(admin_id,))
        c=self.app.test_client()
        with c.session_transaction() as s: s['user_id']=admin_id; s['csrf_token']='host-csrf'
        made=c.post('/api/hosts',json={'name':'Studio PC','endpoint':'http://192.168.1.50:11434'},headers={'X-CSRF-Token':'host-csrf'})
        self.assertEqual(made.status_code,201,made.get_data(as_text=True)); host=made.get_json()['host']
        pairing=c.post(f"/api/hosts/{host['id']}/pairing",headers={'X-CSRF-Token':'host-csrf'}).get_json()
        self.assertTrue(pairing['pairing_token']); self.assertEqual(pairing['host_id'],host['id'])
        registered=c.post('/api/host-connector/register',json={'host_id':host['id'],'pairing_token':pairing['pairing_token']})
        self.assertEqual(registered.status_code,200,registered.get_data(as_text=True)); token=registered.get_json()['connector_token']
        headers={'Authorization':f'Bearer {token}','X-Aperyn-Host-ID':host['id']}
        snap={'helper':{'service_state':'active','effective_env':{'OLLAMA_KV_CACHE_TYPE':'q4_0'},'managed':{}},'gpu':{'detected':True}}
        self.assertIsNone(c.post('/api/host-connector/poll',json={'snapshot':snap},headers=headers).get_json()['action'])
        self.assertEqual(c.post(f"/api/hosts/{host['id']}/activate",headers={'X-CSRF-Token':'host-csrf'}).status_code,200)
        configured=c.get('/api/settings').get_json(); self.assertEqual(configured['active_host_id'],host['id']); self.assertEqual(configured['effective_ollama_endpoint'],'http://192.168.1.50:11434')
        action_id=m._queue_host_action(host['id'],'helper.status')
        action=c.post('/api/host-connector/poll',json={'snapshot':snap},headers=headers).get_json()['action']; self.assertEqual(action['id'],action_id); self.assertEqual(action['operation'],'helper.status')
        self.assertEqual(c.post(f"/api/host-connector/actions/{action_id}/result",json={'ok':True,'result':snap['helper']},headers=headers).status_code,200)
        self.assertEqual(m._wait_for_host_action(action_id,timeout=.1)['service_state'],'active')
        self.assertRaises(ValueError,m._queue_host_action,host['id'],'shell.exec')
        self.assertEqual(c.post('/api/host-connector/poll',json={},headers={'X-Aperyn-Host-ID':host['id'],'Authorization':'Bearer wrong'}).status_code,401)
        self.assertEqual(c.delete(f"/api/hosts/{host['id']}",headers={'X-CSRF-Token':'host-csrf'}).status_code,200)

    def test_all_nondynamic_web_routes_are_gated(self):
        c=self.app.test_client()
        for rule in self.app.url_map.iter_rules():
            if '<' in rule.rule or 'GET' not in rule.methods or rule.endpoint in {'login','static','health','service_worker','host_connector_register','host_connector_poll','host_connector_action_result'} or rule.rule.startswith('/ollama/'):
                continue
            response=c.get(rule.rule)
            expected=401 if rule.rule.startswith('/api/') else 302
            self.assertEqual(response.status_code,expected,f'{rule.rule} was not authentication-gated')

if __name__=='__main__': unittest.main()
