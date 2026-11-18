import json
from django.conf import settings
from django.core.management.base import BaseCommand,CommandError
from django.urls import reverse
from customers.stripe_configuration import configuration_errors


class Command(BaseCommand):
    help='Check Stripe TEST settings without emitting credentials or changing data.'

    def handle(self,*args,**options):
        errors=configuration_errors()
        self.stdout.write(json.dumps({'ready':not errors,'errors':errors,
            'webhook_path':reverse('stripe_webhook'),
            'required_env':['STRIPE_SECRET_KEY','STRIPE_WEBHOOK_SECRET','STRIPE_PUBLIC_BASE_URL'],
            'publishable_key_required':False,'provider_called':False,
            'delivery_verified':False},ensure_ascii=False))
        if errors:raise CommandError('Cấu hình Stripe chưa sẵn sàng; chưa gọi API hoặc thay đổi dữ liệu.')
