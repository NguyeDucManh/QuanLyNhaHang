"""Chronological model selection with recursive, leakage-free holdouts."""
import numpy as np
import pandas as pd
import joblib
from functools import lru_cache
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor
from .research_data import dataset
from .artifacts import new_version, publish, latest, read_json, write_json

FEATURES=['day_of_week','weekend','promotion_flag','lag_1','lag_7','lag_14','rolling_mean_7','rolling_mean_14']

@lru_cache(maxsize=64)
def load_model(path):
    return joblib.load(path)

def features(frame,target):
    df=frame.copy(); df['date']=pd.to_datetime(df['date']); df=df.sort_values('date')
    df['day_of_week']=df['date'].dt.dayofweek; df['weekend']=(df['day_of_week']>=5).astype(int)
    for lag in [1,7,14]: df[f'lag_{lag}']=df[target].shift(lag)
    for window in [7,14]: df[f'rolling_mean_{window}']=df[target].shift(1).rolling(window).mean()
    return df.dropna(subset=FEATURES)

def metric(actual,predicted):
    a=np.asarray(actual,dtype=float); p=np.asarray(predicted,dtype=float); nonzero=a!=0
    return {'MAE':float(mean_absolute_error(a,p)),'RMSE':float(np.sqrt(mean_squared_error(a,p))),'MAPE':float(np.mean(np.abs((a[nonzero]-p[nonzero])/a[nonzero]))*100) if nonzero.any() else None,'mape_excluded_zeros':int((~nonzero).sum())}

def recursive(model,history,dates,promotions=None):
    history=list(map(float,history)); predictions=[]
    if len(history)<14: raise ValueError('Cần ít nhất 14 ngày lịch sử.')
    for i,date in enumerate(dates):
        day=pd.Timestamp(date); dow=day.dayofweek
        row=[dow,int(dow>=5),(promotions or [0]*len(dates))[i],history[-1],history[-7],history[-14],np.mean(history[-7:]),np.mean(history[-14:])]
        value=max(0,float(model.predict(pd.DataFrame([row],columns=FEATURES))[0]))
        history.append(value); predictions.append(value)
    return predictions

def train_series(frame,target,seed=42):
    frame=frame.sort_values('date').reset_index(drop=True)
    n=len(frame); train_end=max(29,int(n*.7)); validation_end=max(train_end+3,int(n*.85))
    if validation_end>=n-2: raise ValueError('Không đủ ngày cho split thời gian.')
    enriched=features(frame,target); training=enriched[enriched.index<train_end]
    models={'Linear Regression':LinearRegression(),'Random Forest':RandomForestRegressor(n_estimators=100,max_depth=5,random_state=seed,n_jobs=1),'XGBoost':XGBRegressor(n_estimators=100,max_depth=3,learning_rate=.05,random_state=seed,n_jobs=1,tree_method='hist')}
    validation={}; test_metrics={}; fitted={}; charts={}
    for name,model in models.items():
        model.fit(training[FEATURES],training[target])
        section=frame.iloc[train_end:validation_end]
        pred=recursive(model,frame[target].iloc[:train_end],section['date'].tolist(),section['promotion_flag'].tolist())
        validation[name]=metric(section[target],pred)
        final=enriched[enriched.index<validation_end]; model.fit(final[FEATURES],final[target])
        section=frame.iloc[validation_end:]
        pred=recursive(model,frame[target].iloc[:validation_end],section['date'].tolist(),section['promotion_flag'].tolist())
        test_metrics[name]=metric(section[target],pred)
        charts[name]=[{'date':str(d)[:10],'actual':float(a),'predicted':float(p)} for d,a,p in zip(section['date'],section[target],pred)]
        fitted[name]=model
    best=min(validation,key=lambda name:validation[name]['MAE'])
    model=fitted[best]; importance=getattr(model,'feature_importances_',getattr(model,'coef_',[]))
    model.fit(enriched[FEATURES],enriched[target])
    return model,{'best_model':best,'validation':validation,'metrics':test_metrics,'actual_vs_predicted':charts,'feature_importance':dict(zip(FEATURES,map(float,importance))),'train_range':[str(frame['date'].iloc[0])[:10],str(frame['date'].iloc[train_end-1])[:10]],'validation_range':[str(frame['date'].iloc[train_end])[:10],str(frame['date'].iloc[validation_end-1])[:10]],'test_range':[str(frame['date'].iloc[validation_end])[:10],str(frame['date'].iloc[-1])[:10]],'split':'Chronological; recursive predictions in validation/test; model selected only by validation MAE.'}

def train():
    daily,meta=dataset('daily'); item_rows,_=dataset('item_daily'); folder=new_version('forecast'); summaries={}
    series={'revenue':(pd.DataFrame(daily),'revenue'),'order_count':(pd.DataFrame(daily),'order_count')}
    item_frame=pd.DataFrame(item_rows)
    if not item_frame.empty:
        for pk,group in item_frame.groupby('menu_item_id'): series[f'menu_{pk}']=(group.reset_index(drop=True),'quantity_sold')
    for key,(frame,target) in series.items():
        model,summary=train_series(frame,target,meta['seed']); joblib.dump(model,folder/(key+'.joblib'))
        write_json(folder/(key+'_history.json'),frame.to_dict('records')); summaries[key]={**summary,'target':target}
    return publish(folder,{'model_name':'Linear Regression / Random Forest / XGBoost','dataset_version':meta['version'],'features':FEATURES,'hyperparameters':{'random_seed':meta['seed'],'trees':100,'rf_max_depth':5,'xgb_max_depth':3,'xgb_learning_rate':.05},'series':summaries,'data_provenance':meta,'limitation':'70-day research dataset; 30-day recursive forecast is exploratory, future promotions assumed absent unless explicitly supplied.'})

def predict(days=7,promotions=None):
    if days not in [7,14,30]: raise ValueError('Chỉ hỗ trợ 7/14/30 ngày.')
    folder=latest('forecast'); meta=read_json(folder/'metadata.json'); results={}
    for key,summary in meta['series'].items():
        history=read_json(folder/(key+'_history.json')); last=pd.Timestamp(history[-1]['date'])
        dates=[(last+pd.Timedelta(days=i)).strftime('%Y-%m-%d') for i in range(1,days+1)]
        # Artifacts are generated locally by trusted training commands only.
        model=load_model(str(folder/(key+'.joblib')))
        values=recursive(model,[r[summary['target']] for r in history],dates,promotions)
        results[key]=[{'date':d,'predicted':v} for d,v in zip(dates,values)]
    return {'version':meta['version'],'metadata':meta,'series':results,'days':days,'forecast_origin':dates[0]}
