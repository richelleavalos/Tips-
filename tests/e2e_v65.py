import json,time,uuid,os
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.getenv('TIPS_EVIDENCE_DIR',str(ROOT/'test-data/evidence')));OUT.mkdir(parents=True,exist_ok=True)
BASE=os.getenv('TIPS_TEST_BASE_URL','http://127.0.0.1:8000').rstrip('/')
from urllib.parse import urlsplit
if urlsplit(BASE).hostname not in {'127.0.0.1','localhost'}:raise SystemExit('Esta suite solo admite servidores locales con datos ficticios.')
results=[];issues=[]
def record(name,fn):
    try:fn();results.append({'case':name,'result':'PASS'})
    except Exception as e:results.append({'case':name,'result':'FAIL','detail':str(e)[:1500]});print(name,str(e)[:1000],flush=True)
def overflow(page,name):
    width=page.evaluate('document.documentElement.scrollWidth');viewport=page.viewport_size['width']
    if width>viewport+2:issues.append({'page':name,'viewport':viewport,'scrollWidth':width})
def shot(page,name):
    if '/admin/' in page.url:
        expect(page.locator('.admin-nav-list [aria-current=page]')).to_have_count(1)
        expect(page.locator('.admin-nav-list [aria-current=page]')).to_have_css('background-color','rgb(228, 236, 217)')
    modal=page.locator('dialog[open],.modal-backdrop.is-open,.cart-drawer.is-open').count()>0
    page.screenshot(path=str(OUT/(name+'.png')),full_page=not modal);overflow(page,name)
def login(page,email,password):
    page.goto(BASE+'/cuenta.html');f=page.locator('[data-auth-form=login]');f.locator('[name=email]').fill(email);f.locator('[name=password]').fill(password);f.locator('button[type=submit],button.btn').click();page.wait_for_url('**/admin/**' if email=='admin@demo.com' else '**/user/**')
