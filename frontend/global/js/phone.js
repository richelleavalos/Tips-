(() => {
  function setup(root=document) {
    root.querySelectorAll('[data-phone]').forEach(input => {
      if(input.dataset.bound) return; input.dataset.bound='1';
      const form=input.closest('form'), country=form.querySelector('[name=country_code]');
      function format(){
        const sv=!country || country.value==='+503';
        if(sv){ let d=input.value.replace(/\D/g,''); if(input.value.startsWith('+503')) d=d.slice(3);d=d.slice(0,8);input.value=d.length>4?d.slice(0,4)+'-'+d.slice(4):d;input.pattern='[0-9]{4}-?[0-9]{4}';input.maxLength=9; }
        else { input.removeAttribute('pattern');input.maxLength=24; }
      }
      country?.addEventListener('change',()=>{
        if(country.value==='custom') {
          const field=document.createElement('input');field.type='text';field.name='country_code';field.value='+';field.required=true;field.pattern='\\+[1-9][0-9]{0,3}';field.setAttribute('aria-label','Prefijo internacional');country.replaceWith(field);
          field.addEventListener('input',()=>{input.removeAttribute('pattern');input.maxLength=24;});
          input.removeAttribute('pattern');input.maxLength=24;field.focus();return;
        }
        input.value='';format();
      });
      input.addEventListener('input',format);format();
    });
  }
  setup();new MutationObserver(()=>setup()).observe(document.body,{childList:true,subtree:true});
})();
