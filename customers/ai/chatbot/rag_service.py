from functools import lru_cache
import numpy as np
from customers.models import MenuItem,Category,Combo,Promotion,RestaurantInfo
from customers.ai.artifacts import root,new_version,publish,write_json,read_json,latest,sha256
from .answer_guard import NO_DATA
from .reranker import rerank

@lru_cache(maxsize=1)
def embedder():
    from pathlib import Path
    manifest=read_json(root()/'pretrained'/'manifest.json')
    if 'embedding' not in manifest: raise ValueError('Chưa tải embedding; chạy download_ai_models.')
    path=Path(manifest['embedding'].get('local_path',str(root()/'pretrained'/'embedding')))
    if not path.exists(): raise ValueError('Chưa tải embedding; chạy download_ai_models.')
    for name,expected in manifest['embedding']['files'].items():
        if sha256(path/name)!=expected: raise ValueError('Embedding hash mismatch: '+name)
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(str(path),device='cpu',local_files_only=True)

def documents():
    docs=[]
    def add(kind,pk,title,content,updated=None,metadata=None):
        if content.strip(): docs.append({'source_type':kind,'source_id':pk,'title':title,'content':content,'updated_at':updated.isoformat() if updated else None,'metadata':metadata or {}})
    for m in MenuItem.objects.filter(is_available=True,category__is_active=True).select_related('category'):
        add('MENU_ITEM',m.pk,m.name,f'{m.name}. Nhóm: {m.category.name}. {m.description}',m.updated_at)
    for c in Category.objects.filter(is_active=True): add('CATEGORY',c.pk,c.name,c.name)
    for c in Combo.objects.filter(is_active=True): add('COMBO',c.pk,c.name,c.description,c.updated_at)
    from django.utils import timezone
    now=timezone.now()
    for p in Promotion.objects.filter(is_active=True,start_at__lte=now,end_at__gte=now):
        add('PROMOTION',p.pk,p.name,f'{p.name}. Mã ưu đãi: {p.code}. Điều kiện và số lượt còn lại cần kiểm tra trực tiếp tại thời điểm hỏi.',metadata={'live_tool':'get_current_promotions'})
    for info in RestaurantInfo.objects.filter(is_active=True): add('RESTAURANT_INFO',info.pk,info.name,info.description,info.updated_at)
    # Policies grounded in existing business code; no invented fees/refunds.
    policies=[
        ('BOOKING_POLICY','booking-window','Đặt bàn','Đặt bàn cần đăng nhập, ngày và giờ trong tương lai, từ 1 đến 20 khách, tên và số điện thoại hợp lệ. Khung giữ bàn mặc định là 120 phút.','customers/booking_service.py'),
        ('BOOKING_POLICY','booking-cancel','Hủy đặt bàn','Bạn có thể hủy đặt bàn của mình khi hệ thống cho phép chuyển trạng thái. Đặt bàn đã mở đơn hàng không thể tự hủy; hãy nhắn nhân viên hỗ trợ.','customers/booking_service.py'),
        ('PAYMENT_POLICY','payment-confirm','Thanh toán','Khách có thể xem hóa đơn của mình và báo đã thanh toán. Nhân viên xác nhận thanh toán; không suy đoán trạng thái từ thông báo của khách.','customers/payment_service.py'),
        ('WEBSITE_GUIDE','cart','Giỏ món','Mở Thực đơn, chọn món và thêm vào giỏ. Kiểm tra giỏ món rồi mở Đặt bàn để gửi thông tin đặt bàn và món chọn trước.','customers/views.py'),
        ('WEBSITE_GUIDE','support','Nhắn nhân viên','Mở Nhắn nhân viên để trao đổi với bộ phận hỗ trợ. Trợ lý AI và trò chuyện với nhân viên là hai chức năng riêng.','customers/module07_views.py'),
        ('WEBSITE_GUIDE','order','Theo dõi đơn hàng','Đăng nhập và mở Lịch sử mua hàng để xem đơn của mình. Mở Hóa đơn của tôi để xem thông tin thanh toán.','customers/module07_views.py'),
    ]
    from django.conf import settings
    for kind,pk,title,content,source in policies:
        add(kind,pk,title,content,metadata={'code_source':source,'code_sha256':sha256(settings.BASE_DIR/source)})
    # A document can produce several bounded chunks; preserve source identity.
    chunks=[]
    for doc in docs:
        content=doc['content']; position=0
        while position<len(content):
            chunks.append({**doc,'content':content[position:position+700],'chunk_id':len(chunks)})
            position+=600
    return docs,chunks