with sync_playwright() as p:
    browser=getattr(p,os.getenv('TIPS_TEST_ENGINE','chromium')).launch(headless=True)
    for w,h in [(1440,900),(768,1024),(390,844)]:
        context=browser.new_context(viewport={'width':w,'height':h});page=context.new_page();page.set_default_timeout(12000)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        def public():
            for route,name in [('/','inicio'),('/servicios-de-diseno.html','servicios'),('/contacto.html','solicitud'),('/checkout.html','checkout'),('/cuenta.html','cuenta')]:
                page.goto(BASE+route);page.wait_for_load_state('networkidle');shot(page,f'{name}-{w}')
            page.goto(BASE+'/');toggle=page.locator('[data-nav-toggle]')
            if toggle.is_visible():toggle.click();expect(page.locator('[data-nav]')).to_have_class(__import__('re').compile('is-open'));toggle.click()
        record(f'public_pages_navigation_{w}',public)
        def register():
            page.goto(BASE+'/cuenta.html');page.locator('[data-auth-tab=register]').click();f=page.locator('[data-auth-form=register]');f.locator('[name=display_name]').fill('Cliente Navegador '+str(w));f.locator('[name=phone]').fill('71234567');expect(f.locator('[name=phone]')).to_have_value('7123-4567');f.locator('[name=email]').fill(f'browser-{w}-{uuid.uuid4().hex[:8]}@tips.test');f.locator('[name=password]').fill('PruebaBrowser2026!');f.locator('[type=checkbox]').check();f.locator('button.btn').click();page.wait_for_url('**/user/**');shot(page,f'cuenta-creada-{w}')
        record(f'register_mask_real_form_{w}',register)
        def profile():
            page.goto(BASE+'/user/datos.html');f=page.locator('[data-user-profile-form]');expect(f.locator('[name=phone]')).to_have_value('7123-4567');f.locator('[name=display_name]').fill('Cliente Actualizado '+str(w));f.get_by_role('button',name='Guardar cambios').click();expect(page.locator('[data-user-profile-message]')).to_contain_text('guardados');shot(page,f'perfil-{w}')
        record(f'profile_edit_{w}',profile)
        order_url=None
        def shopping():
            global order_url
            page.goto(BASE+'/tienda.html');buttons=page.locator('[data-product]');expect(buttons.first).to_be_visible();buttons.nth(1).click();expect(page.locator('[data-modal-variant]')).to_be_visible();expect(page.locator('[data-modal-add]')).to_be_enabled()
            custom=page.locator('[data-customization]');
            for i in range(custom.count()):custom.nth(i).select_option(index=1)
            page.locator('[data-qty-plus]').click();shot(page,f'producto-{w}');page.locator('[data-modal-add]').click();expect(page.locator('[data-cart-drawer]')).to_have_class(__import__('re').compile('is-open'));shot(page,f'carrito-{w}')
            page.locator('[data-cart-close]').click();buttons.nth(2).click();expect(page.locator('[data-modal-add]')).to_be_enabled();page.locator('[data-modal-add]').click();expect(page.locator('[data-cart-drawer]')).to_have_class(__import__('re').compile('is-open'))
            page.goto(BASE+'/checkout.html');f=page.locator('[data-checkout-form]');expect(f.locator('[name=customer_name]')).to_have_value('Cliente Actualizado '+str(w));f.locator('[name=requested_pickup]').fill('2026-12-10');f.locator('[name=notes]').fill('Personalizaciones y retiro de prueba '+str(w));f.get_by_role('button',name='Confirmar solicitud').click();expect(page.locator('[data-order-success]')).to_have_class(__import__('re').compile('is-open'));order_url=page.locator('[data-tracking-link]').get_attribute('href');shot(page,f'pedido-confirmado-{w}');page.locator('[data-tracking-link]').click();expect(page.locator('[data-detail]')).to_be_visible();shot(page,f'seguimiento-{w}')
        record(f'cart_customizations_checkout_tracking_{w}',shopping)
        design_url=None
        def design():
            global design_url
            page.goto(BASE+'/contacto.html');f=page.locator('[data-quote-form]');expect(f.locator('[name=name]')).to_have_value('Cliente Actualizado '+str(w));f.locator('[name=project_type]').select_option(label='Diseño de interiores');f.locator('[name=message]').fill('Necesito renovar la iluminación y los materiales de una sala de trabajo con ventanas amplias.');expect(page.locator('[data-draft-status]')).to_contain_text('Borrador guardado');page.reload();expect(f.locator('[name=message]')).to_contain_text('') if False else expect(f.locator('[name=message]')).to_have_value(__import__('re').compile('Necesito renovar'))
            photo=ROOT/'assets/images/editorial-hero.jpg';f.locator('[name=photos]').set_input_files([str(photo),str(ROOT/'assets/images/editorial-detail.jpg')]);expect(page.locator('[data-quote-message]')).to_contain_text('Fotografías cargadas',timeout=30000);expect(page.locator('.upload-row img')).to_have_count(2);shot(page,f'fotos-cargadas-{w}');f.locator('[type=submit]').click();expect(page.locator('[data-quote-success]')).to_have_class(__import__('re').compile('is-open'));design_url=page.locator('[data-design-tracking]').get_attribute('href');shot(page,f'diseno-confirmado-{w}')
        record(f'design_draft_two_photos_submit_{w}',design)
        # Administrator in a separate browser context to preserve client identity.
        ac=browser.new_context(viewport={'width':w,'height':h});a=ac.new_page();a.set_default_timeout(12000)
        def adminflow():
            login(a,'admin@demo.com','TipsDemo2026!');shot(a,f'dashboard-{w}')
            if order_url:
                params=order_url.split('?',1)[1].split('#')[0];a.goto(BASE+'/admin/trabajo.html?'+params);expect(a.locator('[data-update]')).to_be_visible()
                for s in ['confirmed','processing','ready','completed']:
                    f=a.locator('[data-update]');f.locator('[name=status]').select_option(s);f.locator('[name=notes]').fill('Estado verificado en navegador '+s);f.locator('button').click();expect(a.locator('[data-detail-content] .ops-chip')).to_have_text({'confirmed':'Confirmado','processing':'En preparación','ready':'Listo para retirar','completed':'Retirado'}[s]);expect(a.locator('[data-update] button')).to_be_enabled()
                shot(a,f'pedido-retirado-admin-{w}');page.goto(BASE+order_url);expect(page.locator('[data-detail-content] .ops-chip')).to_have_text('Retirado');shot(page,f'pedido-retirado-cliente-{w}')
            if design_url:
                params=design_url.split('?',1)[1].split('#')[0];a.goto(BASE+'/admin/trabajo.html?'+params);expect(a.locator('.ops-photos img')).to_have_count(2);f=a.locator('[data-update]');f.locator('[name=status]').select_option('reviewing');f.locator('[name=date]').fill('2026-11-15T10:00');f.locator('button').click();expect(a.locator('[data-detail-content] .ops-chip')).to_have_text('En revisión');expect(a.locator('[data-update] button')).to_be_enabled();shot(a,f'diseno-admin-{w}');page.goto(BASE+design_url);expect(page.locator('[data-detail-content] .ops-chip')).to_have_text('En revisión')
            for route,name in [('/admin/pedidos.html','pedidos-admin'),('/admin/cotizaciones.html','disenos-admin'),('/admin/calendario.html','calendario'),('/admin/reportes.html','reportes'),('/admin/actividad.html','actividad'),('/admin/productos.html','productos-admin'),('/admin/inventario.html','inventario'),('/admin/proyectos.html','proyectos'),('/admin/clientes.html','clientes'),('/admin/promociones.html','promociones'),('/admin/usuarios.html','usuarios'),('/admin/configuracion.html','configuracion'),('/admin/cuenta.html','cuenta-admin')]:
                a.goto(BASE+route);a.wait_for_load_state('networkidle');shot(a,f'{name}-{w}')
            a.goto(BASE+'/admin/pedidos.html');f=a.locator('[data-filter]');f.locator('[name=search]').fill('Cliente Actualizado');f.get_by_role('button').click();expect(a.locator('[data-list]')).to_contain_text('Cliente Actualizado');a.get_by_role('button',name='Notificaciones',exact=True).click();expect(a.locator('[data-admin-alert-popover].open')).to_be_visible();shot(a,f'avisos-{w}');a.locator('[data-admin-menu]').click() if not a.locator('[data-admin-logout]').is_visible() else None;a.locator('[data-admin-logout]').click();a.wait_for_url('**/cuenta.html');page.goto(BASE+'/user/pedidos.html');page.locator('[data-logout]').click();page.wait_for_url('**/cuenta.html')
        record(f'admin_client_connected_flows_and_all_modules_{w}',adminflow)
        if errors:issues.extend({'viewport':w,'js_error':e} for e in errors)
        ac.close();context.close()
    for w in [600,1000,1200]:
        c=browser.new_context(viewport={'width':w,'height':900});page=c.new_page()
        for route in ['/servicios-de-diseno.html','/tienda.html','/contacto.html']:
            page.goto(BASE+route);page.wait_for_load_state('networkidle');overflow(page,route)
        c.close()
    browser.close()
(OUT/'browser-results.json').write_text(json.dumps({'cases':results,'issues':issues},indent=2,ensure_ascii=False));print(json.dumps({'cases':results,'issues':issues},indent=2,ensure_ascii=False))

if any(r["result"]!="PASS" for r in results) or issues:raise SystemExit(1)
