import django.db.models.deletion
import customers.order_numbers
from django.db import migrations, models
from django.utils import timezone


def backfill(apps, schema_editor):
    alias = schema_editor.connection.alias
    Order = apps.get_model('customers', 'Order')
    OrderItem = apps.get_model('customers', 'OrderItem')
    for order in Order.objects.using(alias).all().iterator():
        Order.objects.using(alias).filter(pk=order.pk).update(order_number=f'ORD-{order.created_at:%Y%m%d}-LEGACY-{order.pk}')
    for item in OrderItem.objects.using(alias).select_related('menu_item', 'order').iterator():
        OrderItem.objects.using(alias).filter(pk=item.pk).update(item_name=item.menu_item.name,
            source='DIRECT', created_at=item.order.created_at, updated_at=item.order.updated_at)


class Migration(migrations.Migration):
    dependencies = [('customers', '0008_bookingitem_booking_food_subtotal_and_more')]
    operations = [
        migrations.RemoveConstraint(model_name='orderitem', name='order_menu_unique'),
        migrations.AddField(model_name='order', name='booking', field=models.OneToOneField(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,related_name='service_order',to='customers.booking')),
        migrations.AddField(model_name='order', name='order_number', field=models.CharField(max_length=50,null=True,unique=True,editable=False)),
        migrations.AddField(model_name='orderitem', name='item_name', field=models.CharField(max_length=200,default=''),preserve_default=False),
        migrations.AddField(model_name='orderitem', name='source', field=models.CharField(max_length=8,choices=[('PREORDER','Đặt trước'),('DIRECT','Gọi thêm')],default='DIRECT')),
        migrations.AddField(model_name='orderitem', name='created_at', field=models.DateTimeField(auto_now_add=True,default=timezone.now),preserve_default=False),
        migrations.AddField(model_name='orderitem', name='updated_at', field=models.DateTimeField(auto_now=True)),
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.AlterField(model_name='order', name='order_number', field=models.CharField(max_length=50,unique=True,editable=False,default=customers.order_numbers.generate_order_number)),
        migrations.AddConstraint(model_name='orderitem', constraint=models.CheckConstraint(condition=models.Q(source__in=['PREORDER','DIRECT'], item_name__regex=r'\S'),name='orderitem_snapshot_valid')),
    ]
