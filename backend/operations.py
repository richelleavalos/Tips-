"""TIPS 6.5: operaciones de retiro y diseño, sin cobros electrónicos.

La columna status histórica y todas las tablas financieras se conservan.
El estado operativo tiene su propio campo, independiente del cobro.
"""
from __future__ import annotations
import base64
import hashlib
import io
import json
import os
import re
import secrets
from datetime import datetime, timedelta
from http import HTTPStatus
from PIL import Image, ImageOps, UnidentifiedImageError
import phonenumbers
from .database import SUPERADMIN_EMAIL, connect, transaction
from .runtime import RuntimeTipsRequestHandler
from .security import FieldCipher, hash_password, session_token_hash, verify_password
from .server import EMAIL_RE, iso, utc_now

ORDER_NEXT = {'received':['confirmed','cancelled'], 'confirmed':['processing','cancelled'], 'processing':['ready','cancelled'], 'ready':['completed','cancelled'], 'completed':[], 'cancelled':[]}
QUOTE_NEXT = {'received':['reviewing','cancelled'], 'reviewing':['needs_info','qualified','cancelled'], 'needs_info':['reviewing','cancelled'], 'qualified':['closed','reviewing','cancelled'], 'closed':[], 'cancelled':[]}

def phone(value, country='+503'):
    country = str(country)
    if not re.fullmatch(r'\+[1-9]\d{0,3}', country):
        raise ValueError('Selecciona un prefijo internacional válido.')
    raw = str(value).strip()
    if re.search(r'[^\d+()\s-]', raw):
        raise ValueError('El teléfono contiene caracteres inválidos.')
    digits = re.sub(r'\D', '', raw)
    if raw.startswith('+'):
        if not digits.startswith(country[1:]):
            raise ValueError('El teléfono no coincide con su prefijo.')
        digits = digits[len(country)-1:]
    if country == '+503' and len(digits) != 8:
        raise ValueError('El teléfono de El Salvador debe tener ocho dígitos.')
    if not 7 <= len(digits) <= 15-len(country[1:]):
        raise ValueError('Revisa la longitud del teléfono internacional.')
    if country!='+503':
        try:
            parsed=phonenumbers.parse(country+digits,None)
            if str(parsed.country_code)!=country[1:] or not phonenumbers.is_possible_number(parsed):
                raise ValueError('El teléfono no coincide con el plan de numeración de ese país.')
        except phonenumbers.NumberParseException:
            raise ValueError('Prefijo o teléfono internacional inválido.')
    return country + digits, country

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def validate_options(db, product_id, ids):
    if len(ids)!=len(set(ids)):
        raise ValueError('No repitas opciones de personalización.')
    groups=db.execute('SELECT c.id,c.name,c.is_required FROM product_customizations pc JOIN customizations c ON c.id=pc.customization_id WHERE pc.product_id=? AND c.is_active=1',(product_id,)).fetchall()
    selected={}
    for value in ids:
        row=db.execute('SELECT customization_id FROM customization_values WHERE id=? AND is_active=1',(value,)).fetchone()
        if row: selected[row[0]]=selected.get(row[0],0)+1
    for group in groups:
        n=selected.get(group['id'],0)
        if n>1 or (group['is_required'] and n!=1):
            raise ValueError('Selecciona una opción válida para '+group['name']+'.')

def migrate(db):
    additions = {
        'users': {'phone':'TEXT', 'country_code':"TEXT NOT NULL DEFAULT '+503'", 'contact_preferences':"TEXT NOT NULL DEFAULT 'internal'"},
        'orders': {'operational_status':"TEXT NOT NULL DEFAULT 'received'", 'requested_pickup':'TEXT', 'confirmed_pickup':'TEXT', 'notes':"TEXT NOT NULL DEFAULT ''", 'tracking_hash':'TEXT', 'version':'INTEGER NOT NULL DEFAULT 1'},
        'quote_requests': {'user_id':'INTEGER REFERENCES users(id)', 'phone':'TEXT', 'email':'TEXT', 'public_id':'TEXT', 'operational_status':"TEXT NOT NULL DEFAULT 'received'", 'tracking_hash':'TEXT', 'due_at':'TEXT', 'version':'INTEGER NOT NULL DEFAULT 1'},
    }
    for table, columns in additions.items():
        existing = {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}
        for name, spec in columns.items():
            if name not in existing:
                db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {spec}')
                if table == 'orders' and name == 'operational_status':
                    db.execute("UPDATE orders SET operational_status=CASE status WHEN 'paid' THEN 'confirmed' WHEN 'processing' THEN 'processing' WHEN 'ready' THEN 'ready' WHEN 'shipped' THEN 'completed' WHEN 'completed' THEN 'completed' WHEN 'cancelled' THEN 'cancelled' WHEN 'expired' THEN 'cancelled' WHEN 'refunded' THEN 'cancelled' ELSE 'received' END")
                if table == 'quote_requests' and name == 'operational_status':
                    db.execute("UPDATE quote_requests SET operational_status=CASE status WHEN 'contacted' THEN 'reviewing' WHEN 'qualified' THEN 'qualified' WHEN 'closed' THEN 'closed' WHEN 'archived' THEN 'cancelled' ELSE 'received' END")
    db.executescript('''
    CREATE TABLE IF NOT EXISTS operation_events(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,record_id INTEGER NOT NULL,actor_id INTEGER REFERENCES users(id),old_status TEXT,new_status TEXT,notes TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS idx_events_record ON operation_events(kind,record_id,id);
    CREATE TABLE IF NOT EXISTS request_keys(owner TEXT NOT NULL,request_key TEXT NOT NULL,kind TEXT NOT NULL,payload_hash TEXT NOT NULL,response_json TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(owner,request_key,kind));
    CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id),admin_only INTEGER NOT NULL DEFAULT 0,event_key TEXT NOT NULL,title TEXT NOT NULL,url TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(user_id,event_key));
    CREATE TABLE IF NOT EXISTS notification_reads(notification_id INTEGER REFERENCES notifications(id) ON DELETE CASCADE,user_id INTEGER REFERENCES users(id),PRIMARY KEY(notification_id,user_id));
    CREATE TABLE IF NOT EXISTS checkout_drafts(
        session_id INTEGER PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
        payload TEXT NOT NULL,
        expires_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS design_drafts(owner TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id),payload_json TEXT NOT NULL,expires_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS design_uploads(id TEXT PRIMARY KEY,owner TEXT NOT NULL,user_id INTEGER REFERENCES users(id),quote_id INTEGER REFERENCES quote_requests(id),name TEXT NOT NULL,mime TEXT,expected_bytes INTEGER NOT NULL,received_bytes INTEGER NOT NULL DEFAULT 0,data BLOB NOT NULL DEFAULT X'',thumbnail BLOB,completed INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,expires_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS idx_upload_quote ON design_uploads(quote_id);
    CREATE TABLE IF NOT EXISTS manual_receipts(id INTEGER PRIMARY KEY,order_id INTEGER NOT NULL REFERENCES orders(id),amount_cents INTEGER NOT NULL CHECK(amount_cents<>0),method TEXT NOT NULL,notes TEXT NOT NULL,actor_id INTEGER NOT NULL REFERENCES users(id),request_key TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS idx_orders_ops ON orders(operational_status,confirmed_pickup);
    CREATE INDEX IF NOT EXISTS idx_quotes_user ON quote_requests(user_id,id);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_quotes_public ON quote_requests(public_id);
    CREATE INDEX IF NOT EXISTS idx_quotes_ops ON quote_requests(operational_status,due_at);
    CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id,id);
    CREATE TABLE IF NOT EXISTS notification_outbox(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,record_id INTEGER NOT NULL,version INTEGER NOT NULL,title TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,delivered_at TEXT,last_error TEXT,created_at TEXT NOT NULL,UNIQUE(kind,record_id,version));
    CREATE TABLE IF NOT EXISTS email_outbox(id INTEGER PRIMARY KEY,notification_id INTEGER NOT NULL UNIQUE REFERENCES notifications(id),recipient TEXT NOT NULL,subject TEXT NOT NULL,body TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,sent_at TEXT,last_error TEXT);
    CREATE TABLE IF NOT EXISTS auth_mail_outbox(id INTEGER PRIMARY KEY,recipient TEXT NOT NULL,subject TEXT NOT NULL,body TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,sent_at TEXT,last_error TEXT,expires_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS schema_versions(version TEXT PRIMARY KEY,applied_at TEXT NOT NULL);
    ''')
    db.execute("INSERT OR IGNORE INTO schema_versions VALUES('6.5',?)", (iso(utc_now()),))
    # Actualizar denominaciones públicas predefinidas sin reemplazar claves o rutas internas.
    for row in db.execute("SELECT key,value_json FROM site_settings WHERE is_public=1").fetchall():
        updated=row['value_json'].replace('Arquitectura · objetos · interiores','Servicios de diseño · objetos · interiores').replace('ARQUITECTURA · OBJETOS · INTERIORES','SERVICIOS DE DISEÑO · OBJETOS · INTERIORES')
        if updated!=row['value_json']: db.execute('UPDATE site_settings SET value_json=? WHERE key=?',(updated,row['key']))

