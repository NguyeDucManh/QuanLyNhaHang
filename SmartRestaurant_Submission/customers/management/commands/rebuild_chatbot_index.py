import json
from django.core.management.base import BaseCommand,CommandError
class Command(BaseCommand):
    help='Rebuild public knowledge FAISS index explicitly, never at runserver startup.'
    def handle(self,*args,**options):
        from customers.ai.chatbot.rag_service import rebuild
        try: result=rebuild()
        except ValueError as exc: raise CommandError(str(exc))
        self.stdout.write(json.dumps(result,ensure_ascii=True))
