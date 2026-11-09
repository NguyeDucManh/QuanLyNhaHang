"""Read-only inventory of data relevant to the public restaurant pages."""
import json
from django.core.management.base import BaseCommand
from django.contrib.staticfiles import finders
from django.utils import timezone
from customers import models


class Command(BaseCommand):
    help = 'Read-only counts, visibility filters and missing static menu images; no personal data.'

    def handle(self, *args, **options):
        names = ['Category', 'MenuItem', 'Area', 'RestaurantTable', 'Combo',
                 'Promotion', 'Review', 'RestaurantInfo', 'Supplier', 'Ingredient', 'RecipeIngredient']
        now = timezone.now()
        result = {'counts': {name: getattr(models, name).objects.count() for name in names}}
        result['visible_menu'] = models.MenuItem.objects.filter(is_available=True, category__is_active=True).count()
        result['active_promotions_now'] = models.Promotion.objects.filter(is_active=True, start_at__lte=now, end_at__gte=now).count()
        result['missing_menu_image_ids'] = [pk for pk, image in models.MenuItem.objects.values_list('pk', 'image') if not image or not finders.find(image)]
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