def rebuild():
    import faiss
    docs,chunks=documents()
    if not chunks: raise ValueError('Chưa có tài liệu công khai để index.')
    model=embedder(); vectors=model.encode([d['title']+' '+d['content'] for d in chunks],normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False).astype('float32')
    index=faiss.IndexFlatIP(vectors.shape[1]); index.add(vectors)
    folder=new_version('chatbot'); (folder/'index.faiss').write_bytes(faiss.serialize_index(index).tobytes()); write_json(folder/'chunks.json',chunks)
    manifest=read_json(root()/'pretrained'/'manifest.json')
    return publish(folder,{'model_name':manifest['embedding']['model_name'],'model_revision':manifest['embedding']['revision'],'device':'cpu','documents':len(docs),'chunks':len(chunks),'features':['normalized multilingual embeddings','FAISS inner product','BM25 lexical reranking'],'hyperparameters':{'top_k':10,'context_k':3,'semantic_threshold':.42,'reranker_weights':[.65,.25,.1]},'index_sha256':sha256(folder/'index.faiss'),'chunks_sha256':sha256(folder/'chunks.json'),'reranker':'0.65 semantic + 0.25 normalized BM25 + 0.10 token coverage'})

@lru_cache(maxsize=2)
def load_index(version):
    import faiss
    folder=root()/'chatbot'/version; meta=read_json(folder/'metadata.json')
    if sha256(folder/'index.faiss')!=meta['index_sha256'] or sha256(folder/'chunks.json')!=meta['chunks_sha256']: raise ValueError('RAG artifact hash mismatch.')
    index=faiss.deserialize_index(np.frombuffer((folder/'index.faiss').read_bytes(),dtype=np.uint8).copy())
    return index,read_json(folder/'chunks.json'),meta

def retrieve(question,k=10):
    import re
    # Remove polite filler before semantic search; keep all substantive entities.
    question=re.sub(r'\s+(nhé|vui lòng|giúp tôi|ạ)[.!?]*$','',question,flags=re.IGNORECASE).strip()
    folder=latest('chatbot'); index,chunks,meta=load_index(folder.name)
    query=embedder().encode([question],normalize_embeddings=True,convert_to_numpy=True).astype('float32')
    scores,ids=index.search(query,min(k,len(chunks)))
    docs=[chunks[int(i)] for i in ids[0] if i>=0]; values=[float(s) for s,i in zip(scores[0],ids[0]) if i>=0]
    return rerank(question,docs,values),meta

def answer(question,intent):
    try: rows,meta=retrieve(question)
    except (ValueError,OSError,ImportError): return grounded_fallback(question,intent)
    allowed={'BOOKING_POLICY':{'BOOKING_POLICY'},'WEBSITE_HELP':{'WEBSITE_GUIDE'},'POLICY':{'BOOKING_POLICY','PAYMENT_POLICY'},'FAQ':{'WEBSITE_GUIDE','BOOKING_POLICY','PAYMENT_POLICY'}}.get(intent)
    rows=[r for r in rows if r['semantic_score']>=meta['hyperparameters']['semantic_threshold'] and (allowed is None or r['source_type'] in allowed)][:3]
    if intent=='UNKNOWN':
        from .intent_router import normalize
        stop={'nha','hang','co','khong','toi','cho','hoi','la','gi','cua','mot','nao','duoc','hay','ve','nhe','vui','long','dich','vu'}
        terms=set(normalize(question).replace('?','').split())-stop
        rows=[r for r in rows if terms and len(terms & set(normalize(r['title']+' '+r['content']).split()))/len(terms)>=.6 and r['semantic_score']>=.55]
    if not rows: return {'answer':NO_DATA,'tool':'rag_retrieval','sources':[]}
    # Extractive answer: no external LLM or unsupported generated facts.
    chosen=rows[0]
    return {'answer':chosen['content'],'tool':'rag_retrieval','sources':[{'source_type':chosen['source_type'],'source_id':chosen['source_id'],'title':chosen['title'],'chunk_id':chosen['chunk_id']}],'retrieved':[r['chunk_id'] for r in rows]}


def grounded_fallback(question,intent):
    """Extract only a matching code-backed policy; never pretend semantic RAG ran."""
    from .intent_router import normalize
    text=normalize(question)
    key=None
    if 'dat ban' in text and intent in ('BOOKING_POLICY','POLICY','FAQ','UNKNOWN'):
        key='booking-cancel' if 'huy' in text else 'booking-window'
    elif intent=='WEBSITE_HELP':
        key='cart' if 'gio' in text else 'support' if 'nhan' in text else 'order' if 'don' in text else None
    elif intent=='POLICY' and 'thanh toan' in text:
        key='payment-confirm'
    if key:
        docs,_=documents()
        chosen=next((row for row in docs if row['source_id']==key),None)
        if chosen:
            return {'answer':chosen['content'],'tool':'grounded_policy_fallback','semantic_ready':False,
                'sources':[{'source_type':chosen['source_type'],'source_id':key,'title':chosen['title']} ]}
    return {'answer':NO_DATA,'tool':'rag_retrieval','semantic_ready':False,'sources':[]}
