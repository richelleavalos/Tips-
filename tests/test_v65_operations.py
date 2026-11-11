"""Pruebas HTTP reales: persistencia, inventario, permisos y concurrencia."""
import base64,io,json,tempfile,threading,time,unittest,uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.request import Request,build_opener,HTTPCookieProcessor
from urllib.error import HTTPError
from PIL import Image
from backend.config import Settings
from backend.database import initialize,connect,transaction
from backend.runtime import create_server
from backend.security import RateLimiter,FieldCipher

class Client:
    def __init__(self,base):self.base=base;self.op=build_opener(HTTPCookieProcessor(CookieJar()));self.csrf=self.get('/api/csrf')[1]['csrf_token']
    def get(self,path):return self.req(path)
    def post(self,path,data):return self.req(path,data)
    def req(self,path,data=None):
        req=Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json','X-CSRF-Token':getattr(self,'csrf','')})
        try:r=self.op.open(req,timeout=15)
        except HTTPError as e:r=e
        raw=r.read()
        payload = json.loads(raw) if 'application/json' in r.headers.get('Content-Type','') else raw
        if isinstance(payload, dict) and payload.get('csrf_token'):
            self.csrf = payload['csrf_token']
        return r.status, payload
    def login(self,email='admin@demo.com',password='TipsDemo2026!'):return self.post('/api/auth/login',{'email':email,'password':password})

