#!/usr/bin/env bash
# Capture non-sensitive host hardware totals and selected Ollama service settings
# for the Dockerized WebUI.  This script runs on the HOST, not in Docker.
set -u
mkdir -p ./data
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found; skipping hardware snapshot" >&2
  exit 0
fi
python3 - <<'PY'
import json, subprocess, glob, os, shutil, shlex, re
from pathlib import Path

ram=0
cpu_count=os.cpu_count() or 0
gpus=[]
ollama_env={}
try:
    with open('/proc/meminfo') as f:
        for line in f:
            if line.startswith('MemTotal:'):
                ram=int(line.split()[1])*1024
                break
except Exception:
    pass

# Read non-secret Ollama systemd environment values that affect estimates.
try:
    p=subprocess.run(['systemctl','show','ollama','--property=Environment','--value'],capture_output=True,text=True,timeout=3,check=True)
    for token in shlex.split(p.stdout.strip()):
        if '=' not in token:
            continue
        k,v=token.split('=',1)
        if k in {'OLLAMA_KV_CACHE_TYPE','OLLAMA_FLASH_ATTENTION','OLLAMA_SCHED_SPREAD','OLLAMA_MAX_LOADED_MODELS','OLLAMA_NUM_PARALLEL','OLLAMA_MAX_QUEUE','OLLAMA_KEEP_ALIVE','OLLAMA_GPU_OVERHEAD','OLLAMA_CONTEXT_LENGTH','LLAMA_ARG_FIT','LLAMA_ARG_FIT_TARGET','OLLAMA_LOAD_TIMEOUT','OLLAMA_MAX_TRANSFER_STREAMS','LLAMA_ARG_SPEC_TYPE','LLAMA_ARG_SPEC_DRAFT_N_MAX'}:
            ollama_env[k]=v
except Exception:
    pass

# NVIDIA: search common paths as PATH can be minimal under sudo/systemd shells.
nvsmi=shutil.which('nvidia-smi')
if not nvsmi:
    for candidate in ('/usr/bin/nvidia-smi','/usr/local/bin/nvidia-smi','/bin/nvidia-smi','/usr/lib/wsl/lib/nvidia-smi'):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            nvsmi=candidate; break
if nvsmi:
    try:
        p=subprocess.run([nvsmi,'--query-gpu=name,memory.total','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=4,check=True)
        for line in p.stdout.splitlines():
            if not line.strip(): continue
            name,mb=[x.strip() for x in line.rsplit(',',1)]
            gpus.append({'name':name,'total_bytes':int(float(mb))*1024*1024,'source':'nvidia-smi'})
    except Exception:
        pass

# AMD / Intel discrete local memory exposed through DRM sysfs.
if not gpus:
    seen=set()
    for device in glob.glob('/sys/class/drm/card[0-9]*/device'):
        candidates=[
            os.path.join(device,'mem_info_vram_total'),
            os.path.join(device,'lmem_total_bytes'),
            os.path.join(device,'local_memory_size'),
        ]
        total=0
        for path in candidates:
            try:
                if os.path.isfile(path):
                    total=int(Path(path).read_text().strip(),0)
                    if total>0: break
            except Exception:
                total=0
        if total<=0 or total in seen:
            continue
        seen.add(total)
        name='GPU'
        for pth in (os.path.join(device,'product_name'), os.path.join(device,'uevent')):
            try:
                text=Path(pth).read_text(errors='ignore')
                if pth.endswith('product_name') and text.strip():
                    name=text.strip(); break
                m=re.search(r'PCI_ID=([0-9A-Fa-f]{4}:[0-9A-Fa-f]{4})',text)
                if m: name=f'GPU {m.group(1)}'
            except Exception:
                pass
        gpus.append({'name':name,'total_bytes':total,'source':'drm sysfs'})

# ROCm CLI fallback when sysfs is absent/unusual.
if not gpus:
    rocm=shutil.which('rocm-smi')
    if rocm:
        try:
            p=subprocess.run([rocm,'--showmeminfo','vram'],capture_output=True,text=True,timeout=5,check=True)
            totals=[]
            for line in p.stdout.splitlines():
                m=re.search(r'VRAM Total Memory \(B\):\s*(\d+)',line)
                if m: totals.append(int(m.group(1)))
            for i,total in enumerate(totals):
                if total>0: gpus.append({'name':f'AMD GPU {i}','total_bytes':total,'source':'rocm-smi'})
        except Exception:
            pass

# Last-resort: Ollama itself logs discovered inference compute total VRAM.
# This is useful on hosts where nvidia-smi/ROCm utilities are unavailable to the
# login user but the Ollama service has already discovered the accelerator.
if not gpus and shutil.which('journalctl'):
    try:
        p=subprocess.run(['journalctl','-u','ollama','-n','500','--no-pager','-o','cat'],capture_output=True,text=True,timeout=5,check=True)
        found=[]
        for line in p.stdout.splitlines():
            if 'msg="inference compute"' not in line or 'library=cpu' in line:
                continue
            mt=re.search(r'total="([0-9.]+)\s+(GiB|MiB)"',line)
            if not mt: continue
            value=float(mt.group(1))*(1024**3 if mt.group(2)=='GiB' else 1024**2)
            md=re.search(r'description="([^"]+)"',line) or re.search(r'name=([^\s]+)',line)
            name=(md.group(1) if md else 'Ollama GPU').strip('"')
            found.append((name,int(value)))
        # Keep the latest occurrence of each device description.
        latest={name:total for name,total in found}
        for name,total in latest.items():
            if total>0: gpus.append({'name':name,'total_bytes':total,'source':'ollama journal'})
    except Exception:
        pass

payload={'system_ram_bytes':ram,'cpu_count':cpu_count,'gpus':gpus,'ollama_env':ollama_env}
with open('./data/hardware.json','w') as f:
    json.dump(payload,f,indent=2)

if gpus:
    print('Hardware snapshot: '+', '.join(f"{g['name']} {g['total_bytes']/1024**3:.1f} GB ({g.get('source','auto')})" for g in gpus)+f"; RAM {ram/1024**3:.1f} GB")
elif ram:
    print(f'Hardware snapshot: RAM {ram/1024**3:.1f} GB; GPU total unavailable. Try nvidia-smi / rocm-smi or load a model and rerun preflight.')
if ollama_env.get('OLLAMA_KV_CACHE_TYPE'):
    print('Ollama KV cache type: '+ollama_env['OLLAMA_KV_CACHE_TYPE'])
PY
