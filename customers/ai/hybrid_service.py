from collections import defaultdict
from datetime import datetime
from customers.recommendation_service import item_vectors, valid, cold_start
from .research_data import dataset
from .artifacts import new_version, latest, publish, read_json, write_json

def content_scores(service,key,content):
    _offline_dependencies()
    if key not in service.users: return np.zeros(len(service.ids))
    history=service.matrix[service.users.index(key)]
    if not history.sum(): return np.zeros(len(service.ids))
    profile=np.asarray(content.T.dot(history)).ravel()/history.sum()
    result=cosine_similarity(profile.reshape(1,-1),content).ravel()
    return result/max(float(result.max()),1e-12)

def rank(items,scores,history,n=5):
    candidates=sorted((i for i,m in enumerate(items) if valid(m)),key=lambda i:(items[i].pk in history,-scores[i],items[i].pk))
    selected=[]; categories=defaultdict(int)
    # Greedy diversity penalty; prefer unseen items first.
    while candidates and len(selected)<n:
        unseen=[i for i in candidates if items[i].pk not in history]
        pool=unseen or candidates
        i=max(pool,key=lambda j:(scores[j]-.12*categories[items[j].category_id],-items[j].pk))
        selected.append(i); categories[items[i].category_id]+=1; candidates.remove(i)
    return selected

def evaluate(train,held,items,content,alpha):
    _offline_dependencies()
    service=CollaborativeService().fit(train,[m.pk for m in items])
    relevant=defaultdict(set)
    for row in held:
        if row['customer_key'] in service.users and row['menu_item_id'] in service.ids:
            relevant[row['customer_key']].add(row['menu_item_id'])
    metrics=[]; evaluated_keys=[]
    for key,truth in relevant.items():
        scores=alpha*service.scores(key)+(1-alpha)*content_scores(service,key,content)
        history={service.ids[i] for i in np.flatnonzero(service.matrix[service.users.index(key)])}
        truth={pk for pk in truth if any(m.pk==pk and valid(m) for m in items)}
        if not truth: continue
        predicted=[items[i].pk for i in rank(items,scores,history)]
        metrics.append(ranking_metrics(predicted,truth)); evaluated_keys.append(key)
    return {'users':len(metrics),'real_users':sum(key.startswith('real:') for key in evaluated_keys),'synthetic_users':sum(key.startswith('simulated:') for key in evaluated_keys),**{name:float(np.mean([m[name] for m in metrics])) if metrics else None for name in ['precision_at_5','recall_at_5','f1_at_5','ndcg_at_5']}}

def train():
    _offline_dependencies()
    rows,meta=dataset('interactions'); training,validation,test=temporal_split(rows)
    items,_,content,_=item_vectors()
    grid={str(a):evaluate(training,validation,items,content,a) for a in [.25,.5,.75]}
    if not any(m['users'] for m in grid.values()): raise ValueError('Không đủ user validation để chọn alpha.')
    alpha=max([.25,.5,.75],key=lambda a:((grid[str(a)]['ndcg_at_5'] or 0),-abs(a-.5)))
    final_train=training+validation
    metrics={name:evaluate(final_train,test,items,content,a) for name,a in [('Content-Based',0),('Collaborative',1),('Hybrid',alpha)]}
    folder=new_version('recommendation')
    # JSON sufficient to refit small item-item matrix safely; no pickle.
    write_json(folder/'interactions.json',rows)
    return publish(folder,{'dataset_version':meta['version'],'model_name':'item-item cosine + content hybrid','best_alpha':alpha,'features':['category','price_band','recipe_ingredients','quantity','rating','90-day half-life'],'hyperparameters':{'diversity_penalty':.12,'alpha_grid':[.25,.5,.75]},'validation':grid,'metrics':metrics,'train_range':[training[0]['at'],training[-1]['at']],'validation_range':[validation[0]['at'],validation[-1]['at']],'test_range':[test[0]['at'],test[-1]['at']],'data_provenance':meta,'interaction_formula':'(1 + ln(1 + quantity)) × (1 + 0.125 × (rating - 3)) × exp(-ln(2) × age_days/90)'})

def recommend(user=None,*,n=4,**kwargs):
    from .live_recommendation import recommend as live
    return live(user,n=n,**kwargs)

def _offline_dependencies():
    global np,cosine_similarity,CollaborativeService,ranking_metrics,temporal_split
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity
    from .collaborative_service import CollaborativeService,ranking_metrics,temporal_split
