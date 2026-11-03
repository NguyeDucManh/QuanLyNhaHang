"""Import chính thức, chỉ thêm bản ghi thiếu, không ghi đè dữ liệu đã quản lý."""
from django.core.management.base import BaseCommand, CommandError
from django.core.management.color import no_style
from django.contrib.staticfiles import finders
from django.db import connection, transaction
from django.utils.text import slugify
from customers.models import Category, MenuItem


class Command(BaseCommand):
    help = 'Import 45 món từ catalog backup; chạy lại không tạo trùng hoặc ghi đè.'

    @transaction.atomic
    def handle(self, *args, **options):
        from customers.catalog import PRODUCTS
        created_count = 0
        for item_id, name, category_name, price, image in PRODUCTS:
            if not finders.find(image):
                raise CommandError(f'Ảnh không tồn tại: {image}')
            category, _ = Category.objects.get_or_create(
                slug=slugify(category_name.replace('đ', 'd')), defaults={'name': category_name})
            if category.name != category_name:
                raise CommandError(f'Danh mục trùng slug: {category_name}')
            item, created = MenuItem.objects.get_or_create(pk=item_id, defaults={
                'name': name, 'category': category, 'price': price, 'image': image})
            if not created and item.name != name:
                raise CommandError(f'ID {item_id} đã được dùng bởi món khác. Không ghi đè.')
            created_count += created
        # ID seed được gán tường minh; đồng bộ sequence để món mới bắt đầu sau ID 45.
        with connection.cursor() as cursor:
            for sql in connection.ops.sequence_reset_sql(no_style(), [MenuItem]):
                cursor.execute(sql)
        self.stdout.write(self.style.SUCCESS(f'Đã thêm {created_count} món. Tổng: {MenuItem.objects.count()} món, {Category.objects.count()} danh mục.'))
