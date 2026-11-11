"""Worker opcional SMTP; no se ejecuta al arrancar ni usa servicios de pago.
Ejecutar periódicamente solo con SMTP configurado por el operador.
"""
import os,sys,smtplib,ssl
from pathlib import Path
from email.message import EmailMessage
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.config import Settings
from backend.database import connect,transaction
from backend.server import iso,utc_now

def send():
    host=os.getenv('TIPS_SMTP_HOST');sender=os.getenv('TIPS_SMTP_FROM');base=os.getenv('TIPS_PUBLIC_URL','').rstrip('/')
    if not host or not sender or not base.startswith('https://'):raise SystemExit('Configura SMTP y TIPS_PUBLIC_URL=https://... antes de ejecutar.')
    settings=Settings.load()
    from backend.notifications import NotificationDispatcher
    NotificationDispatcher(settings).deliver()
    # Bloqueo de archivo independiente: nunca mantener una escritura SQLite durante red SMTP.
    from contextlib import contextmanager
    @contextmanager
    def worker_lock():
        lock=settings.database_path.with_suffix('.mail.lock')
        try: lock.mkdir()
        except FileExistsError: raise SystemExit('Worker activo o lock de un proceso interrumpido. Revisa antes de retirar el directorio .mail.lock.')
        try: yield
        finally: lock.rmdir()
    with worker_lock():
        from backend.security import FieldCipher
        with connect(settings) as db:
            jobs=[{**dict(r),'table':'email_outbox'} for r in db.execute('SELECT * FROM email_outbox WHERE sent_at IS NULL AND attempts<10 LIMIT 50')]
            for r in db.execute('SELECT * FROM auth_mail_outbox WHERE sent_at IS NULL AND attempts<10 AND expires_at>? LIMIT 50',(iso(utc_now()),)):
                job=dict(r);job['body']=FieldCipher(settings.field_encryption_key).decrypt(job['body'],aad='auth-mail');job['notification_id']='reset-'+str(job['id']);job['table']='auth_mail_outbox';jobs.append(job)
        for job in jobs:
            try:
                message=EmailMessage();message['From']=sender;message['To']=job['recipient'];message['Subject']=job['subject'];message['Message-ID']=f'<tips-notification-{job["notification_id"]}@{sender.split("@")[-1]}>';message.set_content(job['body'].replace('Consulta tu cuenta: /','Consulta tu cuenta: '+base+'/').replace('Abre /recuperar.html','Abre '+base+'/recuperar.html'))
                with smtplib.SMTP(host,int(os.getenv('TIPS_SMTP_PORT','587')),timeout=15) as smtp:
                    smtp.starttls(context=ssl.create_default_context())
                    if os.getenv('TIPS_SMTP_USER'):smtp.login(os.environ['TIPS_SMTP_USER'],os.environ['TIPS_SMTP_PASSWORD'])
                    smtp.send_message(message)
                with transaction(settings) as db:db.execute('UPDATE '+job['table']+' SET sent_at=?,attempts=attempts+1,last_error=NULL WHERE id=?',(iso(utc_now()),job['id']))
            except Exception:
                with transaction(settings) as db:db.execute("UPDATE "+job['table']+" SET attempts=attempts+1,last_error='Fallo SMTP; revisar configuración o proveedor.' WHERE id=?",(job['id'],))
if __name__=='__main__':send()
