(()=>{
  const DEFAULTS={accent:'#78a9ff',background:'#090d14',panel:'#111720',panel2:'#17202c',text:'#f3f6f8',glass:'subtle',gpuVramGb:0,systemRamGb:0,hardwareProfileVersion:3};
  const key='ollama-control-theme-v2';
  const load=()=>{try{return {...DEFAULTS,...JSON.parse(localStorage.getItem(key)||'{}')}}catch(_){return {...DEFAULTS}}};
  const save=s=>localStorage.setItem(key,JSON.stringify({...DEFAULTS,...s}));
  function shade(hex,amount){let c=hex.replace('#','');if(c.length!==6)return hex;let n=parseInt(c,16),r=Math.max(0,Math.min(255,(n>>16)+amount)),g=Math.max(0,Math.min(255,((n>>8)&255)+amount)),b=Math.max(0,Math.min(255,(n&255)+amount));return '#'+[r,g,b].map(x=>x.toString(16).padStart(2,'0')).join('')}
  function rgb(hex){const n=parseInt(String(hex).replace('#',''),16);return `${n>>16},${(n>>8)&255},${n&255}`}
  function apply(s=load()){const r=document.documentElement.style;r.setProperty('--accent',s.accent);r.setProperty('--accent-rgb',rgb(s.accent));r.setProperty('--accent-strong',shade(s.accent,-35));r.setProperty('--accent-soft',`rgba(${rgb(s.accent)},.12)`);r.setProperty('--accent-border',`rgba(${rgb(s.accent)},.32)`);r.setProperty('--accent-glow',`rgba(${rgb(s.accent)},.2)`);r.setProperty('--bg',s.background);r.setProperty('--panel',s.panel);r.setProperty('--panel-2',s.panel2);r.setProperty('--panel-3',shade(s.panel2,10));r.setProperty('--text',s.text);document.documentElement.dataset.glass=['off','subtle','full'].includes(s.glass)?s.glass:'subtle';document.documentElement.dataset.themeReady='1'}
  const validHex=v=>/^#[0-9a-f]{6}$/i.test(String(v||''));
  async function syncFromServer(){try{const r=await fetch('/api/settings',{cache:'no-store'});if(!r.ok)return load();const d=await r.json(),st=d.theme||{},patch={};for(const k of ['accent','background','panel','panel2'])if(validHex(st[k]))patch[k]=st[k];if(['off','subtle','full'].includes(st.glass))patch.glass=st.glass;if(!Object.keys(patch).length)return load();const merged={...load(),...patch};save(merged);apply(merged);window.dispatchEvent(new CustomEvent('ollama-theme-change',{detail:merged,server:true}));return merged}catch(_){return load()}}
  let csrf='';
  const nativeFetch=window.fetch.bind(window);
  window.fetch=async(input,opt={})=>{const method=String(opt.method||((input&&input.method)||'GET')).toUpperCase(),url=typeof input==='string'?input:(input&&input.url)||'';if(!['GET','HEAD','OPTIONS'].includes(method)&&(!url||new URL(url,location.href).origin===location.origin)){const headers=new Headers(opt.headers||(input&&input.headers)||{});if(csrf)headers.set('X-CSRF-Token',csrf);opt={...opt,headers}}return nativeFetch(input,opt)};
  async function loadSession(){try{const r=await nativeFetch('/api/auth/session',{cache:'no-store'});if(r.ok){const d=await r.json();csrf=d.csrf_token||'';window.OllamaUser=d.user||null}}catch(_){}}
  function normalizeNavigation(){
    const entries=[
      ['dashboard','/dashboard','Dashboard'],['models','/dashboard?view=models','Models'],
      ['chat','/chat','Chat'],['agent','/agent','Agent'],['library','/library','Model library'],
      ['converter','/converter','Dataset converter'],['storage','/storage','Storage'],
      ['downloads','/downloads','Downloads'],['settings','/settings','Settings']
    ];
    const icon=id=>`<svg class="nav-icon" aria-hidden="true"><use href="/static/brand/nav-icons.svg#${id}"></use></svg>`;
    for(const nav of document.querySelectorAll('.app-nav,.chat-side-bottom,.agent-side-bottom,.sidebar.app-sidebar nav')){
      const managed=[...nav.children];
      const find=id=>managed.find(node=>node.dataset.view===id||node.querySelector(`use[href$="#${id}"]`));
      for(const [id,href,label] of entries){
        let item=find(id);
        if(!item){
          if(id==='agent'&&window.OllamaUser?.role!=='admin')continue;
          item=document.createElement('a'); item.href=href;
          if(nav.closest('.sidebar.app-sidebar'))item.className='nav-item';
          item.innerHTML=`${icon(id)}${label}`;
        }else if(item.tagName==='A'&&!item.classList.contains('active')){
          item.innerHTML=`${icon(id)}${label}`;
        }
        nav.append(item);
      }
    }
  }
  function closeNav(){document.body.classList.remove('nav-open')}
  apply();queueMicrotask(async()=>{await loadSession();normalizeNavigation();await syncFromServer()});
  document.addEventListener('click',e=>{const m=e.target.closest('[data-mobile-menu]');if(m){e.preventDefault();document.body.classList.toggle('nav-open');return}if((e.target.closest('.app-nav a')||e.target.closest('[data-nav-close]'))&&innerWidth<=820)closeNav()});
  window.addEventListener('resize',()=>{if(innerWidth>820)closeNav()});
  window.OllamaTheme={load,save,apply,syncFromServer,defaults:()=>({...DEFAULTS}),csrf:()=>csrf,getHardware:()=>{const s=load();return {gpuVramGb:Number(s.gpuVramGb)||0,systemRamGb:Number(s.systemRamGb)||0}}};
  if('serviceWorker' in navigator){window.addEventListener('load',()=>navigator.serviceWorker.register('/sw.js').catch(()=>{}),{once:true})}
})();
