"""Disposable PostgreSQL smoke verification of the extracted clean source."""
import os,sys,json,uuid,io
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT));os.environ.setdefault('DJANGO_SETTINGS_MODULE','restaurant_system.settings')
def main():
    from django.conf import settings
    import psycopg
    from psycopg import sql
    db=settings.DATABASES['default'];name='sr_submission_verify_'+uuid.uuid4().hex[:12]
    conn=psycopg.connect(host=db['HOST'],port=db['PORT'],user=db['USER'],password=db['PASSWORD'],dbname='postgres',autocommit=True)
    conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)));settings.DATABASES['default']['NAME']=name
    result={'isolated_database':True,'source_root':str(ROOT),'fresh_pip_install':'NOT RUN; reused prepared interpreter, checked requirements compatibility','checks':[]}
    try:
        import django;django.setup()
        from django.core.management import call_command
        from django.test import Client
        from django.contrib.auth.models import User
        from customers.rbac import assign_role
        from django.test.utils import override_settings
        for command in ['check','migrate','seed_menu','seed_rbac']:
            call_command(command,stdout=io.StringIO(),verbosity=0);result['checks'].append(command+' PASS')
        with override_settings(ALLOWED_HOSTS=['testserver','localhost','127.0.0.1']):
            client=Client()
            for url in ['/','/login/','/register/','/menu/','/cart/']:
                response=client.get(url);assert response.status_code==200,(url,response.status_code);result['checks'].append(url+' HTTP200')
            user=User.objects.create_user('submission-qa-staff',password=uuid.uuid4().hex);assign_role(user,'STAFF');client.force_login(user)
            for url in ['/staff/','/work/','/work/faceid/','/account/','/ai/chat/']:
                response=client.get(url);assert response.status_code==200,(url,response.status_code);result['checks'].append(url+' HTTP200')
        from customers.ai.face.facenet_service import engine
        face=engine();assert face.session.get_providers()==['CPUExecutionProvider'];result['checks'].append('FaceNet/MediaPipe CPU initialization PASS; not biometric accuracy')
        from customers.ai.chatbot.rag_service import embedder
        model=embedder();vector=model.encode(['Thuc don nha hang'],normalize_embeddings=True);assert vector.shape==(1,384);result['checks'].append('Embedding CPU inference PASS')
        from customers.ai.artifacts import latest
        import faiss
        import numpy as np
        index=faiss.deserialize_index(np.frombuffer((latest('chatbot')/'index.faiss').read_bytes(),dtype='uint8'));assert index.d==384;result['checks'].append('FAISS packaged index PASS; Unicode Windows path via bytes')
        for kind in ['forecast','recommendation']:
            assert (latest(kind)/'metadata.json').exists();result['checks'].append(kind+' latest artifact PASS')
        result['success']=True
    finally:
        from django.db import connections
        connections.close_all();conn.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()',(name,));conn.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)));conn.close();result['QA_database_deleted']=True
        (ROOT/'submission_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))
if __name__=='__main__':main()
