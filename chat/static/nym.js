(()=>{
  const clean=state=>['idle','chatting','thinking','coding','approval','error','incognito'].includes(state)?state:'idle';
  const attr=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  function icon(state='idle',label='Nym'){
    state=clean(state);
    const eyes=state==='incognito'
      ?'<path class="nym-eyes-fill" d="M22 25h8v5h-8zm12 0h8v5h-8z"/><path class="nym-eyes" d="M30 27h4"/>'
      :state==='error'
      ?'<path class="nym-eyes" d="m25.5 25.5 4 4m0-4-4 4m9-4 4 4m0-4-4 4"/>'
      :state==='coding'
        ?'<path class="nym-eyes" d="M25 26h5M34 26h5"/>'
        :state==='approval'
          ?'<circle class="nym-eyes-fill" cx="28" cy="27" r="1.7"/><circle class="nym-eyes-fill" cx="36" cy="27" r="1.7"/>'
          :'<path class="nym-eyes" d="M26 27h3M35 27h3"/>';
    const mouth=state==='chatting'
      ?'<ellipse class="nym-mouth-fill nym-talk" cx="32" cy="34" rx="2.8" ry="2.2"/>'
      :state==='approval'
        ?'<path class="nym-mouth" d="M32 32v4M32 39v.2"/>'
        :state==='error'
          ?'<path class="nym-mouth" d="M29 36c2-2 4-2 6 0"/>'
          :'<path class="nym-mouth" d="M29 33c2 2 4 2 6 0"/>';
    const activity=state==='coding'
      ?'<path class="nym-activity nym-code" d="m13 28-4 4 4 4m38-8 4 4-4 4"/>'
      :state==='thinking'
        ?'<path class="nym-activity nym-orbit" d="M12 33c2-16 37-22 43-6 5 14-26 24-42 12"/><circle class="nym-dot" cx="13" cy="39" r="2.5"/>'
        :state==='approval'
          ?'<path class="nym-activity nym-alert" d="M50 12v7M50 23v.2"/>'
          :state==='chatting'
            ?'<path class="nym-activity nym-signal" d="M50 20c4 2 5 5 5 9M52 15c7 3 10 8 10 14"/>'
            :'';
    return `<svg class="nym nym-${state}" data-nym-state="${state}" viewBox="0 0 64 64" role="img" aria-label="${attr(label)} · ${state}"><g class="nym-antennae"><path d="M27 19C23 11 18 13 15 7M37 19C41 11 46 13 49 7"/></g><g class="nym-wings"><path d="M28 23C19 15 8 18 8 31c0 10 9 17 20 10l4-5 4 5c11 7 20 0 20-10 0-13-11-16-20-8"/></g><path class="nym-body" d="M32 17c-6 0-10 5-10 11 0 4 2 7 5 9l2 14 3 6 3-6 2-14c3-2 5-5 5-9 0-6-4-11-10-11Z"/>${eyes}${mouth}${activity}</svg>`;
  }
  function mount(target,state='idle',label='Nym'){
    if(!target)return;
    target.innerHTML=icon(state,label);
    target.dataset.nymState=clean(state);
  }
  window.Nym={icon,mount,states:['idle','chatting','thinking','coding','approval','error','incognito']};
})();
