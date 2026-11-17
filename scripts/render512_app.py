"""CI-only ASGI wrapper: real Django/Daphne plus a tensor diagnostic, no identity bypass."""
from restaurant_system.asgi import application as django_application
from django.conf import settings
assert settings.DATABASES['default']['NAME']=='restaurant_ci512'

async def application(scope,receive,send):
    if scope['type']=='http' and scope['path']=='/__ci_face_sample':
        import asyncio,json,time
        body=b''
        while True:
            message=await receive();body+=message.get('body',b'')
            assert len(body)<1500000,'CI sample payload too large'
            if not message.get('more_body'):break
        frame=json.loads(body)['frame']
        def sample_probe():
            from customers.ai.face.facenet_service import engine
            import numpy as np
            net=engine();results=[]
            for count in (5,25):
                started=time.perf_counter();reference=None
                for _ in range(count):
                    vector,quality,_=net.process(frame)
                    assert len(vector)==128 and quality['faces']==1 and np.isfinite(vector).all()
                    if reference is None:reference=vector
                    assert float(np.dot(reference,vector))>.999
                results.append({'frames':count,'dimensions':128,'seconds':round(time.perf_counter()-started,3)})
            return {'detector_and_embedding_real':True,'public_test_fixture':True,
                'identity_test':False,'liveness_test':False,'batches':results,'model_version':net.model_version}
        result=await asyncio.to_thread(sample_probe)
        await send({'type':'http.response.start','status':200,'headers':[(b'content-type',b'application/json')]})
        await send({'type':'http.response.body','body':json.dumps(result).encode()})
        return
    if scope['type']=='http' and scope['path']=='/__ci_face_tensor':
        import asyncio,json,time
        def probe():
            from customers.ai.face.facenet_service import engine
            import numpy as np
            net=engine();started=time.perf_counter()
            for _ in range(25):
                vector=net.embedding(np.zeros((160,160,3),dtype=np.uint8))
                assert len(vector)==128
            return {'tensor_frames':25,'seconds':round(time.perf_counter()-started,3),'identity_test':False,'model_version':net.model_version}
        result=await asyncio.to_thread(probe)
        await send({'type':'http.response.start','status':200,'headers':[(b'content-type',b'application/json')]})
        await send({'type':'http.response.body','body':json.dumps(result).encode()})
        return
    await django_application(scope,receive,send)
