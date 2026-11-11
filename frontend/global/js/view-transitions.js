/** Shared 500 ms crossfade, without navigation delays or replacing app documents. */
(() => {
  'use strict';
  const duration=500, key='tips:view-snapshot:v2';
  const reduced=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
  const nativeNavigation='PageSwapEvent' in window && 'PageRevealEvent' in window;
  let finishLocal=null;
  const clear=()=>{try{sessionStorage.removeItem(key);sessionStorage.removeItem('tips:view-snapshot:v1');}catch{}};
  const publicSnapshots = new Set(['/', '/index.html', '/tienda.html', '/servicios-de-diseno.html',
    '/arquitectura.html', '/proyecto.html', '/merchandise.html']);
  const canStoreSnapshot = () => publicSnapshots.has(location.pathname) && !location.hash;
  function savePublicSnapshot(destination) {
    clear();
    if (!canStoreSnapshot() || reduced()) return;
    try {
      const data = snapshot(true);
      if (destination) data.to = destination;
      const raw = JSON.stringify(data);
      if (raw.length < 1800000) sessionStorage.setItem(key, raw);
    } catch { clear(); }
  }
  function snapshot(publicOnly = false) {
    const copy=document.body.cloneNode(true);
    if (publicOnly) copy.querySelectorAll('[data-profile-slot], [data-cart-drawer], [data-order-success]').forEach(node => node.remove());
    copy.querySelectorAll('script,.tips-view-snapshot,#tips-global-loading').forEach(n=>n.remove());
    copy.querySelectorAll('input,textarea').forEach(n=>{n.removeAttribute('value');if(n.tagName==='TEXTAREA')n.textContent='';});
    copy.querySelectorAll('[data-2fa-secret],[data-dev-reset-note]').forEach(n=>n.textContent='••••');
    copy.querySelectorAll('*').forEach(n=>{
      for(const a of [...n.attributes]) if(a.name.startsWith('on')||a.name==='href')n.removeAttribute(a.name);
    });
    const computed=getComputedStyle(document.documentElement);const variables={};for(let i=0;i<computed.length;i++){const name=computed[i];if(name.startsWith('--'))variables[name]=computed.getPropertyValue(name);}
    return {variables,body:copy.outerHTML,styles:[...document.querySelectorAll('link[rel=stylesheet],head style')].map(n=>n.outerHTML).join(''),x:scrollX,y:scrollY,time:Date.now()};
  }
  function overlay(data) {
    const layer=document.createElement('div');layer.className='tips-view-snapshot';layer.inert=true;layer.setAttribute('aria-hidden','true');
    for(const [name,value] of Object.entries(data.variables||{}))layer.style.setProperty(name,value);
    const shadow=layer.attachShadow({mode:'closed'});
    shadow.innerHTML=data.styles;
    const old=document.importNode(new DOMParser().parseFromString(data.body,'text/html').body,true);
    shadow.append(old);
    old.style.margin='0';old.style.width=innerWidth+'px';old.style.marginTop=(-data.y)+'px';old.style.marginLeft=(-data.x)+'px';
    old.classList.remove('tips-fallback-enter');
    document.documentElement.append(layer);return layer;
  }
  function change(update) {
    if(reduced())return Promise.resolve(update());
    finishLocal?.();
    const layer=overlay(snapshot());
    let timer;
    const finish=()=>{
      clearTimeout(timer);layer.remove();
      document.body.classList.remove('tips-fallback-enter');
      if(finishLocal===finish)finishLocal=null;
    };
    finishLocal=finish;
    let value;
    try{value=update();}catch(error){finish();throw error;}
    return Promise.resolve(value).finally(()=>{
      if(!layer.isConnected)return;
      requestAnimationFrame(()=>{
        if(!layer.isConnected)return;
        document.body.classList.add('tips-fallback-enter');layer.classList.add('leaving');
        layer.addEventListener('animationend',finish,{once:true});
        timer=setTimeout(finish,duration+80);
      });
    });
  }
  window.TipsMotion={duration,change,nativeNavigation};
  // Native navigation covers links, redirects, history and form navigation.
  // Older engines retain an inert, script-free visual snapshot for one navigation.
  if(!nativeNavigation){
    document.addEventListener('click',e=>{
      const a=e.target.closest('a[href]');
      if(!a||e.defaultPrevented||e.button!==0||e.ctrlKey||e.metaKey||e.shiftKey||e.altKey||a.download||a.target==='_blank')return;
      const url=new URL(a.href,location.href);
      if(url.origin!==location.origin||url.pathname===location.pathname&&url.search===location.search)return;
      savePublicSnapshot(url.pathname + url.search);
    });
    addEventListener('pagehide',()=>{if (!canStoreSnapshot()) clear();});
  }else clear();
  function restore(){
    if(nativeNavigation||reduced()){clear();return;}
    try{
      const data=JSON.parse(sessionStorage.getItem(key)||'null');clear();
      if (!data && !canStoreSnapshot()) {
        document.body.classList.add('tips-fallback-enter');
        setTimeout(() => document.body.classList.remove('tips-fallback-enter'), duration + 50);
      }
      if(data&&Date.now()-data.time<10000&&(!data.to||data.to===location.pathname+location.search)){
        const layer=overlay(data);document.body.classList.add('tips-fallback-enter');
        requestAnimationFrame(()=>layer.classList.add('leaving'));
        setTimeout(()=>{layer.remove();document.body.classList.remove('tips-fallback-enter');},duration+50);
      }
    }catch{clear();}
  }
  document.addEventListener('DOMContentLoaded',restore,{once:true});
  addEventListener('pageshow',event=>{if(event.persisted)restore();});
})();
