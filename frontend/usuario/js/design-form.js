(async () => {
  const form=document.querySelector('[data-quote-form]');if(!form)return;
  let saveTask=Promise.resolve();
  let csrf='',files=[],saving=false,timer,key=sessionStorage.getItem('tips-design-key')||crypto.randomUUID();
  sessionStorage.setItem('tips-design-key',key);
  const msg=form.querySelector('[data-quote-message]'),draft=form.querySelector('[data-draft-status]'),list=form.querySelector('[data-file-list]'),submit=form.querySelector('[type=submit]');
  async function api(path,data){
    if(data&&!csrf)csrf=(await (await fetch('/api/csrf')).json()).csrf_token;
    const r=await fetch(path,data?{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(data)}:{});
    const p=await r.json();if(!r.ok)throw Error(p.error||'No se pudo completar la acción.');return p;
  }
  function payload(){return Object.fromEntries(new FormData(form));}
  async function save(){try{await api('/api/ops/draft',{payload:payload()});draft.textContent='Borrador guardado · caduca en 7 días';}catch(e){draft.textContent='No se guardó el borrador: '+e.message;}}
  form.addEventListener('input',()=>{clearTimeout(timer);draft.textContent='Guardando…';timer=setTimeout(()=>{saveTask=save();},650);});
  function render(){
    list.replaceChildren();
    files.forEach(f=>{
      const row=document.createElement('div');row.className='upload-row';
      if(f.completed){const img=document.createElement('img');img.src='/api/ops/file/'+f.id+'?thumbnail=1';img.alt='Vista previa de '+f.name;row.append(img);}
      const label=document.createElement('span');label.textContent=f.name+' · '+Math.round(100*f.received_bytes/f.expected_bytes)+'%'+(f.completed?' · Lista':' · Selecciona el mismo archivo para reanudar');row.append(label);
      const progress=document.createElement('progress');progress.max=f.expected_bytes;progress.value=f.received_bytes;progress.setAttribute('aria-label','Progreso de '+f.name);row.append(progress);
      const remove=document.createElement('button');remove.type='button';remove.textContent='Eliminar';remove.disabled=saving;remove.onclick=async()=>{try{await api('/api/ops/uploads/delete',{id:f.id});files=files.filter(x=>x!==f);render();}catch(e){msg.textContent=e.message;}};row.append(remove);list.append(row);
    });
  }
  const ready = (async () => {
  try{
    const stored=await api('/api/ops/draft');for(const [k,v] of Object.entries(stored.payload))if(form.elements[k]&&k!=='photos')form.elements[k].value=v;
    files=stored.files;render();if(Object.keys(stored.payload).length)draft.textContent='Borrador recuperado · caduca en 7 días';
    const account=await api('/api/account').catch(()=>null);
    if(account){for(const [k,v] of Object.entries({name:account.user.display_name,email:account.user.email,phone:account.user.phone,country_code:account.user.country_code}))if(!form.elements[k].value||k==='country_code')form.elements[k].value=v||'';form.elements.phone.dispatchEvent(new Event('input'));}
  }catch(e){draft.textContent=e.message;}
  })();
  form.elements.photos.addEventListener('change',async()=>{
    if (saving) return;
    const selectedPhotos = Array.from(form.elements.photos.files);
    saving=true;submit.disabled=true;form.elements.photos.disabled=true;msg.textContent='Cargando fotografías…';
    try{
      await ready;
      for(const file of selectedPhotos){
        if(file.size>20*1048576)throw Error('Cada fotografía admite hasta 20 MB.');
        let f=files.find(x=>!x.completed&&x.name===file.name&&x.expected_bytes===file.size);
        if(!f){const started=await api('/api/ops/uploads/start',{name:file.name,size:file.size});f={id:started.id,name:file.name,expected_bytes:file.size,received_bytes:0,completed:false};files.push(f);}
        render();
        while(f.received_bytes<file.size){
          const chunk=new Uint8Array(await file.slice(f.received_bytes,f.received_bytes+256*1024).arrayBuffer());let str='';for(const b of chunk)str+=String.fromCharCode(b);
          const result=await api('/api/ops/uploads/chunk',{id:f.id,offset:f.received_bytes,data:btoa(str)});f.received_bytes=result.offset;f.completed=result.completed;render();
        }
      }
      msg.textContent='Fotografías cargadas y verificadas.';
    }catch(e){msg.textContent=e.message+' Puedes reintentar seleccionando el mismo archivo.';}
    finally{saving=false;submit.disabled=false;form.elements.photos.disabled=false;form.elements.photos.value='';render();}
  });
  form.addEventListener('submit',async e=>{
    e.preventDefault();if(saving)return;
    saving=true;submit.disabled=true;clearTimeout(timer);msg.textContent='Guardando solicitud…';
    try{
      await ready;
      await saveTask;
      if(files.some(f=>!f.completed)){msg.textContent='Completa o elimina las cargas pendientes antes de enviar.';return;}
      const data=payload();delete data.photos;data.idempotency_key=key;data.upload_ids=files.map(f=>f.id);
      const result=await api('/api/quotes',data);
      const modal=document.querySelector('[data-quote-success]');modal.classList.add('is-open');modal.setAttribute('aria-hidden','false');modal.querySelector('[data-quote-reference]').textContent=result.public_id;modal.querySelector('[data-design-tracking]').href=result.tracking_url;
      form.reset();files=[];render();draft.textContent='Solicitud enviada. El borrador se eliminó.';msg.textContent='Solicitud guardada.';
      sessionStorage.removeItem('tips-design-key');key=crypto.randomUUID();sessionStorage.setItem('tips-design-key',key);
    }catch(e){msg.textContent=e.message;}
    finally{saving=false;submit.disabled=false;}
  });
  document.querySelector('[data-success-close]')?.addEventListener('click',()=>document.querySelector('[data-quote-success]').classList.remove('is-open'));
})();
