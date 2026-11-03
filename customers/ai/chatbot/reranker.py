import numpy as np
from rank_bm25 import BM25Okapi
from .intent_router import normalize

def rerank(query,documents,semantic_scores):
    tokens=[normalize(d['content']+' '+d['title']).split() for d in documents]
    if not tokens: return []
    lexical=np.maximum(0,BM25Okapi(tokens).get_scores(normalize(query).split()))
    lexical=lexical/max(float(lexical.max()),1e-9)
    q=set(normalize(query).split())
    ranked=[]
    for i,doc in enumerate(documents):
        coverage=len(q & set(tokens[i]))/max(1,len(q))
        score=.65*max(0,float(semantic_scores[i]))+.25*float(lexical[i])+.1*coverage
        ranked.append({**doc,'semantic_score':float(semantic_scores[i]),'rerank_score':score})
    return sorted(ranked,key=lambda d:d['rerank_score'],reverse=True)
