from collections import defaultdict
from datetime import datetime
import math
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

def interaction_score(row, reference):
    age=max(0,(reference-datetime.fromisoformat(row['at'])).total_seconds()/86400)
    return (1+math.log1p(row['quantity']))*(1+.125*(row.get('rating',3)-3))*math.exp(-math.log(2)*age/90)

def build_interaction_matrix(rows, item_ids, reference=None):
    users=sorted({r['customer_key'] for r in rows}); ids=list(item_ids)
    matrix=np.zeros((len(users),len(ids)),dtype=np.float64)
    uindex={u:i for i,u in enumerate(users)}; iindex={pk:i for i,pk in enumerate(ids)}
    reference=reference or max((datetime.fromisoformat(r['at']) for r in rows),default=datetime.now().astimezone())
    for row in rows:
        if row['menu_item_id'] in iindex: matrix[uindex[row['customer_key']],iindex[row['menu_item_id']]]+=interaction_score(row,reference)
    return users,ids,matrix

class CollaborativeService:
    def fit(self, rows, item_ids, reference=None):
        self.users,self.ids,self.matrix=build_interaction_matrix(rows,item_ids,reference)
        self.similarity=cosine_similarity(self.matrix.T) if len(self.users) else np.zeros((len(self.ids),len(self.ids)))
        np.fill_diagonal(self.similarity,0)
        return self

    def scores(self,key):
        if key not in self.users: return np.zeros(len(self.ids))
        history=self.matrix[self.users.index(key)]
        scores=history@self.similarity
        return scores/max(float(scores.max()),1e-12)

    def recommend_for_user(self,key,n=5):
        scores=self.scores(key)
        seen=set(np.flatnonzero(self.matrix[self.users.index(key)])) if key in self.users else set()
        return [self.ids[i] for i in sorted(range(len(self.ids)),key=lambda i:(i in seen,-scores[i],self.ids[i]))[:n]]

    def similar_items(self,pk,n=5):
        if pk not in self.ids: return []
        scores=self.similarity[self.ids.index(pk)]
        return [self.ids[i] for i in np.argsort(-scores) if self.ids[i]!=pk][:n]

def ranking_metrics(predicted,relevant,k=5):
    relevant=set(relevant); ranked=list(dict.fromkeys(predicted))[:k]
    hits=len(set(ranked)&relevant); precision=hits/k; recall=hits/len(relevant) if relevant else 0
    dcg=sum(1/math.log2(i+2) for i,pk in enumerate(ranked) if pk in relevant)
    ideal=sum(1/math.log2(i+2) for i in range(min(k,len(relevant))))
    return {'precision_at_5':precision,'recall_at_5':recall,'f1_at_5':2*precision*recall/(precision+recall) if precision+recall else 0,'ndcg_at_5':dcg/ideal if ideal else 0}

def temporal_split(rows):
    stamp=lambda row:datetime.fromisoformat(row['at']).timestamp()
    dates=sorted({stamp(r) for r in rows})
    if len(dates)<5: raise ValueError('Cần ít nhất 5 mốc thời gian để train/validation/test.')
    v=dates[max(1,int(len(dates)*.7))]; t=dates[max(2,int(len(dates)*.85))]
    return ([r for r in rows if stamp(r)<v],[r for r in rows if v<=stamp(r)<t],[r for r in rows if stamp(r)>=t])
