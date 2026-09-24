// Run with: node --test tests/test_user_area.cjs
// Exercise the actual browser script with controlled asynchronous HTTP responses.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../frontend/usuario/js/user-area.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

async function account(page, mutation) {
  const nodes = new Map(), calls = [];
  function element() {
    const attributes = {};
    return {
      dataset: {}, textContent: '', innerHTML: '', value: '', disabled: false,
      classList: {toggle() {}}, addEventListener() {}, contains() {return false;},
      setAttribute(k, v) {attributes[k] = v;}, removeAttribute(k) {delete attributes[k];},
      getAttribute(k) {return attributes[k];}, focus() {},
      insertAdjacentHTML(_, value) {this.innerHTML += value;},
      querySelectorAll() {return [];},
    };
  }
  function get(selector) {
    if (!nodes.has(selector)) nodes.set(selector, element());
    return nodes.get(selector);
  }
  const names = ['display_name', 'email', 'current_password', 'new_password', 'confirm_password', 'confirmation'];
  for (const kind of ['profile', 'password', 'deactivate']) {
    const form = get(`[data-user-${kind}-form]`);
    form.elements = Object.fromEntries(names.map(n => [n, element()]));
    form.button = element(); form.button.textContent = 'Guardar';
    form.querySelector = () => form.button;
    form.resetCount = 0;
    form.reset = () => {form.resetCount++; for (const input of Object.values(form.elements)) input.value = '';};
  }
  const document = {
    body: {dataset: {userPage: page}, classList: {toggle() {}}},
    querySelector: get, querySelectorAll() {return [];},
    createElement() {
      let text = '';
      return {set textContent(v) {text = v;}, get innerHTML() {return text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}};
    },
  };
  const user = {role:'user', display_name:'Cliente "Uno"',email:'cliente@example.com'};
  const context = {
    document, Intl, URLSearchParams, encodeURIComponent, location: {pathname:'/user/'},
    window: {matchMedia() {return {matches:false};}}, requestAnimationFrame(fn) {fn();},
    confirm: () => true,
    FormData: class {constructor(form) {this.values=Object.fromEntries(names.map(n=>[n,form.elements[n].value]));} get(n) {return this.values[n];}},
    async fetch(url, options = {}) {
      calls.push({url,options});
      if (url === '/api/account') return {ok:true,json:async()=>({user,recent_orders:[]})};
      if (url === '/api/csrf') return {ok:true,json:async()=>({csrf_token:'test-token'})};
      return mutation(url,options);
    },
  };
  vm.runInNewContext(source, context);
  await tick();
  function dispatch(form) {
    const event = {currentTarget:form,preventDefault(){}};
    const result = form.onsubmit(event);
    event.currentTarget = null; // Browser event lifetime ends before HTTP resolves.
    return result;
  }
  return {get,calls,dispatch};
}

function passwords(form) {
  form.elements.current_password.value = 'OldPassword2026!';
  form.elements.new_password.value = 'NewPassword2026!';
  form.elements.confirm_password.value = 'NewPassword2026!';
}

test('password success resets the form after the event has finished', async () => {
  const ui = await account('seguridad', async () => ({ok:true,json:async()=>({ok:true})}));
  const form = ui.get('[data-user-password-form]'); passwords(form);
  await ui.dispatch(form);
  assert.equal(form.resetCount,1);
  assert.equal(ui.get('[data-user-password-message]').dataset.state,'success');
  assert.equal(form.button.disabled,false);
});

test('pending submission sends only one request, then restores the button', async () => {
  let resolve;
  const pending = new Promise(r => resolve=r);
  const ui = await account('seguridad', () => pending);
  const form=ui.get('[data-user-password-form]'); passwords(form);
  const first=ui.dispatch(form); await tick();
  assert.equal(form.button.disabled,true);
  await ui.dispatch(form);
  assert.equal(ui.calls.filter(c=>c.url==='/api/account/password').length,1);
  resolve({ok:true,json:async()=>({ok:true})}); await first;
  assert.equal(form.button.disabled,false);
  assert.equal(form.getAttribute('aria-busy'),undefined);
});

test('failed request preserves inputs and allows a successful retry', async () => {
  let attempts=0;
  const ui=await account('seguridad',async()=> ++attempts===1 ? {ok:false,status:400,json:async()=>({error:'Contraseña incorrecta.'})} : {ok:true,json:async()=>({ok:true})});
  const form=ui.get('[data-user-password-form]'); passwords(form);
  await ui.dispatch(form);
  assert.equal(form.resetCount,0);
  assert.equal(form.elements.new_password.value,'NewPassword2026!');
  assert.equal(ui.get('[data-user-password-message]').dataset.state,'error');
  assert.equal(form.button.disabled,false);
  await ui.dispatch(form);
  assert.equal(form.resetCount,1);
  assert.equal(ui.get('[data-user-password-message]').dataset.state,'success');
});

test('profile normalizes saved values, updates the header and safely renders quotes',async()=>{
  const ui=await account('datos',async()=>({ok:true,json:async()=>({user:{display_name:'Nombre guardado',email:'nuevo@example.com'}})}));
  assert.match(ui.get('[data-user-content]').innerHTML,/Cliente &quot;Uno&quot;/);
  const form=ui.get('[data-user-profile-form]');
  form.elements.display_name.value='Nombre guardado'; form.elements.email.value='nuevo@example.com';
  form.elements.current_password.value='OldPassword2026!';
  await ui.dispatch(form);
  assert.equal(ui.get('[data-user-name]').textContent,'Nombre guardado');
  assert.equal(form.elements.current_password.value,'');
  assert.equal(form.elements.email.value,'nuevo@example.com');
  assert.equal(ui.get('[data-user-profile-message]').dataset.state,'success');
});
