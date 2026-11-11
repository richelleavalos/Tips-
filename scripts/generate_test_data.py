"""Dataset ficticio reproducible; destino restringido para proteger producción."""
import argparse,io,random,sys,json
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from backend.config import Settings
from backend.database import initialize,connect,transaction
from backend.security import hash_password,FieldCipher
PASSWORD='SoloPruebas2026!'
def generate(target,reset=False):
    target=Path(target).resolve()
    if target.name!='tips-test.db' or 'test-data' not in target.parts:raise SystemExit('Destino permitido: test-data/.../tips-test.db. Nunca data/tips.db.')
    if target.exists():
        if not reset:raise SystemExit('La base existe. --reset reinicia solo este dataset ficticio.')
        for p in [target,Path(str(target)+'-wal'),Path(str(target)+'-shm')]:p.unlink(missing_ok=True)
    settings=replace(Settings.load(),environment='test',database_path=target);initialize(settings)
    rng=random.Random(650);cipher=FieldCipher(settings.field_encryption_key);encoded=hash_password(PASSWORD);base=datetime(2026,8,1,tzinfo=timezone.utc)
    with transaction(settings) as db:
        admin=db.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()[0]
        users=[]
        for i in range(200):
            t=(base+timedelta(days=i%70)).isoformat()
            users.append(db.execute('INSERT INTO users(email,password_hash,display_name,phone,country_code,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(f'cliente{i:03}@tips.test',encoded,f'Cliente Ficticio {i:03}',cipher.encrypt('+5037'+str(1000000+i),aad='user-phone'),'+503',t,t)).lastrowid)
        variants=db.execute('SELECT v.*,p.name,p.base_price_cents FROM product_variants v JOIN products p ON p.id=v.product_id').fetchall()
        db.execute('UPDATE product_variants SET stock_quantity=1000 WHERE stock_quantity IS NOT NULL')
        im=Image.new('RGB',(1400,1000),(120,150,110));out=io.BytesIO();im.save(out,'JPEG',quality=90);raw=out.getvalue();im.thumbnail((480,480));out=io.BytesIO();im.save(out,'JPEG');thumb=out.getvalue()
        os=['received','confirmed','processing','ready','completed','cancelled'];qs=['received','reviewing','needs_info','qualified','closed','cancelled']
        for i in range(100):
            stamp=(base+timedelta(days=rng.randrange(100),hours=rng.randrange(24))).isoformat();uid=users[i];v=variants[i%len(variants)];qty=1+i%3;unit=v['price_cents'] if v['price_cents'] is not None else v['base_price_cents'];state='ready' if i==0 else os[i%6];due=(datetime.fromisoformat(stamp)+timedelta(days=7)).isoformat() if state!='received' else None
            customization=[]
            for c in db.execute("SELECT cv.id,cv.label,cv.price_delta_cents,c.name FROM product_customizations pc JOIN customizations c ON c.id=pc.customization_id JOIN customization_values cv ON cv.customization_id=c.id WHERE pc.product_id=? AND cv.is_active=1 GROUP BY c.id ORDER BY c.id",(v['product_id'],)):
                customization.append({'id':c['id'],'grupo':c['name'],'opcion':c['label'],'ajuste_centavos':c['price_delta_cents']})
                unit+=c['price_delta_cents']
            rid=db.execute("INSERT INTO orders(public_id,user_id,email,customer_name,phone,status,operational_status,subtotal_cents,total_cents,created_at,updated_at,confirmed_pickup,notes) VALUES(?,?,?,?,?,'pending_payment',?,?,?,?,?,?,?)",(f'TEST-PED-{i:04}',uid,f'cliente{i:03}@tips.test',f'Cliente Ficticio {i:03}',cipher.encrypt('+50371000000',aad='order-phone'),state,qty*unit,qty*unit,stamp,stamp,due,cipher.encrypt('Pedido ficticio de prueba',aad='order-notes'))).lastrowid
            db.execute('INSERT INTO order_items(order_id,variant_id,product_name,sku,quantity,unit_price_cents,customization_json) VALUES(?,?,?,?,?,?,?)',(rid,v['id'],v['name'],v['sku'],qty,unit,json.dumps(customization,ensure_ascii=False)))
            rs='released' if state=='cancelled' else 'consumed' if state in {'processing','ready','completed'} else 'reserved'
            if v['stock_quantity'] is not None:
                if rs!='released':db.execute('UPDATE product_variants SET stock_quantity=stock_quantity-? WHERE id=?',(qty,v['id']))
                db.execute('INSERT INTO inventory_reservations(order_id,variant_id,quantity,status,expires_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(rid,v['id'],qty,rs,'9999-12-31T00:00:00+00:00',stamp,stamp))
                db.execute("INSERT INTO inventory_movements(variant_id,delta,reason,reference_type,reference_id,created_by,created_at) VALUES(?,?,'dataset ficticio','order',?,?,?)",(v['id'],0 if rs=='released' else -qty,rid,admin,stamp))
            chain={'received':['received'],'confirmed':['received','confirmed'],'processing':['received','confirmed','processing'],'ready':['received','confirmed','processing','ready'],'completed':['received','confirmed','processing','ready','completed'],'cancelled':['received','cancelled']}[state]
            for j,s in enumerate(chain):db.execute("INSERT INTO operation_events(kind,record_id,actor_id,old_status,new_status,created_at) VALUES('order',?,?,?,?,?)",(rid,uid if j==0 else admin,chain[j-1] if j else None,s,(datetime.fromisoformat(stamp)+timedelta(hours=j)).isoformat()))
            db.execute('UPDATE orders SET version=?,updated_at=? WHERE id=?',(len(chain),(datetime.fromisoformat(stamp)+timedelta(hours=len(chain)-1)).isoformat(),rid))
            quote_state='reviewing' if i==0 else qs[i%6]
            qid=db.execute('INSERT INTO quote_requests(name,contact,project_type,message,user_id,phone,email,public_id,operational_status,created_at,updated_at,due_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(f'Cliente Ficticio {i:03}',cipher.encrypt('+50371000000',aad='quote-contact'),'Diseño de interiores',cipher.encrypt(f'Solicitud ficticia {i}. Renovar un espacio con iluminación y materiales naturales.',aad='quote-message'),uid,cipher.encrypt('+50371000000',aad='quote-phone'),f'cliente{i:03}@tips.test',f'TEST-DIS-{i:04}',quote_state,stamp,stamp,due)).lastrowid
            db.execute('INSERT INTO design_uploads(id,owner,user_id,quote_id,name,mime,expected_bytes,received_bytes,data,thumbnail,completed,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?)',(f'test-photo-{i:04}',f'u:{uid}',uid,qid,'espacio-ficticio.jpg','image/jpeg',len(raw),len(raw),raw,thumb,stamp,stamp))
            quote_chain={'received':['received'],'reviewing':['received','reviewing'],'needs_info':['received','reviewing','needs_info'],'qualified':['received','reviewing','qualified'],'closed':['received','reviewing','qualified','closed'],'cancelled':['received','cancelled']}[quote_state]
            for j,status in enumerate(quote_chain):
                db.execute("INSERT INTO operation_events(kind,record_id,actor_id,old_status,new_status,created_at) VALUES('quote',?,?,?,?,?)",(qid,uid if j==0 else admin,quote_chain[j-1] if j else None,status,(datetime.fromisoformat(stamp)+timedelta(hours=j)).isoformat()))
            db.execute('UPDATE quote_requests SET version=?,updated_at=? WHERE id=?',(len(quote_chain),(datetime.fromisoformat(stamp)+timedelta(hours=len(quote_chain)-1)).isoformat(),qid))
            for k,record in [('order',rid),('quote',qid)]:
                for recipient,ao in [(uid,0),(admin,1)]:db.execute('INSERT INTO notifications(user_id,admin_only,event_key,title,url,created_at) VALUES(?,?,?,?,?,?)',(recipient,ao,f'test:{k}:{record}','Actualización ficticia',('/admin/trabajo.html' if ao else '/seguimiento.html')+f'?kind={k}&id={record}',stamp))
                db.execute('INSERT INTO audit_logs(actor_user_id,action,entity_type,entity_id,metadata_json,created_at) VALUES(?,?,?,?,?,?)',(admin,'test_dataset',k,str(record),'{"fictitious":true}',stamp))
        db.execute('UPDATE users SET display_name=?,phone=? WHERE id=?',('Cliente Ficticio 000 · perfil actualizado',cipher.encrypt('+50370000000',aad='user-phone'),users[0]))
        for case in ['archivo_falso','doble_envio','sesion_caducada']:
            db.execute("INSERT INTO audit_logs(action,entity_type,entity_id,metadata_json) VALUES('test_fixture','edge_case',?,?)",(case,json.dumps({'expected':'rechazo o reintento controlado','fictitious':True})))
    with connect(settings) as db:
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        counts={t:db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ['users','orders','quote_requests','design_uploads','notifications','operation_events']}
    print(counts);print('Ambas modalidades: cliente000@tips.test / '+PASSWORD);return counts
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',default='test-data/tips-test.db');p.add_argument('--reset',action='store_true');a=p.parse_args();generate(a.output,a.reset)
