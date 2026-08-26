#!/usr/bin/env python3
"""Aperyn's non-root, workspace-contained host SDK runner."""
import json, os, socket, subprocess, sys
from pathlib import Path

CONFIG = Path('/etc/aperyn-host-runner/config.json')
ALLOWED = {'dotnet','cargo','rustc','java','javac','gcc','g++','cmake','make'}

def config():
    data=json.loads(CONFIG.read_text(encoding='utf-8'))
    for key in ('workspace_root','mnt_root'):
        data[key]=str(Path(data[key]).resolve())
    return data

def host_cwd(value, data):
    raw=Path(str(value or '/workspace')).resolve(strict=False)
    if raw == Path('/workspace') or Path('/workspace') in raw.parents:
        target=Path(data['workspace_root']) / raw.relative_to('/workspace')
    elif raw == Path('/mnt') or Path('/mnt') in raw.parents:
        target=Path(data['mnt_root']) / raw.relative_to('/mnt')
    else:
        raise ValueError('Working directory is outside the Agent workspace mapping')
    target=target.resolve(strict=False)
    if not any(target == Path(root) or Path(root) in target.parents for root in map(Path,(data['workspace_root'],data['mnt_root']))):
        raise ValueError('Working directory escapes the permitted host boundaries')
    if not target.is_dir(): raise ValueError('Working directory does not exist on the host')
    return str(target)

def run(request):
    data=config(); program=str(request.get('program') or '')
    args=request.get('args') or []
    if program not in ALLOWED: raise ValueError('Program is not allowed by the Aperyn Host Runner')
    if not isinstance(args,list) or any(not isinstance(x,str) or '\x00' in x for x in args): raise ValueError('Invalid command arguments')
    result=subprocess.run([program,*args], cwd=host_cwd(request.get('cwd'),data), text=True, capture_output=True, timeout=min(max(int(request.get('timeout') or 900),1),1800), env={**os.environ,'HOME':str(Path(data['workspace_root']).parent)})
    return {'code':result.returncode,'stdout':result.stdout[-1_000_000:],'stderr':result.stderr[-1_000_000:]}

def serve():
    sock=socket.socket(fileno=3)
    while True:
        conn,_=sock.accept()
        with conn:
            try:
                raw=conn.recv(1_100_000); response={'ok':True,**run(json.loads(raw))}
            except Exception as exc: response={'ok':False,'error':str(exc)}
            conn.sendall(json.dumps(response).encode())

if __name__ == '__main__': serve()