class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.settings=replace(Settings.load(),environment='test',port=0,database_path=Path(self.tmp.name)/'tips.db',rate_limit_per_minute=10000)
        initialize(self.settings);self.server=create_server(self.settings);self.server.RequestHandlerClass.sensitive_rate_limiter=RateLimiter(10000)
        self.server.RequestHandlerClass.log_message=lambda *a:None
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base=f'http://127.0.0.1:{self.server.server_address[1]}';self.client=Client(self.base);self.admin=Client(self.base);self.assertEqual(self.admin.login()[0],200)
        with connect(self.settings) as db:self.variant=db.execute('SELECT id FROM product_variants WHERE stock_quantity IS NOT NULL LIMIT 1').fetchone()[0]
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def register(self,c=None,email='person@tips.test'):
        c=c or self.client;status,p=c.post('/api/auth/register',{'display_name':'Persona Ficticia','email':email,'phone':'7123-4567','country_code':'+503','password':'ClaveSegura2026!' });self.assertEqual(status,201,p);return p['user']['id']
    def cart(self,c=None,qty=1):
        result=(c or self.client).post('/api/cart/items',{'variant_id':self.variant,'quantity':qty,'customization_value_ids':[]});self.assertEqual(result[0],201,result);return result[1]
    def order(self,c=None,key=None):
        c = c or self.client
        if not c.get('/api/auth/me')[1]['authenticated']:
            self.register(c, f'{uuid.uuid4().hex}@tips.test')
        return c.post('/api/checkout/create',{'customer_name':'Persona Ficticia','phone':'71234567','country_code':'+503','email':'','notes':'Pedido de pruebas','idempotency_key':key or str(uuid.uuid4())})
    def detail(self,kind,rid,c=None):return (c or self.admin).get(f'/api/ops/detail?kind={kind}&id={rid}')
    def update(self,rid,status,version,kind='order',**extra):return self.admin.post('/api/ops/update',{'id':rid,'kind':kind,'status':status,'version':version,**extra})
    def test_registration_profile_and_phone(self):
        uid=self.register();account=self.client.get('/api/account')[1];self.assertEqual(account['user']['phone'],'+50371234567')
        status,p=self.client.post('/api/account/profile',{'display_name':'Nombre Actualizado','email':'person@tips.test','phone':'2025550198','country_code':'+1','contact_preferences':'whatsapp'});self.assertEqual(status,200,p);self.assertEqual(self.client.get('/api/account')[1]['user']['phone'],'+12025550198')
        bad=self.client.post('/api/account/profile',{'display_name':'Nombre','email':'intruso@tips.test','phone':'71234567','country_code':'+503'});self.assertEqual(bad[0],400)
        bad=self.client.post('/api/auth/register',{'display_name':'Nombre','email':'x@tips.test','phone':'123','password':'ClaveSegura2026!'});self.assertEqual(bad[0],400)
    def test_authenticated_order_idempotency_and_private_tracking(self):
        self.cart();key=str(uuid.uuid4());a=self.order(key=key);b=self.order(key=key);self.assertEqual(a[0],201,a);self.assertEqual(a[1],b[1]);rid=a[1]['order_id']
        self.assertEqual(self.detail('order',rid,Client(self.base))[0],404)
        url=a[1]['tracking_url'];token=url.split('#token=')[1];self.assertEqual(self.client.get(f'/api/ops/detail?kind=order&id={rid}&token={token}')[0],200)
        with connect(self.settings) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM orders').fetchone()[0],1);self.assertEqual(db.execute('SELECT COUNT(*) FROM payments').fetchone()[0],0)
    def test_guest_draft_survives_registration_without_creating_order(self):
        self.cart()
        payload = {'customer_name':'Cliente ficticio', 'email':'draft@tips.test',
                   'phone':'71234567', 'requested_pickup':'2026-12-10', 'notes':'Prueba',
                   'idempotency_key':str(uuid.uuid4())}
        self.assertEqual(self.client.post('/api/checkout/create', payload)[0], 401)
        self.assertEqual(self.client.post('/api/checkout/draft', payload)[0], 200)
        self.assertEqual(Client(self.base).get('/api/checkout/draft')[1]['draft'], {})
        with connect(self.settings) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM orders').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM inventory_reservations').fetchone()[0], 0)
        user_id = self.register(email='draft@tips.test')
        draft = self.client.get('/api/checkout/draft')[1]['draft']
        self.assertEqual(draft['requested_pickup'], payload['requested_pickup'])
        self.assertEqual(draft['notes'], payload['notes'])
        self.assertEqual(len(self.client.get('/api/cart')[1]['items']), 1)
        status, order = self.client.post('/api/checkout/create', draft)
        self.assertEqual(status, 201, order)
        self.assertEqual(self.client.get('/api/checkout/draft')[1]['draft'], {})
        with connect(self.settings) as db:
            self.assertEqual(db.execute('SELECT user_id FROM orders').fetchone()[0], user_id)

    def test_grouped_variant_reservations_and_rollback(self):
        self.cart(qty=2);self.cart(qty=3);a=self.order();self.assertEqual(a[0],201,a)
        with connect(self.settings) as db:self.assertEqual(db.execute('SELECT quantity FROM inventory_reservations WHERE order_id=?',(a[1]['order_id'],)).fetchone()[0],5)
        self.cart(qty=1);self.cart(qty=1)
        with transaction(self.settings) as db:db.execute('UPDATE product_variants SET stock_quantity=1 WHERE id=?',(self.variant,))
        self.assertEqual(self.order()[0],409)
        with connect(self.settings) as db:self.assertEqual(db.execute('SELECT stock_quantity FROM product_variants WHERE id=?',(self.variant,)).fetchone()[0],1);self.assertEqual(db.execute('SELECT COUNT(*) FROM orders').fetchone()[0],1)
    def test_order_lifecycle_notifications_calendar_receipt(self):
        uid=self.register();self.cart();a=self.order();rid=a[1]['order_id'];self.assertEqual(a[0],201,a)
        self.assertEqual(self.update(rid,'ready',1)[0],400)
        for version,state in enumerate(['confirmed','processing','ready','completed'],1):
            result=self.update(rid,state,version,confirmed_pickup='2026-11-12T15:00');self.assertEqual(result[0],200,result)
            self.assertEqual(self.detail('order',rid,self.client)[1]['record']['status'],state)
        r=self.detail('order',rid)[1]['record'];self.assertEqual(len(r['history']),5)
        notices=self.client.get('/api/ops/notifications')[1];self.assertEqual(notices['unread'],5)
        self.client.post('/api/ops/read',{'id':notices['items'][0]['id']});self.assertEqual(self.client.get('/api/ops/notifications')[1]['unread'],4)
        self.assertEqual(self.admin.get('/api/ops/calendar')[1]['items'],[])
        total=r['total_cents'];key=str(uuid.uuid4());data={'id':rid,'amount_cents':total,'notes':'Presencial ficticio','method':'efectivo','idempotency_key':key}
        self.assertEqual(self.admin.post('/api/ops/receipt',data)[0],200);self.assertEqual(self.admin.post('/api/ops/receipt',data)[0],200)
        self.assertEqual(self.admin.get('/api/ops/reports')[1]['manual_collected_cents'],total)
        data.update(amount_cents=-total,idempotency_key=str(uuid.uuid4()));self.assertEqual(self.admin.post('/api/ops/receipt',data)[0],200)
        self.assertEqual(self.detail('order',rid)[1]['record']['collected_cents'],0)
    def test_cancel_before_and_after_consumption(self):
        for consumed in [False,True]:
            with connect(self.settings) as db:before=db.execute('SELECT stock_quantity FROM product_variants WHERE id=?',(self.variant,)).fetchone()[0]
            self.cart(qty=2);rid=self.order()[1]['order_id'];version=1
            if consumed:
                self.update(rid,'confirmed',1);self.update(rid,'processing',2);version=3
            self.assertEqual(self.update(rid,'cancelled',version)[0],200)
            with connect(self.settings) as db:after=db.execute('SELECT stock_quantity FROM product_variants WHERE id=?',(self.variant,)).fetchone()[0]
            self.assertEqual(after,before-2 if consumed else before)
    def test_last_unit_concurrency(self):
        c2=Client(self.base);self.register();self.register(c2,'second@tips.test');self.cart();self.cart(c2)
        with transaction(self.settings) as db:db.execute('UPDATE product_variants SET stock_quantity=1 WHERE id=?',(self.variant,))
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda c:self.order(c),[self.client,c2]))
        self.assertEqual(sorted(r[0] for r in results),[201,409],results)
        with connect(self.settings) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM orders').fetchone()[0],1);self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok');self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
    def test_admin_concurrent_version_guard(self):
        self.cart();rid=self.order()[1]['order_id'];admin2=Client(self.base);admin2.login()
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda c:c.post('/api/ops/update',{'kind':'order','id':rid,'version':1,'status':'confirmed'}),[self.admin,admin2]))
        self.assertEqual(sorted(r[0] for r in results),[200,409],results)
    def test_double_click_concurrency(self):
        self.register();self.cart();key=str(uuid.uuid4())
        # Dos clientes HTTP con la misma cookie emulan solicitudes simultáneas del mismo navegador.
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:self.order(key=key),range(2)))
        self.assertEqual({r[1].get('order_id') for r in results},{results[0][1]['order_id']})
        with connect(self.settings) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM orders').fetchone()[0],1)
    def test_photos_resume_private_design_and_draft(self):
        uid=self.register();self.assertEqual(self.client.post('/api/ops/draft',{'payload':{'message':'Borrador privado'}})[0],200);self.assertEqual(self.client.get('/api/ops/draft')[1]['payload']['message'],'Borrador privado');self.assertEqual(Client(self.base).get('/api/ops/draft')[1]['payload'],{})
        image=Image.new('RGB',(1400,1200),(100,140,90));out=io.BytesIO();image.save(out,'JPEG');raw=out.getvalue()
        fid=self.client.post('/api/ops/uploads/start',{'name':'referencia.jpg','size':len(raw)})[1]['id'];half=len(raw)//2
        first={'id':fid,'offset':0,'data':base64.b64encode(raw[:half]).decode()};self.assertEqual(self.client.post('/api/ops/uploads/chunk',first)[1]['offset'],half);self.assertEqual(self.client.post('/api/ops/uploads/chunk',first)[1]['offset'],half)
        self.assertEqual(self.client.post('/api/ops/uploads/chunk',{'id':fid,'offset':half,'data':base64.b64encode(raw[half:]).decode()})[1]['completed'],True)
        data={'name':'Persona Ficticia','phone':'71234567','country_code':'+503','project_type':'Interiores','message':'Renovar la iluminación del espacio de trabajo.','upload_ids':[fid],'idempotency_key':str(uuid.uuid4())}
        a=self.client.post('/api/quotes',data);b=self.client.post('/api/quotes',data);self.assertEqual(a[0],201,a);self.assertEqual(a[1],b[1]);rid=a[1]['id']
        r=self.detail('quote',rid)[1]['record'];self.assertEqual(r['user_id'],uid);self.assertEqual(len(r['files']),1)
        self.assertEqual(self.admin.get('/api/ops/file/'+fid)[1],raw);self.assertEqual(Client(self.base).get('/api/ops/file/'+fid)[0],404)
        self.assertEqual(self.client.get('/api/ops/draft')[1]['payload'],{})
        self.assertEqual(self.update(rid,'reviewing',1,kind='quote')[0],200);self.assertEqual(self.update(rid,'needs_info',2,kind='quote')[0],200)
        self.assertEqual(self.detail('quote',rid,self.client)[1]['record']['status'],'needs_info')
    def test_fake_large_and_unauthorized_upload(self):
        self.assertEqual(self.client.post('/api/ops/uploads/start',{'name':'grande.jpg','size':21*1048576})[0],400)
        fid=self.client.post('/api/ops/uploads/start',{'name':'malicioso.jpg','size':6})[1]['id']
        self.assertEqual(self.client.post('/api/ops/uploads/chunk',{'id':fid,'offset':0,'data':base64.b64encode(b'<html>').decode()})[0],400)
        self.assertEqual(Client(self.base).post('/api/ops/uploads/chunk',{'id':fid,'offset':0,'data':'YWJj'})[0],400)
    def test_roles_csrf_disabled_payments_and_history_pagination(self):
        self.register();self.assertEqual(self.client.get('/api/ops/dashboard')[0],403);self.assertEqual(self.client.post('/api/ops/update',{'kind':'order','id':1})[0],403)
        self.client.csrf='invalid';self.assertEqual(self.client.post('/api/ops/draft',{'payload':{}})[0],403);self.client.csrf=self.client.get('/api/csrf')[1]['csrf_token']
        self.assertEqual(self.client.post('/api/payments/sandbox/complete',{})[0],410)
        with transaction(self.settings) as db:db.execute('UPDATE product_variants SET stock_quantity=100 WHERE id=?',(self.variant,))
        for _ in range(35):self.cart();self.assertEqual(self.order()[0],201)
        self.assertEqual(len(self.client.get('/api/account')[1]['recent_orders']),35);self.assertEqual(self.client.get('/api/ops/records?kind=order')[1]['total'],35)
        self.assertEqual(len(self.client.get('/api/ops/records?kind=order&page=1')[1]['items']),30)
        self.assertEqual(len(self.client.get('/api/ops/records?kind=order&page=2')[1]['items']),5)
        outsider=Client(self.base);self.register(outsider,'outsider@tips.test');self.assertEqual(outsider.get('/api/ops/records?kind=order')[1]['total'],0)
    def test_read_load_100_requests(self):
        started=time.perf_counter()
        with ThreadPoolExecutor(8) as pool:results=list(pool.map(lambda _:self.admin.get('/api/ops/dashboard')[0],range(100)))
        self.assertEqual(set(results),{200});print('\nLOAD100 seconds',round(time.perf_counter()-started,3))
    def test_additive_migration_idempotent(self):
        self.cart();rid=self.order()[1]['order_id'];initialize(self.settings);initialize(self.settings)
        with connect(self.settings) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM orders').fetchone()[0],1);self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_notification_failure_retains_order_and_retries(self):
        self.register();self.cart()
        with transaction(self.settings) as db:
            db.execute("CREATE TRIGGER test_fail_notice BEFORE INSERT ON notifications BEGIN SELECT RAISE(FAIL,'simulated failure'); END")
        response=self.order();self.assertEqual(response[0],201,response);rid=response[1]['order_id']
        self.assertEqual(self.client.get('/api/ops/notifications')[1]['unread'],0)
        with connect(self.settings) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM orders WHERE id=?',(rid,)).fetchone()[0],1)
            self.assertEqual(db.execute('SELECT attempts FROM notification_outbox').fetchone()[0],1)
        with transaction(self.settings) as db:db.execute('DROP TRIGGER test_fail_notice')
        self.assertEqual(self.client.get('/api/ops/notifications')[1]['unread'],1)
        self.assertEqual(self.client.get('/api/ops/notifications')[1]['unread'],1)

    def test_expired_session_rejects_mutation(self):
        from backend.security import session_token_hash
        cookie=next(iter(self.client.op.handlers[0].cookiejar)) if False else None
        self.register()
        with transaction(self.settings) as db:db.execute("UPDATE sessions SET expires_at='2020-01-01T00:00:00+00:00' WHERE user_id IS NOT NULL AND user_id NOT IN (SELECT id FROM users WHERE role='admin')")
        self.assertEqual(self.client.post('/api/ops/draft',{'payload':{'message':'no guardar'}})[0],401)

    def test_private_internal_notes_and_client_history(self):
        uid=self.register();data={'name':'Persona','phone':'71234567','message':'Renovar un espacio de trabajo con ventanas.','project_type':'Interiores','idempotency_key':str(uuid.uuid4())}
        response=self.client.post('/api/quotes',data);rid=response[1]['id']
        self.assertEqual(self.update(rid,'reviewing',1,kind='quote',internal_notes='Nota privada administrativa')[0],200)
        self.assertNotIn('internal_notes',self.detail('quote',rid,self.client)[1]['record'])
        self.assertEqual(self.detail('quote',rid)[1]['record']['internal_notes'],'Nota privada administrativa')
        self.assertEqual(self.admin.get(f'/api/ops/records?kind=quote&client={uid}')[1]['total'],1)

    def test_original_order_snapshot_after_profile_edit(self):
        self.register();self.cart();response=self.order();rid=response[1]['order_id']
        self.client.post('/api/account/profile',{'display_name':'Nombre Nuevo','email':'person@tips.test','phone':'71230000','country_code':'+503'})
        record=self.detail('order',rid)[1]['record'];self.assertEqual(record['customer_name'],'Persona Ficticia');self.assertEqual(record['phone'],'+50371234567')

    def test_required_options_distinct_lines_and_grouped_inventory(self):
        with transaction(self.settings) as db:
            group=db.execute("INSERT INTO customizations(name,is_required) VALUES('Color prueba',1)").lastrowid
            options=[db.execute('INSERT INTO customization_values(customization_id,label) VALUES(?,?)',(group,v)).lastrowid for v in ['A','B']]
            product=db.execute('SELECT product_id FROM product_variants WHERE id=?',(self.variant,)).fetchone()[0]
            db.execute('INSERT INTO product_customizations VALUES(?,?,0)',(product,group))
        self.assertEqual(self.client.post('/api/cart/items',{'variant_id':self.variant,'quantity':1,'customization_value_ids':[]})[0],400)
        for option in options:
            self.assertEqual(self.client.post('/api/cart/items',{'variant_id':self.variant,'quantity':1,'customization_value_ids':[option]})[0],201)
        response=self.order();self.assertEqual(response[0],201,response)
        with connect(self.settings) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM order_items').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT quantity FROM inventory_reservations').fetchone()[0],2)

    def test_draft_and_temporary_photo_expiry(self):
        self.client.post('/api/ops/draft',{'payload':{'message':'caducado'}})
        fid=self.client.post('/api/ops/uploads/start',{'name':'foto.jpg','size':10})[1]['id']
        with transaction(self.settings) as db:
            db.execute("UPDATE design_drafts SET expires_at='2020-01-01T00:00:00+00:00'")
            db.execute("UPDATE design_uploads SET expires_at='2020-01-01T00:00:00+00:00'")
        d=self.client.get('/api/ops/draft')[1];self.assertEqual(d['payload'],{});self.assertEqual(d['files'],[])
        self.assertEqual(self.client.post('/api/ops/uploads/chunk',{'id':fid,'offset':0,'data':'YWJj'})[0],400)

    def test_production_does_not_create_known_demo_accounts(self):
        prod=replace(self.settings,environment='production',database_path=Path(self.tmp.name)/'production-empty.db')
        initialize(prod)
        with connect(prod) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM users').fetchone()[0],0)

    def test_nonempty_legacy_financial_migration(self):
        import sqlite3
        legacy_path=Path(self.tmp.name)/'legacy.db'
        with sqlite3.connect(legacy_path) as db:
            db.executescript((Path(__file__).resolve().parents[1]/'sql/schema.sql').read_text())
            db.execute("INSERT INTO orders(public_id,customer_name,status,subtotal_cents,total_cents,created_at,updated_at) VALUES('LEGACY-PAID','Cliente histórico','paid',1200,1200,'2025-01-01T00:00:00+00:00','2025-01-01T00:00:00+00:00')")
            db.execute("INSERT INTO payments(order_id,provider,provider_payment_id,status,amount_cents,idempotency_key,created_at,updated_at) VALUES(1,'legacy','old-provider-id','paid',1200,'legacy-idempotency','2025-01-01','2025-01-01')")
            before=db.execute('SELECT * FROM payments').fetchall()
        legacy=replace(self.settings,environment='production',database_path=legacy_path);initialize(legacy);initialize(legacy)
        with connect(legacy) as db:
            self.assertEqual(before,[tuple(r) for r in db.execute('SELECT * FROM payments')])
            row=db.execute('SELECT status,operational_status,total_cents FROM orders').fetchone();self.assertEqual(tuple(row),('paid','confirmed',1200))
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
        self.assertTrue(legacy_path.with_name('legacy.db.pre-v65.bak').exists())

    def test_smtp_worker_failure_retry_and_password_recovery_queue(self):
        from unittest.mock import patch,MagicMock
        from scripts import send_notifications
        import os
        uid=self.register()
        with transaction(self.settings) as db:db.execute("UPDATE users SET contact_preferences='email' WHERE id=?",(uid,))
        self.cart();self.order()
        response=self.client.post('/api/auth/password-reset/request',{'email':'person@tips.test'});self.assertEqual(response[0],200,response)
        self.assertTrue(response[1].get('development_token'))
        smtp=MagicMock();smtp.__enter__.return_value=smtp;smtp.send_message.side_effect=OSError('simulated SMTP failure')
        env={'TIPS_SMTP_HOST':'smtp.tips.invalid','TIPS_SMTP_FROM':'avisos@tips.test','TIPS_PUBLIC_URL':'https://tips.invalid'}
        with patch.dict(os.environ,env),patch.object(send_notifications.Settings,'load',return_value=self.settings),patch.object(send_notifications.smtplib,'SMTP',return_value=smtp):
            send_notifications.send()
            with connect(self.settings) as db:
                self.assertEqual(db.execute('SELECT attempts FROM email_outbox').fetchone()[0],1)
                self.assertIsNone(db.execute('SELECT sent_at FROM auth_mail_outbox').fetchone()[0])
            smtp.send_message.side_effect=None;send_notifications.send();calls=smtp.send_message.call_count;send_notifications.send();self.assertEqual(smtp.send_message.call_count,calls)
            with connect(self.settings) as db:
                self.assertIsNotNone(db.execute('SELECT sent_at FROM email_outbox').fetchone()[0])
                self.assertIsNotNone(db.execute('SELECT sent_at FROM auth_mail_outbox').fetchone()[0])

    def test_large_high_quality_photo_multichunk_roundtrip(self):
        import random
        rawpixels=random.Random(650).randbytes(2200*1800*3)
        image=Image.frombytes('RGB',(2200,1800),rawpixels);out=io.BytesIO();image.save(out,'JPEG',quality=95);raw=out.getvalue()
        self.assertGreater(len(raw),4*1024*1024)
        response=self.client.post('/api/ops/uploads/start',{'name':'alta-calidad.jpg','size':len(raw)});self.assertEqual(response[0],200,response);fid=response[1]['id']
        for offset in range(0,len(raw),256*1024):
            response=self.client.post('/api/ops/uploads/chunk',{'id':fid,'offset':offset,'data':base64.b64encode(raw[offset:offset+256*1024]).decode()});self.assertEqual(response[0],200,response)
        self.assertTrue(response[1]['completed']);self.assertEqual(self.client.get('/api/ops/file/'+fid)[1],raw)
        thumb=self.client.get('/api/ops/file/'+fid+'?thumbnail=1')[1];self.assertLess(len(thumb),len(raw));self.assertLessEqual(max(Image.open(io.BytesIO(thumb)).size),480)

    def test_controlled_correction_retains_history_and_calendar_date(self):
        self.cart();rid=self.order()[1]['order_id'];self.assertEqual(self.update(rid,'confirmed',1,confirmed_pickup='2026-11-12T15:00')[0],200)
        events=self.admin.get('/api/ops/calendar')[1]['items'];self.assertEqual(events[0]['date'],'2026-11-12T21:00:00+00:00')
        self.assertEqual(self.update(rid,'received',2,correction=True,notes='')[0],400)
        self.assertEqual(self.update(rid,'received',2,correction=True,notes='Confirmación registrada por error')[0],200)
        record=self.detail('order',rid)[1]['record'];self.assertEqual([e['new_status'] for e in record['history']],['received','confirmed','received'])

    def test_admin_customer_counts_follow_user_id_after_email_change(self):
        uid=self.register()
        for _ in range(3):self.cart();self.assertEqual(self.order()[0],201)
        response=self.client.post('/api/account/profile',{'display_name':'Nombre nuevo','email':'nuevo@tips.test','phone':'71234567','country_code':'+503','current_password':'ClaveSegura2026!'})
        self.assertEqual(response[0],200,response)
        data=self.admin.get('/api/admin/users')[1];user=next(u for u in data['items'] if u['id']==uid)
        self.assertEqual(user['order_count'],3);self.assertGreater(user['order_total_cents'],0)
        self.assertEqual(user['email'],'nuevo@tips.test')

    def test_root_email_protected_in_profile_api(self):
        root=Client(self.base);self.assertEqual(root.login('root@demo.com','123456789')[0],200)
        result=root.post('/api/account/profile',{'display_name':'Root prueba','email':'otro-root@tips.test','phone':'71234567','country_code':'+503','current_password':'123456789'})
        self.assertEqual(result[0],409,result)
        with connect(self.settings) as db:self.assertEqual(db.execute("SELECT email FROM users WHERE role='superadmin'").fetchone()[0],'root@demo.com')

if __name__=='__main__':unittest.main()
