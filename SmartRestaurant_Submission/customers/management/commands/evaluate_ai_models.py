import json
from collections import Counter
from django.core.management.base import BaseCommand
from customers.ai.artifacts import latest,read_json,new_version,publish
class Command(BaseCommand):
    help='Collect real training metrics and run DB-derived chatbot assertions.'
    def handle(self,*args,**options):
        from customers.ai.chatbot.evaluation import evaluate
        from customers.ai.forecast_service import predict
        from customers.ai.inventory_ai_service import calculate
        folder=new_version('evaluation')
        recommendation=read_json(latest('recommendation')/'metadata.json')
        forecast=predict(7); rows=calculate(forecast)
        from customers.models import FaceProfile,FaceEmbedding
        metadata=publish(folder,{'model_name':'AI evaluation report','recommendation_version':recommendation['version'],'recommendation':recommendation['metrics'],'best_alpha':recommendation['best_alpha'],'forecast_version':forecast['version'],'forecast':forecast['metadata']['series'],'chatbot_version':latest('chatbot').name,'inventory':{'ingredient_count':len(rows),'risks':dict(Counter(r['risk'] for r in rows)),'examples':[{'ingredient':r['ingredient'].name,'predicted_usage':str(r['predicted_usage']),'recommended_purchase':str(r['recommended_purchase']),'unit':r['ingredient'].unit,'risk':r['risk']} for r in rows if r['recommended_purchase']>0][:5]},'faceid':{'enrolled_employees':FaceProfile.objects.count(),'embeddings':FaceEmbedding.objects.count(),'metrics':None,'limitation':'Chưa đủ dữ liệu khuôn mặt thật để công bố metrics.'},'chatbot':evaluate(folder)})
        self.stdout.write(json.dumps({'version':metadata['version'],'chatbot':metadata['chatbot'],'inventory':metadata['inventory']},ensure_ascii=True))
