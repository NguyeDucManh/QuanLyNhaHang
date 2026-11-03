import numpy as np

def confusion(genuine,impostor,threshold):
    tp=sum(s>=threshold for s in genuine); fn=len(genuine)-tp
    fp=sum(s>=threshold for s in impostor); tn=len(impostor)-fp
    precision=tp/(tp+fp) if tp+fp else 0; recall=tp/len(genuine) if genuine else 0
    return {'threshold':threshold,'accuracy':(tp+tn)/(len(genuine)+len(impostor)),'precision':precision,'recall':recall,'f1':2*precision*recall/(precision+recall) if precision+recall else 0,'FAR':fp/len(impostor),'FRR':fn/len(genuine),'genuine_count':len(genuine),'impostor_count':len(impostor)}

def select_threshold(genuine,impostor):
    if len(genuine)<5 or len(impostor)<5: raise ValueError('Cần ≥5 ảnh genuine và ≥5 impostor riêng cho validation.')
    candidates=[confusion(genuine,impostor,float(t)) for t in np.arange(.4,.96,.025)]
    best=min(candidates,key=lambda m:(m['FAR']+m['FRR'],m['FAR'],-m['threshold']))
    return best,candidates
