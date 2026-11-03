from django.core.management.base import BaseCommand
from customers.deposit_service import expire_due_deposits,expire_provider_sessions


class Command(BaseCommand):
    help='Release timed-out booking holds and optionally close Stripe Test Checkout sessions. Run every minute.'
    def add_arguments(self,parser): parser.add_argument('--stripe',action='store_true',help='Also expire provider sessions (requires a test API key)')
    def handle(self,*args,**options):
        count=expire_due_deposits()
        provider=expire_provider_sessions() if options['stripe'] else 0
        self.stdout.write(f'Expired booking holds: {count}; Stripe sessions closed: {provider}')
