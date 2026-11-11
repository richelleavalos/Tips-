"""Distribución durable de avisos internos, reutilizable desde HTTP y tareas periódicas."""
from .database import connect, transaction
from .server import iso, utc_now

class NotificationDispatcher:
    def __init__(self, settings):
        self.settings=settings

    def deliver(self):
        with connect(self.settings) as db:
            pending=[dict(r) for r in db.execute('SELECT * FROM notification_outbox WHERE delivered_at IS NULL ORDER BY id LIMIT 200')]
        for job in pending:
            try:
                with transaction(self.settings) as db:
                    live=db.execute('SELECT delivered_at FROM notification_outbox WHERE id=?',(job['id'],)).fetchone()
                    if not live or live[0]: continue
                    table='orders' if job['kind']=='order' else 'quote_requests'
                    row=db.execute(f'SELECT user_id FROM {table} WHERE id=?',(job['record_id'],)).fetchone()
                    targets=[(r['id'],1) for r in db.execute("SELECT id FROM users WHERE role IN('admin','superadmin') AND is_active=1")]
                    if row and row['user_id']: targets.append((row['user_id'],0))
                    for uid,admin in targets:
                        url=('/admin/trabajo.html' if admin else '/seguimiento.html')+f'?kind={job["kind"]}&id={job["record_id"]}'
                        event_key=f'{job["kind"]}:{job["record_id"]}:{job["version"]}'
                        db.execute('INSERT OR IGNORE INTO notifications(user_id,admin_only,event_key,title,url,created_at) VALUES(?,?,?,?,?,?)',(uid,admin,event_key,job['title'],url,job['created_at']))
                        account=db.execute('SELECT email,contact_preferences FROM users WHERE id=?',(uid,)).fetchone()
                        if account['contact_preferences']=='email':
                            nid=db.execute('SELECT id FROM notifications WHERE user_id=? AND event_key=?',(uid,event_key)).fetchone()[0]
                            db.execute('INSERT OR IGNORE INTO email_outbox(notification_id,recipient,subject,body) VALUES(?,?,?,?)',(nid,account['email'],job['title'],'Tienes una actualización de TIPS. Consulta tu cuenta: '+url))
                    db.execute('UPDATE notification_outbox SET delivered_at=?,attempts=attempts+1,last_error=NULL WHERE id=?',(iso(utc_now()),job['id']))
            except Exception:
                # La excepción nunca revierte pedidos ni fotografías ya confirmados.
                with transaction(self.settings) as db:
                    db.execute("UPDATE notification_outbox SET attempts=attempts+1,last_error='No se pudo repartir; se reintentará.' WHERE id=?",(job['id'],))