class OperationsHandler(RuntimeTipsRequestHandler):
    def _owner(self):
        user = self._current_user()
        return ('u:'+str(user['id'])) if user else 's:'+session_token_hash(self._ensure_session())

    def _bind_session_to_user(self, db, raw_token, user_id):
        rotated_token = super()._bind_session_to_user(db, raw_token, user_id)
        old='s:'+session_token_hash(raw_token); new='u:'+str(user_id)
        db.execute('UPDATE design_uploads SET owner=?,user_id=? WHERE owner=? AND quote_id IS NULL',(new,user_id,old))
        if not db.execute('SELECT 1 FROM design_drafts WHERE owner=?',(new,)).fetchone():
            db.execute('UPDATE design_drafts SET owner=?,user_id=? WHERE owner=?',(new,user_id,old))
        return rotated_token

    def _cipher(self):
        return FieldCipher(self.settings.field_encryption_key)

    def _handle_payment_webhook(self, path):
        self._json({'error':'Los pagos electrónicos fueron retirados.'}, HTTPStatus.GONE)

    def _handle_api_get(self, path, query):
        if path == '/api/checkout/draft':
            raw = self._read_session_cookie()
            if not raw:
                return self._json({'draft': {}})
            with connect(self.settings) as db:
                row = db.execute(
                    '''SELECT d.payload FROM checkout_drafts d JOIN sessions s ON s.id=d.session_id
                       WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.expires_at>? AND d.expires_at>?''',
                    (session_token_hash(raw), iso(utc_now()), iso(utc_now())),
                ).fetchone()
            payload = self._cipher().decrypt(row['payload'], aad='checkout-draft') if row else None
            return self._json({'draft': json.loads(payload) if payload else {}})
        if path.startswith('/api/ops/'): 
            try:
                self._ops_get(path, query)
            except (ValueError, LookupError) as exc:
                self._json({'error':str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path == '/api/account':
            user = self._current_user()
            if not user:
                return self._json({'error':'Autenticación requerida.'}, HTTPStatus.UNAUTHORIZED)
            with connect(self.settings) as db:
                row = dict(db.execute('SELECT id,email,display_name,phone,country_code,contact_preferences,role,created_at,password_hash,must_change_password,two_factor_enabled FROM users WHERE id=?', (user['id'],)).fetchone())
                row['has_password'] = bool(row.pop('password_hash'))
                row['phone'] = self._cipher().decrypt(row['phone'], aad='user-phone') or ''
                orders = [dict(r) for r in db.execute('SELECT public_id,operational_status AS status,total_cents,created_at FROM orders WHERE user_id=? ORDER BY id DESC', (user['id'],))]
            return self._json({'user':row,'recent_orders':orders})
        return super()._handle_api_get(path, query)

    def _handle_api_post(self, path):
        if path.startswith('/api/payments/') or path == '/api/admin/payments/refund' or path == '/api/checkout/mock':
            return self._json({'error':'Los pagos electrónicos fueron retirados.'}, HTTPStatus.GONE)
        routes = {'/api/checkout/create':self._create_checkout, '/api/checkout/draft':self._save_checkout_draft, '/api/quotes':self._create_quote,
                  '/api/ops/update':self._update_operation, '/api/ops/draft':self._draft,
                  '/api/ops/uploads/start':self._upload_start, '/api/ops/uploads/chunk':self._upload_chunk,
                  '/api/ops/uploads/delete':self._upload_delete, '/api/ops/read':self._notification_read,
                  '/api/ops/receipt':self._receipt, '/api/auth/register':self._register,
                  '/api/account/profile':self._profile}
        # No permitir que las antiguas rutas eludan el historial o inventario.
        if path in {'/api/admin/orders/update','/api/admin/quotes/update'}:
            data = self._read_json()
            if data is not None:
                data['kind'] = 'order' if 'orders' in path else 'quote'
                self._guard(self._update_operation, data)
            return
        if path in routes:
            data = self._read_json()
            if data is not None:
                self._guard(routes[path], data)
            return
        super()._handle_api_post(path)

    def _guard(self, fn, data):
        try:
            fn(data)
        except (ValueError, LookupError) as exc:
            self._json({'error':str(exc)}, HTTPStatus.CONFLICT if isinstance(exc, LookupError) else HTTPStatus.BAD_REQUEST)

    def log_request(self, code='-', size='-'):
        # Los parámetros pueden contener enlaces privados, correos o búsquedas.
        path = self.path.split('?', 1)[0].split('#', 1)[0]
        self.log_message('"%s %s %s" %s %s', self.command, path, self.request_version, code, size)

    def _request_password_reset(self,data):
        email=str(data.get('email','')).strip().lower();debug=None
        if EMAIL_RE.fullmatch(email):
            with transaction(self.settings) as db:
                row=db.execute('SELECT id FROM users WHERE email=? AND is_active=1',(email,)).fetchone()
                if row:
                    token=secrets.token_urlsafe(32);now=iso(utc_now());expires=iso(utc_now()+timedelta(minutes=self.settings.password_reset_minutes))
                    db.execute('UPDATE password_reset_tokens SET used_at=? WHERE user_id=? AND used_at IS NULL',(now,row['id']))
                    db.execute('INSERT INTO password_reset_tokens(user_id,token_hash,created_at,expires_at) VALUES(?,?,?,?)',(row['id'],digest(token),now,expires))
                    # El token permanece cifrado hasta que el worker prepara el correo.
                    body=self._cipher().encrypt('Recupera tu acceso a TIPS. Abre /recuperar.html#token='+token+' . El enlace caduca pronto.',aad='auth-mail')
                    db.execute('INSERT INTO auth_mail_outbox(recipient,subject,body,expires_at) VALUES(?,?,?,?)',(email,'Recuperar acceso a TIPS',body,expires))
                    if self.settings.environment!='production':debug=token
        result={'ok':True,'message':'Si la cuenta existe, se preparó un enlace de recuperación. Su envío requiere correo configurado.'}
        if debug:result['development_token']=debug
        self._json(result)

    def _unexpected_error(self):
        import sys
        error_id='TIP-'+secrets.token_hex(4).upper()
        print('[TIPS] Error interno '+error_id,file=sys.stderr)
        try:
            with transaction(self.settings) as db:
                db.execute("INSERT INTO audit_logs(action,entity_type,entity_id,metadata_json) VALUES('system_error','system',?,'{}')",(error_id,))
                for user in db.execute("SELECT id FROM users WHERE is_active=1 AND role IN('admin','superadmin')"):
                    db.execute('INSERT OR IGNORE INTO notifications(user_id,admin_only,event_key,title,url,created_at) VALUES(?,1,?,?,?,?)',(user['id'],'error:'+error_id,'Error que requiere revisión · '+error_id,'/admin/actividad.html',iso(utc_now())))
        except Exception: pass
        self._json({'error':'No se pudo completar la operación. Conserva el identificador de soporte.','error_id':error_id},HTTPStatus.INTERNAL_SERVER_ERROR)

    def _identity(self, data, name_key):
        name = str(data.get(name_key,'')).strip()
        email = str(data.get('email','')).strip().lower()
        number, code = phone(data.get('phone',''), data.get('country_code','+503'))
        if not 2 <= len(name) <= 120 or (email and not EMAIL_RE.fullmatch(email)) or len(email)>180:
            raise ValueError('Revisa el nombre y correo electrónico.')
        return name,email,number,code

    def _register(self, data):
        name,email,number,code = self._identity(data,'display_name')
        if not email or email == SUPERADMIN_EMAIL:
            raise ValueError('Indica un correo válido para una cuenta de cliente.')
        encoded = hash_password(str(data.get('password','')))
        raw = self._ensure_session()
        stamp = iso(utc_now())
        with transaction(self.settings) as db:
            if db.execute('SELECT 1 FROM users WHERE email=?',(email,)).fetchone():
                raise ValueError('Ya existe una cuenta con ese correo.')
            uid = db.execute("INSERT INTO users(email,password_hash,display_name,phone,country_code,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (email,encoded,name,self._cipher().encrypt(number,aad='user-phone'),code,stamp,stamp)).lastrowid
            rotated_token = self._bind_session_to_user(db,raw,uid)
        self._authenticated_json({'user':{'id':uid,'email':email,'display_name':name,'role':'user','must_change_password':False,'two_factor_enabled':False}}, rotated_token, HTTPStatus.CREATED)

    def _profile(self, data):
        user = self._current_user()
        if not user:
            return self._json({'error':'Autenticación requerida.'}, HTTPStatus.UNAUTHORIZED)
        name,email,number,code = self._identity(data,'display_name')
        if email != user['email'] and (user['role'] == 'superadmin' or email == SUPERADMIN_EMAIL):
            raise LookupError('El correo de la cuenta raíz está protegido.')
        prefs = str(data.get('contact_preferences','internal'))
        if prefs not in {'internal','email','whatsapp'} or not email:
            raise ValueError('Revisa el correo y las preferencias.')
        with transaction(self.settings) as db:
            row = db.execute('SELECT * FROM users WHERE id=?',(user['id'],)).fetchone()
            if email != row['email'] and not verify_password(str(data.get('current_password','')), row['password_hash'] or ''):
                raise ValueError('Confirma tu contraseña actual para cambiar el correo.')
            if db.execute('SELECT 1 FROM users WHERE email=? AND id<>?',(email,user['id'])).fetchone():
                raise ValueError('Ese correo pertenece a otra cuenta.')
            if email != row['email']:
                self._invalidate_recovery(db, user['id'])
            db.execute('UPDATE users SET display_name=?,email=?,phone=?,country_code=?,contact_preferences=?,updated_at=? WHERE id=?', (name,email,self._cipher().encrypt(number,aad='user-phone'),code,prefs,iso(utc_now()),user['id']))
            self._audit(db,user,'self_update','user',str(user['id']),{'email_changed':email!=row['email']})
        self._json({'ok':True,'user':{**user,'display_name':name,'email':email}})

    def _key(self, db, data, kind):
        key = str(data.get('idempotency_key',''))
        if not re.fullmatch(r'[\w-]{16,100}', key):
            raise ValueError('Falta la clave de reintento. Recarga el formulario.')
        fingerprint = digest(json.dumps({k:v for k,v in data.items() if k!='idempotency_key'},sort_keys=True))
        row = db.execute('SELECT * FROM request_keys WHERE owner=? AND request_key=? AND kind=?',(self._owner(),key,kind)).fetchone()
        if row and row['payload_hash'] != fingerprint:
            raise LookupError('La clave de envío ya se utilizó con otros datos.')
        return key,fingerprint,json.loads(self._cipher().decrypt(row['response_json'], aad='request-response')) if row else None

    def _save_key(self, db, key, fingerprint, kind, response):
        db.execute('INSERT INTO request_keys VALUES(?,?,?,?,?,?)',(self._owner(),key,kind,fingerprint,self._cipher().encrypt(json.dumps(response), aad='request-response'),iso(utc_now())))

    def _event(self, db, kind, rid, before, after, actor=None, notes=''):
        db.execute('INSERT INTO operation_events(kind,record_id,actor_id,old_status,new_status,notes,created_at) VALUES(?,?,?,?,?,?,?)',(kind,rid,actor,before,after,notes,iso(utc_now())))

    def _notify(self, db, kind, rid, title):
        # Se registra intención durable dentro de la transacción de negocio.
        # El reparto se reintenta aparte; nunca depende de correo ni de un proveedor.
        table='orders' if kind=='order' else 'quote_requests'
        version=db.execute(f'SELECT version FROM {table} WHERE id=?',(rid,)).fetchone()[0]
        db.execute('INSERT OR IGNORE INTO notification_outbox(kind,record_id,version,title,created_at) VALUES(?,?,?,?,?)',(kind,rid,version,title,iso(utc_now())))

    def _deliver_notifications(self):
        from .notifications import NotificationDispatcher
        NotificationDispatcher(self.settings).deliver()

    def _date(self, value):
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value))
            if parsed.tzinfo is None:
                from zoneinfo import ZoneInfo
                parsed = parsed.replace(tzinfo=ZoneInfo('America/El_Salvador'))
            from datetime import timezone
            return iso(parsed.astimezone(timezone.utc))
        except (ValueError,TypeError):
            raise ValueError('Fecha inválida.')

    def _save_checkout_draft(self, data):
        name, email, number, code = self._identity(data, 'customer_name')
        requested = str(data.get('requested_pickup', ''))
        notes = str(data.get('notes', '')).strip()
        if not email or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', requested) or len(notes) > 3000:
            raise ValueError('Revisa el correo, la fecha de retiro y las indicaciones.')
        self._date(requested)
        key = str(data.get('idempotency_key', ''))
        if not re.fullmatch(r'[\w-]{16,100}', key):
            raise ValueError('Recarga el formulario para guardar tu pedido.')
        draft = {'customer_name': name, 'email': email, 'phone': number, 'country_code': code,
                 'requested_pickup': requested, 'notes': notes, 'idempotency_key': key}
        raw = self._read_session_cookie()
        now = iso(utc_now())
        with transaction(self.settings) as db:
            session = db.execute(
                '''SELECT s.id FROM sessions s JOIN carts c ON c.session_id=s.id
                   WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.expires_at>?
                   AND c.status='active' AND EXISTS(SELECT 1 FROM cart_items WHERE cart_id=c.id)''',
                (session_token_hash(raw), now),
            ).fetchone()
            if not session:
                raise ValueError('Agrega productos antes de guardar el pedido.')
            db.execute('DELETE FROM checkout_drafts WHERE expires_at<=?', (now,))
            db.execute(
                '''INSERT INTO checkout_drafts VALUES(?,?,?)
                   ON CONFLICT(session_id) DO UPDATE SET payload=excluded.payload,expires_at=excluded.expires_at''',
                (session['id'], self._cipher().encrypt(json.dumps(draft), aad='checkout-draft'),
                 iso(utc_now() + timedelta(days=7))),
            )
        self._json({'ok': True})

    def _create_checkout(self, data, **unused):
        user = self._current_user()
        if not user:
            return self._json({'error': 'Inicia sesión o crea una cuenta para confirmar el pedido.'}, HTTPStatus.UNAUTHORIZED)
        if user['role'] != 'user':
            return self._json({'error': 'Usa una cuenta de cliente para confirmar el pedido.'}, HTTPStatus.FORBIDDEN)
        if user.get('must_change_password'):
            raise ValueError('Cambia la contraseña temporal antes de realizar pedidos.')
        name,email,number,_ = self._identity(data,'customer_name')
        requested = self._date(data.get('requested_pickup'))
        notes = str(data.get('notes','')).strip()
        if len(notes)>3000:
            raise ValueError('Las indicaciones admiten hasta 3000 caracteres.')
        raw = self._ensure_session()
        with transaction(self.settings) as db:
            key,fingerprint,replay = self._key(db,data,'order')
            if replay:
                return self._json(replay)
            cart = db.execute("SELECT c.* FROM carts c JOIN sessions s ON s.id=c.session_id WHERE s.token_hash=? AND s.user_id=? AND s.revoked_at IS NULL AND s.expires_at>? AND c.status='active'",(session_token_hash(raw), user['id'], iso(utc_now()))).fetchone()
            if not cart:
                raise ValueError('El carrito está vacío.')
            items = self._repriced_cart_items(db,cart['id'])
            if not items:
                raise ValueError('El carrito está vacío.')
            totals = {}
            for item in items:
                totals[item['variant_id']] = totals.get(item['variant_id'],0)+item['quantity']
            for vid,qty in totals.items():
                stock = db.execute('SELECT stock_quantity FROM product_variants WHERE id=?',(vid,)).fetchone()[0]
                if stock is not None and stock<qty:
                    raise LookupError('El inventario cambió. Reduce la cantidad y vuelve a intentarlo.')
            total = sum(i['quantity']*i['unit_price_cents'] for i in items)
            now = iso(utc_now())
            public = 'TIPS-'+secrets.token_hex(6).upper()
            token = secrets.token_urlsafe(32)
            rid = db.execute("INSERT INTO orders(public_id,user_id,email,customer_name,phone,status,currency,subtotal_cents,total_cents,created_at,updated_at,tracking_hash,requested_pickup,notes) VALUES(?,?,?,?,?,'pending_payment',?,?,?,?,?,?,?,?)",(public,user['id'] if user else None,email,name,self._cipher().encrypt(number,aad='order-phone'),cart['currency'],total,total,now,now,digest(token),requested,self._cipher().encrypt(notes,aad='order-notes'))).lastrowid
            for i in items:
                db.execute('INSERT INTO order_items(order_id,variant_id,product_name,sku,quantity,unit_price_cents,customization_json) VALUES(?,?,?,?,?,?,?)',(rid,i['variant_id'],i['name'],i['sku'],i['quantity'],i['unit_price_cents'],i['customization_json']))
            for vid,qty in totals.items():
                if db.execute('SELECT stock_quantity FROM product_variants WHERE id=?',(vid,)).fetchone()[0] is not None:
                    db.execute('UPDATE product_variants SET stock_quantity=stock_quantity-? WHERE id=?',(qty,vid))
                    db.execute("INSERT INTO inventory_reservations(order_id,variant_id,quantity,expires_at,created_at,updated_at) VALUES(?,?,?,?,?,?)",(rid,vid,qty,'9999-12-31T00:00:00+00:00',now,now))
                    db.execute("INSERT INTO inventory_movements(variant_id,delta,reason,reference_type,reference_id,created_at) VALUES(?,?,'reserva de retiro','order',?,?)",(vid,-qty,rid,now))
            db.execute("UPDATE carts SET status='converted',user_id=?,updated_at=? WHERE id=?",(user['id'] if user else None,now,cart['id']))
            self._event(db,'order',rid,None,'received',user['id'] if user else None)
            self._notify(db,'order',rid,'Pedido recibido · '+public)
            result = {'public_id':public,'order_id':rid,'order_status':'received','total_cents':total,'tracking_url':f'/seguimiento.html?kind=order&id={rid}#token={token}'}
            self._save_key(db,key,fingerprint,'order',result)
            db.execute('DELETE FROM checkout_drafts WHERE session_id=?', (cart['session_id'],))
        self._json(result,HTTPStatus.CREATED)

    def _create_quote(self, data):
        name,email,number,_ = self._identity(data,'name')
        message = str(data.get('message','')).strip()
        comments = str(data.get('comments','')).strip()
        if len(comments)>3000: raise ValueError('Los comentarios admiten hasta 3000 caracteres.')
        if comments: message += '\n\nComentarios: '+comments
        budget = str(data.get('budget','')).strip()[:120]
        if budget: message += '\n\nPresupuesto indicado: '+budget
        project = str(data.get('project_type','')).strip()
        files = data.get('upload_ids',[])
        if not 20<=len(message)<=20000 or not 2<=len(project)<=120 or not isinstance(files,list) or len(files)>20 or any(not isinstance(f,str) for f in files) or len(set(files))!=len(files):
            raise ValueError('Describe el proyecto (20 a 20000 caracteres) y revisa los archivos.')
        user = self._current_user()
        now = iso(utc_now())
        with transaction(self.settings) as db:
            key,fingerprint,replay = self._key(db,data,'quote')
            if replay:
                return self._json(replay)
            for fid in files:
                if not db.execute('SELECT 1 FROM design_uploads WHERE id=? AND owner=? AND quote_id IS NULL AND completed=1 AND expires_at>?',(fid,self._owner(),now)).fetchone():
                    raise ValueError('Una fotografía no terminó de cargarse o caducó. Vuelve a cargarla.')
            public = 'DIS-'+secrets.token_hex(6).upper()
            token = secrets.token_urlsafe(32)
            rid = db.execute('INSERT INTO quote_requests(name,contact,project_type,message,user_id,phone,email,public_id,tracking_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(name,self._cipher().encrypt(number,aad='quote-contact'),project,self._cipher().encrypt(message,aad='quote-message'),user['id'] if user else None,self._cipher().encrypt(number,aad='quote-phone'),email,public,digest(token),now,now)).lastrowid
            for fid in files:
                db.execute('UPDATE design_uploads SET quote_id=? WHERE id=?',(rid,fid))
            db.execute('DELETE FROM design_drafts WHERE owner=?',(self._owner(),))
            self._event(db,'quote',rid,None,'received',user['id'] if user else None)
            self._notify(db,'quote',rid,'Solicitud de diseño recibida · '+public)
            result = {'public_id':public,'id':rid,'tracking_url':f'/seguimiento.html?kind=quote&id={rid}#token={token}'}
            self._save_key(db,key,fingerprint,'quote',result)
        self._json(result,HTTPStatus.CREATED)

    def _update_operation(self, data):
        user = self._require_admin()
        if not user:
            return
        if type(data.get('id'))!=int or type(data.get('version'))!=int or data['id']<1:
            raise ValueError('Identificador o versión inválidos.')
        kind = data.get('kind')
        table = 'orders' if kind=='order' else 'quote_requests' if kind=='quote' else None
        if not table:
            raise ValueError('Tipo de registro inválido.')
        with transaction(self.settings) as db:
            row = db.execute(f'SELECT * FROM {table} WHERE id=?',(data.get('id'),)).fetchone()
            if not row:
                raise ValueError('Registro no encontrado.')
            if data.get('version') != row['version']:
                raise LookupError('Otra administradora actualizó el registro. Recarga antes de guardar.')
            status = data.get('status',row['operational_status'])
            before = row['operational_status']
            transitions = ORDER_NEXT if kind=='order' else QUOTE_NEXT
            correction = data.get('correction', False)
            if not isinstance(status, str) or type(correction) is not bool:
                raise ValueError('Estado o corrección inválidos.')
            notes = str(data.get('notes','')).strip()
            if len(notes)>3000:
                raise ValueError('La observación es demasiado extensa.')
            if correction:
                if not notes or kind!='order' or (before,status) not in {('confirmed','received'),('ready','processing')}:
                    raise ValueError('Solo se puede corregir Confirmado → Recibido o Listo → Preparación con una justificación.')
            elif status!=before and status not in transitions.get(before,[]):
                raise ValueError('Transición de estado no permitida.')
            date_field = 'confirmed_pickup' if kind=='order' else 'due_at'
            date = self._date(data[date_field]) if date_field in data else row[date_field]
            if kind=='order' and status=='processing' and before!='processing':
                db.execute("UPDATE inventory_reservations SET status='consumed',updated_at=? WHERE order_id=? AND status='reserved'",(iso(utc_now()),row['id']))
            if kind=='order' and status=='cancelled' and before!='cancelled':
                for res in db.execute("SELECT * FROM inventory_reservations WHERE order_id=? AND status='reserved'",(row['id'],)).fetchall():
                    db.execute('UPDATE product_variants SET stock_quantity=stock_quantity+? WHERE id=?',(res['quantity'],res['variant_id']))
                    db.execute("UPDATE inventory_reservations SET status='released',updated_at=? WHERE id=?",(iso(utc_now()),res['id']))
                    db.execute("INSERT INTO inventory_movements(variant_id,delta,reason,reference_type,reference_id,created_by) VALUES(?,?,'cancelación antes de consumo','order',?,?)",(res['variant_id'],res['quantity'],row['id'],user['id']))
            db.execute(f'UPDATE {table} SET operational_status=?,{date_field}=?,updated_at=?,version=version+1 WHERE id=?',(status,date,iso(utc_now()),row['id']))
            if kind=='quote' and 'internal_notes' in data:
                internal=str(data['internal_notes'])
                if len(internal)>10000: raise ValueError('Notas internas demasiado extensas.')
                db.execute('UPDATE quote_requests SET internal_notes=? WHERE id=?',(self._cipher().encrypt(internal,aad='quote-notes'),row['id']))
            event_notes = notes + (f' · Fecha: {date or "sin compromiso"}' if date!=row[date_field] else '')
            self._event(db,kind,row['id'],before,status,user['id'],event_notes)
            self._audit(db,user,'correction' if correction else 'operation_update',kind,str(row['id']),{'before':before,'after':status,'date_before':row[date_field],'date_after':date,'notes':notes})
            self._notify(db,kind,row['id'],'Actualización · '+str(row['public_id'] or row['id'])+' · '+status)
        self._json({'ok':True})

    def _draft(self, data):
        payload = data.get('payload',{})
        if not isinstance(payload,dict) or len(json.dumps(payload))>50000:
            raise ValueError('Borrador demasiado grande.')
        with transaction(self.settings) as db:
            db.execute('INSERT INTO design_drafts VALUES(?,?,?,?) ON CONFLICT(owner) DO UPDATE SET payload_json=excluded.payload_json,expires_at=excluded.expires_at',(self._owner(),(self._current_user() or {}).get('id'),self._cipher().encrypt(json.dumps(payload),aad='draft'),iso(utc_now()+timedelta(days=7))))
        self._json({'ok':True,'expires_days':7})

    def _upload_start(self, data):
        size = data.get('size')
        maximum = int(os.getenv('TIPS_DESIGN_MAX_IMAGE_BYTES',20*1024*1024))
        if type(size)!=int or not 1<=size<=maximum:
            raise ValueError(f'Cada fotografía admite hasta {maximum//1048576} MB.')
        owner = self._owner()
        with transaction(self.settings) as db:
            # Los archivos temporales y borradores caducados se purgan sin tocar expedientes enviados.
            db.execute('DELETE FROM design_uploads WHERE quote_id IS NULL AND expires_at<?',(iso(utc_now()),))
            db.execute('DELETE FROM design_drafts WHERE expires_at<?',(iso(utc_now()),))
            usage = db.execute('SELECT COUNT(*),COALESCE(SUM(expected_bytes),0) FROM design_uploads WHERE owner=? AND quote_id IS NULL',(owner,)).fetchone()
            if usage[0]>=20 or usage[1]+size>200*1024*1024:
                raise ValueError('Límite temporal: 20 fotografías o 200 MB. Elimina las que no necesitas.')
            fid = secrets.token_urlsafe(24)
            name = str(data.get('name','fotografía'))[:150]
            db.execute('INSERT INTO design_uploads(id,owner,user_id,name,expected_bytes,created_at,expires_at) VALUES(?,?,?,?,?,?,?)',(fid,owner,(self._current_user() or {}).get('id'),name,size,iso(utc_now()),iso(utc_now()+timedelta(days=7))))
        self._json({'id':fid,'offset':0})

    def _upload_chunk(self, data):
        try:
            raw = base64.b64decode(data.get('data',''),validate=True)
        except Exception:
            raise ValueError('Bloque de archivo inválido.')
        if not 0<len(raw)<=256*1024 or type(data.get('offset'))!=int:
            raise ValueError('Bloque de archivo demasiado grande o posición inválida.')
        with transaction(self.settings) as db:
            row = db.execute('SELECT * FROM design_uploads WHERE id=? AND owner=? AND quote_id IS NULL AND expires_at>?',(data.get('id'),self._owner(),iso(utc_now()))).fetchone()
            if not row:
                raise ValueError('Carga no encontrada o caducada.')
            if data['offset']!=row['received_bytes']:
                return self._json({'id':row['id'],'offset':row['received_bytes'],'completed':bool(row['completed'])})
            combined = bytes(row['data'])+raw
            if len(combined)>row['expected_bytes']:
                raise ValueError('El archivo excede el tamaño declarado.')
            done = len(combined)==row['expected_bytes']
            thumb = None
            mime = None
            if done:
                try:
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter('error',Image.DecompressionBombWarning)
                        image = Image.open(io.BytesIO(combined))
                        if image.format not in {'JPEG','PNG','WEBP'} or image.width*image.height>40_000_000:
                            raise ValueError('Formato o dimensiones no admitidos. Usa JPEG, PNG o WebP de hasta 40 megapíxeles.')
                        mime = Image.MIME[image.format]
                        image.verify()
                        image = ImageOps.exif_transpose(Image.open(io.BytesIO(combined))).convert('RGB')
                        image.thumbnail((480,480))
                        out = io.BytesIO(); image.save(out,'JPEG',quality=80); thumb=out.getvalue()
                except (UnidentifiedImageError,OSError,Image.DecompressionBombError,Image.DecompressionBombWarning):
                    raise ValueError('El archivo no es una fotografía válida.')
            db.execute('UPDATE design_uploads SET data=?,received_bytes=?,completed=?,mime=?,thumbnail=? WHERE id=?',(combined,len(combined),int(done),mime,thumb,row['id']))
        self._json({'id':row['id'],'offset':len(combined),'completed':done})

    def _upload_delete(self,data):
        with transaction(self.settings) as db:
            db.execute('DELETE FROM design_uploads WHERE id=? AND owner=? AND quote_id IS NULL',(data.get('id'),self._owner()))
        self._json({'ok':True})

    def _notification_read(self,data):
        user = self._current_user()
        if not user:
            return self._json({'error':'Autenticación requerida.'},HTTPStatus.UNAUTHORIZED)
        with transaction(self.settings) as db:
            db.execute('INSERT OR IGNORE INTO notification_reads SELECT id,? FROM notifications WHERE id=? AND user_id=?',(user['id'],data.get('id'),user['id']))
        self._json({'ok':True})

    def _receipt(self,data):
        user=self._require_admin()
        if not user: return
        amount=data.get('amount_cents'); key=str(data.get('idempotency_key',''))
        if type(amount)!=int or amount==0 or abs(amount)>100000000 or not re.fullmatch(r'[\w-]{16,100}',key) or not str(data.get('notes','')).strip():
            raise ValueError('Indica importe no nulo, concepto y clave de reintento.')
        with transaction(self.settings) as db:
            row=db.execute('SELECT * FROM orders WHERE id=?',(data.get('id'),)).fetchone()
            if not row: raise ValueError('Pedido no encontrado.')
            old=db.execute('SELECT * FROM manual_receipts WHERE request_key=?',(key,)).fetchone()
            if old:
                if old['order_id']!=row['id'] or old['amount_cents']!=amount: raise LookupError('Clave de cobro reutilizada.')
                return self._json({'ok':True})
            total=db.execute('SELECT COALESCE(SUM(amount_cents),0) FROM manual_receipts WHERE order_id=?',(row['id'],)).fetchone()[0]
            if not 0<=total+amount<=row['total_cents']: raise ValueError('El saldo debe permanecer entre cero y el total. Usa un ajuste negativo para corregir un cobro.')
            db.execute('INSERT INTO manual_receipts(order_id,amount_cents,method,notes,actor_id,request_key,created_at) VALUES(?,?,?,?,?,?,?)',(row['id'],amount,str(data.get('method','presencial'))[:80],str(data['notes'])[:1000],user['id'],key,iso(utc_now())))
            self._audit(db,user,'manual_receipt','order',str(row['id']),{'amount_cents':amount,'notes':str(data['notes'])[:1000]})
        self._json({'ok':True})

    def _record(self,db,kind,row,admin=False):
        r=dict(row)
        r['kind']=kind
        r['status']=r.pop('operational_status')
        r.pop('tracking_hash',None)
        r.pop('shipping_address_json',None)
        cipher=self._cipher()
        if kind=='order':
            r['phone']=cipher.decrypt(r['phone'],aad='order-phone') or ''
            r['notes']=cipher.decrypt(r['notes'],aad='order-notes') or ''
            r['items']=[dict(i) for i in db.execute('SELECT product_name,quantity,unit_price_cents,customization_json FROM order_items WHERE order_id=?',(r['id'],))]
            r['collected_cents']=db.execute('SELECT COALESCE(SUM(amount_cents),0) FROM manual_receipts WHERE order_id=?',(r['id'],)).fetchone()[0]
            r['legacy_payments']=[dict(p) for p in db.execute('SELECT provider,status,amount_cents,created_at FROM payments WHERE order_id=?',(r['id'],))] if admin else []
            if admin:
                r['receipts']=[dict(p) for p in db.execute('SELECT amount_cents,method,notes,actor_id,created_at FROM manual_receipts WHERE order_id=? ORDER BY id',(r['id'],))]
        else:
            for key,aad in [('phone','quote-phone'),('contact','quote-contact'),('message','quote-message'),('internal_notes','quote-notes')]:
                r[key]=cipher.decrypt(r.get(key),aad=aad) or ''
            if not admin: r.pop('internal_notes',None)
            r['files']=[dict(f) for f in db.execute('SELECT id,name,mime,expected_bytes FROM design_uploads WHERE quote_id=? AND completed=1',(r['id'],))]
        r['history']=[dict(e) for e in db.execute('SELECT e.old_status,e.new_status,e.notes,e.created_at,e.actor_id,u.display_name AS actor_name FROM operation_events e LEFT JOIN users u ON u.id=e.actor_id WHERE e.kind=? AND e.record_id=? ORDER BY e.id',(kind,r['id']))]
        if not admin:
            for event in r['history']:
                event.pop('actor_id')
                event.pop('actor_name')
        r['next_states']=(ORDER_NEXT if kind=='order' else QUOTE_NEXT).get(r['status'],[])
        return r

    def _admin_users(self,user):
        with connect(self.settings) as db:
            rows=[dict(r) for r in db.execute("""SELECT u.id,u.email,u.display_name,u.role,u.must_change_password,u.two_factor_enabled,u.is_active,u.failed_login_count,u.locked_until,u.created_at,u.updated_at,
                COALESCE(o.order_count,0) order_count,COALESCE(o.order_total_cents,0) order_total_cents,COALESCE(q.quote_count,0) quote_count
                FROM users u LEFT JOIN (SELECT user_id,COUNT(*) order_count,SUM(total_cents) order_total_cents FROM orders GROUP BY user_id) o ON o.user_id=u.id
                LEFT JOIN (SELECT user_id,COUNT(*) quote_count FROM quote_requests GROUP BY user_id) q ON q.user_id=u.id
                ORDER BY u.created_at DESC,u.id DESC""")]
        self._json({'user':user,'items':rows})

    def _admin_orders(self,user):
        with connect(self.settings) as db:
            items=[self._record(db,'order',r,True) for r in db.execute('SELECT * FROM orders ORDER BY id DESC LIMIT 200')]
        self._json({'user':user,'items':items})

    def _admin_quotes(self,user):
        with connect(self.settings) as db:
            items=[self._record(db,'quote',r,True) for r in db.execute('SELECT * FROM quote_requests ORDER BY id DESC LIMIT 200')]
        self._json({'user':user,'items':items})

    def _ops_get(self,path,q):
        user=self._current_user()
        admin=bool(user and user['role'] in {'admin','superadmin'} and not user.get('must_change_password'))
        if path=='/api/ops/draft':
            with connect(self.settings) as db:
                row=db.execute('SELECT * FROM design_drafts WHERE owner=? AND expires_at>?',(self._owner(),iso(utc_now()))).fetchone()
                files=[dict(r) for r in db.execute('SELECT id,name,received_bytes,expected_bytes,completed FROM design_uploads WHERE owner=? AND quote_id IS NULL AND expires_at>?',(self._owner(),iso(utc_now())))]
            return self._json({'payload':json.loads(self._cipher().decrypt(row['payload_json'],aad='draft')) if row else {},'files':files})
        if path=='/api/ops/notifications':
            if not user: return self._json({'items':[],'unread':0})
            self._deliver_notifications()
            with transaction(self.settings) as db:
                if admin: self._reminders(db,user)
                count=db.execute('SELECT COUNT(*) FROM notifications n WHERE n.user_id=? AND NOT EXISTS(SELECT 1 FROM notification_reads nr WHERE nr.notification_id=n.id AND nr.user_id=?)',(user['id'],user['id'])).fetchone()[0]
                rows=[dict(r) for r in db.execute('SELECT n.*,EXISTS(SELECT 1 FROM notification_reads r WHERE r.notification_id=n.id AND r.user_id=?) AS is_read FROM notifications n WHERE n.user_id=? ORDER BY id DESC LIMIT 100',(user['id'],user['id']))]
            return self._json({'items':rows,'unread':count})
        if path=='/api/ops/records':
            if not user: return self._json({'error':'Autenticación requerida.'},HTTPStatus.UNAUTHORIZED)
            kind=q.get('kind',['order'])[0]
            table='orders' if kind=='order' else 'quote_requests' if kind=='quote' else None
            if not table: raise ValueError('Tipo inválido.')
            page = int(q.get('page', ['1'])[0])
            if not 1 <= page <= 1_000_000:
                raise ValueError('Página fuera de rango.')
            search = q.get('search', [''])[0][:120]
            state = q.get('status', [''])[0]
            where=' WHERE 1=1'; args=[]
            if not admin: where+=' AND user_id=?'; args.append(user['id'])
            if admin and q.get('client'):
                where+=' AND user_id=?';args.append(int(q['client'][0]))
            if state: where+=' AND operational_status=?';args.append(state)
            if search:
                where+=' AND (public_id LIKE ? OR '+('customer_name' if kind=='order' else 'name')+' LIKE ?)'; args.extend(['%'+search+'%']*2)
            for param,op in [('from','>='),('to','<=')]:
                if q.get(param):
                    where+=f' AND created_at {op} ?';args.append(self._date(q[param][0]))
            with connect(self.settings) as db:
                count=db.execute(f'SELECT COUNT(*) FROM {table}'+where,args).fetchone()[0]
                # Listados mínimos; los expedientes completos se cargan al abrir cada registro.
                fields='id,public_id,operational_status AS status,version,created_at,updated_at,'+('customer_name AS name,total_cents,confirmed_pickup AS due_at' if kind=='order' else 'name,project_type,due_at,phone')
                rows=[dict(r) for r in db.execute(f'SELECT {fields} FROM {table}'+where+' ORDER BY id DESC LIMIT 30 OFFSET ?',(*args,(page-1)*30))]
                if kind=='quote':
                    for r in rows:
                        r['phone']=self._cipher().decrypt(r['phone'],aad='quote-phone') or ''
                        r['files_count']=db.execute('SELECT COUNT(*) FROM design_uploads WHERE quote_id=? AND completed=1',(r['id'],)).fetchone()[0]
            return self._json({'items':rows,'total':count,'page':page,'page_size':30})
        if path=='/api/ops/detail' or path.startswith('/api/ops/file/'):
            file=None
            with connect(self.settings) as db:
                kind=q.get('kind',['order'])[0]; rid=q.get('id',[''])[0]
                if path.startswith('/api/ops/file/'):
                    fid=path.rsplit('/',1)[-1]
                    file=db.execute('SELECT * FROM design_uploads WHERE id=? AND completed=1',(fid,)).fetchone()
                    if not file: return self._json({'error':'Archivo no encontrado.'},HTTPStatus.NOT_FOUND)
                    if file['quote_id'] is None:
                        if file['expires_at'] <= iso(utc_now()) or file['owner'] != self._owner(): return self._json({'error':'Archivo no encontrado.'},HTTPStatus.NOT_FOUND)
                        return self._file_response(file,q)
                    kind='quote';rid=file['quote_id']
                table='orders' if kind=='order' else 'quote_requests' if kind=='quote' else None
                if not table: raise ValueError('Tipo inválido.')
                row=db.execute(f'SELECT * FROM {table} WHERE id=?',(rid,)).fetchone()
                token=q.get('token',[''])[0]
                allowed=row and (admin or (user and row['user_id']==user['id']) or (token and row['tracking_hash'] and secrets.compare_digest(digest(token),row['tracking_hash'])))
                if not allowed: return self._json({'error':'Registro no encontrado o enlace privado inválido.'},HTTPStatus.NOT_FOUND)
                if file: return self._file_response(file,q)
                result=self._record(db,kind,row,admin)
                settings={r['key']:json.loads(r['value_json']) for r in db.execute('SELECT key,value_json FROM site_settings WHERE is_public=1')}
            return self._json({'record':result,'business':settings})
        if path in {'/api/ops/dashboard','/api/ops/calendar','/api/ops/activity','/api/ops/reports'}:
            if not admin: return self._json({'error':'Administración requerida.'},HTTPStatus.FORBIDDEN)
            with connect(self.settings) as db:
                if path=='/api/ops/activity':
                    rows=[dict(r) for r in db.execute('SELECT a.*,u.display_name AS actor FROM audit_logs a LEFT JOIN users u ON u.id=a.actor_user_id ORDER BY a.id DESC LIMIT 500')]
                    return self._json({'items':rows})
                if path=='/api/ops/calendar':
                    rows=[dict(r) for r in db.execute("SELECT id,public_id,customer_name AS name,confirmed_pickup AS date,'order' AS kind FROM orders WHERE confirmed_pickup IS NOT NULL AND operational_status NOT IN('cancelled','completed') UNION ALL SELECT id,public_id,name,due_at AS date,'quote' AS kind FROM quote_requests WHERE due_at IS NOT NULL AND operational_status NOT IN('cancelled','closed') ORDER BY date")]
                    return self._json({'items':rows})
                start=self._date(q.get('from',[''])[0]);end=self._date(q.get('to',[''])[0])
                clause=' WHERE (? IS NULL OR created_at>=?) AND (? IS NULL OR created_at<=?)';args=(start,start,end,end)
                counts={kind:{r[0]:r[1] for r in db.execute(f'SELECT operational_status,COUNT(*) FROM {table}'+clause+' GROUP BY operational_status',args)} for kind,table in [('order','orders'),('quote','quote_requests')]}
                amounts=db.execute('SELECT COALESCE(SUM(total_cents),0) FROM orders'+clause,args).fetchone()[0]
                receipts=db.execute('SELECT COALESCE(SUM(amount_cents),0) FROM manual_receipts'+clause,args).fetchone()[0]
                overdue=db.execute("SELECT COUNT(*) FROM orders WHERE confirmed_pickup<? AND operational_status NOT IN('completed','cancelled')",(iso(utc_now()),)).fetchone()[0]
                top=[dict(r) for r in db.execute('SELECT i.product_name,SUM(i.quantity) AS quantity FROM order_items i JOIN orders o ON o.id=i.order_id WHERE o.operational_status<>\'cancelled\' AND (? IS NULL OR o.created_at>=?) AND (? IS NULL OR o.created_at<=?) GROUP BY i.product_name ORDER BY quantity DESC LIMIT 10',args)]
                avg=db.execute("SELECT AVG((julianday(e.first_at)-julianday(o.created_at))*24) FROM orders o JOIN (SELECT record_id,MIN(created_at) first_at FROM operation_events WHERE kind='order' AND old_status IS NOT NULL GROUP BY record_id) e ON e.record_id=o.id"+clause.replace('created_at','o.created_at'),args).fetchone()[0]
                latest=[dict(r) for r in db.execute("SELECT id,public_id,created_at,customer_name AS name,operational_status AS status,'order' AS kind FROM orders ORDER BY id DESC LIMIT 8")]
                latest += [dict(r) for r in db.execute("SELECT id,public_id,created_at,name,operational_status AS status,'quote' AS kind FROM quote_requests ORDER BY id DESC LIMIT 8")]
            return self._json({'counts':counts,'order_amount_cents':amounts,'manual_collected_cents':receipts,'overdue_orders':overdue,'average_first_response_hours':avg,'top_products':top,'latest':latest})
        self._json({'error':'Ruta no encontrada.'},HTTPStatus.NOT_FOUND)

    def _file_response(self,row,q):
        thumb=q.get('thumbnail',[''])[0]=='1'
        content=bytes(row['thumbnail'] if thumb else row['data'])
        self.send_response(200)
        self.send_header('Content-Type','image/jpeg' if thumb else row['mime'])
        self.send_header('Content-Length',str(len(content)))
        self.send_header('Cache-Control','private, no-store')
        self.send_header('Content-Disposition','inline; filename="reference'+('.jpg' if thumb else {'image/png':'.png','image/jpeg':'.jpg','image/webp':'.webp'}[row['mime']])+'"')
        self.end_headers();self.wfile.write(content)

    def _reminders(self,db,user):
        now=iso(utc_now()); stale=iso(utc_now()-timedelta(days=3))
        rows=db.execute("SELECT id,public_id,operational_status FROM orders WHERE (confirmed_pickup IS NOT NULL AND confirmed_pickup<=? AND operational_status NOT IN('completed','cancelled')) OR (operational_status='ready' AND updated_at<?)",(now,stale)).fetchall()
        for r in rows:
            db.execute('INSERT OR IGNORE INTO notifications(user_id,admin_only,event_key,title,url,created_at) VALUES(?,1,?,?,?,?)',(user['id'],f'due:order:{r["id"]}:{now[:10]}','Compromiso pendiente · '+r['public_id'],f'/admin/trabajo.html?kind=order&id={r["id"]}',now))
        for r in db.execute("SELECT id,public_id FROM quote_requests WHERE due_at<=? AND operational_status NOT IN('closed','cancelled')",(now,)):
            db.execute('INSERT OR IGNORE INTO notifications(user_id,admin_only,event_key,title,url,created_at) VALUES(?,1,?,?,?,?)',(user['id'],f'due:quote:{r["id"]}:{now[:10]}','Seguimiento de diseño pendiente · '+str(r['public_id'] or r['id']),f'/admin/trabajo.html?kind=quote&id={r["id"]}',now))
