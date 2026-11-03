from django.db import migrations


def backfill(apps, schema_editor):
    Item = apps.get_model('customers', 'OrderItem')
    states = {'PENDING':'DRAFT','CONFIRMED':'QUEUED','PREPARING':'PREPARING','COMPLETED':'READY','CANCELLED':'CANCELLED'}
    for item in Item.objects.using(schema_editor.connection.alias).select_related('order').all().iterator():
        status = states[item.order.status]
        # No kitchen event history existed. Infer a boundary from the old Order,
        # never pretend this is an accurately recorded historical kitchen event.
        boundary = max(item.created_at, item.order.updated_at)
        values = {'kitchen_status':status}
        if status in ('QUEUED','PREPARING','READY'):
            values['queued_at'] = boundary
        if status in ('PREPARING','READY'):
            values['preparing_at'] = boundary
        if status == 'READY':
            values['ready_at'] = boundary
        Item.objects.using(schema_editor.connection.alias).filter(pk=item.pk).update(**values)
    # Old totals are historical records. Do not rewrite legacy financial amounts,
    # especially already cancelled orders, or their Invoice/Payment snapshots.


class Migration(migrations.Migration):
    dependencies = [('customers', '0010_orderitem_kitchen_status_orderitem_preparing_at_and_more')]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
