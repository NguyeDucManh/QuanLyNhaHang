"""CI-only ASGI wrapper: real Django/Daphne plus a tensor diagnostic, no identity bypass."""
from restaurant_system.asgi import application as django_application
from django.conf import settings
assert settings.DATABASES['default']['NAME']=='restaurant_ci512'

async def application(scope,receive,send):
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
