(()=>{
  const defs=[
    {re:/\b(qwen|qwq)\b/i,key:'qwen',label:'Qwen',src:null,fallback:'Q'},
    {re:/\b(nvidia|nemotron)\b/i,key:'nvidia',label:'NVIDIA',src:'https://cdn.simpleicons.org/nvidia/76B900',fallback:'N'},
    {re:/\b(gpt[-_ ]?oss|openai)\b/i,key:'openai',label:'OpenAI',src:'https://cdn.simpleicons.org/openai/FFFFFF',fallback:'◎'},
    {re:/\b(llama|meta[-_ ]?llama)\b/i,key:'meta',label:'Meta',src:'https://cdn.simpleicons.org/meta/0866FF',fallback:'M'},
    {re:/\b(gemma|google)\b/i,key:'google',label:'Google',src:'https://cdn.simpleicons.org/google/4285F4',fallback:'G'},
    {re:/\b(mistral|mixtral|codestral|ministral)\b/i,key:'mistral',label:'Mistral AI',src:'https://cdn.simpleicons.org/mistralai/FA520F',fallback:'M'},
    {re:/\b(deepseek)\b/i,key:'deepseek',label:'DeepSeek',src:'https://cdn.simpleicons.org/deepseek/4D6BFE',fallback:'D'},
    {re:/\b(phi[-_ ]?\d|microsoft)\b/i,key:'microsoft',label:'Microsoft',src:'https://cdn.simpleicons.org/microsoft/5E5E5E',fallback:'⊞'},
    {re:/\b(cohere|command[-_ ]?r)\b/i,key:'cohere',label:'Cohere',src:'https://cdn.simpleicons.org/cohere/39594D',fallback:'C'},
    {re:/\b(granite|ibm)\b/i,key:'ibm',label:'IBM',src:'https://cdn.simpleicons.org/ibm/4589FF',fallback:'IBM'},
    {re:/\b(starcode|huggingface)\b/i,key:'huggingface',label:'Hugging Face',src:'https://cdn.simpleicons.org/huggingface/FFD21E',fallback:'🤗'}
  ];
  function info(name='',source='ollama'){
    const normalized=String(name).replace(/[\/_:.-]+/g,' ');
    const hit=defs.find(d=>d.re.test(normalized));
    if(hit)return hit;
    if(source==='huggingface')return {key:'huggingface',label:'Hugging Face',src:'https://cdn.simpleicons.org/huggingface/FFD21E',fallback:'🤗'};
    return {key:'ollama',label:'Ollama',src:'https://cdn.simpleicons.org/ollama/FFFFFF',fallback:'O'};
  }
  function html(name,source='ollama',small=false){
    const d=info(name,source), cls=`brand-logo ${small?'small':''} brand-${d.key}`;
    const img=d.src?`<img src="${d.src}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.hidden=true;this.nextElementSibling.hidden=false">`:'';
    return `<span class="${cls}" title="${d.label}">${img}<b ${d.src?'hidden':''}>${d.fallback}</b></span>`;
  }
  window.OllamaBrand={info,html};
})();
