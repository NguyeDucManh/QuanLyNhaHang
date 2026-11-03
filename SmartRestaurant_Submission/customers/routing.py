from django.urls import path
from .consumers import ManagementUpdatesConsumer,FinancialUpdatesConsumer,ChatUpdatesConsumer

websocket_urlpatterns = [
    path('ws/chat/<int:conversation_id>/',ChatUpdatesConsumer.as_asgi()),
    path('ws/management/payments/',FinancialUpdatesConsumer.as_asgi(),{'stream':'payments'}),
    path('ws/management/invoices/<int:invoice_id>/',FinancialUpdatesConsumer.as_asgi(),{'stream':'invoice'}),
    path('ws/customer/invoices/<int:invoice_id>/',FinancialUpdatesConsumer.as_asgi(),{'stream':'customer_invoice'}),
    path('ws/management/kitchen/', ManagementUpdatesConsumer.as_asgi(), {'stream':'kitchen'}),
    path('ws/management/orders/<int:order_id>/', ManagementUpdatesConsumer.as_asgi(), {'stream':'order'}),
]
