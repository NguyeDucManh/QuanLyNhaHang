"""Explicit, repeatable representative recipes. Never seeds stock or transactions."""
from decimal import Decimal
from django.core.management.base import BaseCommand,CommandError
from django.db import transaction
from customers.models import MenuItem,Ingredient,RecipeIngredient

# Quantities per serving in the existing ingredient's unit. Starter demo recipes;
# kitchen must approve actual procurement yields/portions before operational use.
RECIPES={
 'Gỏi cá hồi sốt mè rang':{'Cá hồi':('.150','kg'),'Mè rang':('.010','kg'),'Xà lách':('.050','kg'),'Nước tương':('.015','l'),'Dầu ăn':('.005','l')},
 'Bào ngư sốt dầu hào':{'Bào ngư':('.200','kg'),'Dầu hào':('.020','l'),'Tỏi':('.005','kg'),'Dầu ăn':('.010','l')},
 'Hải sâm hầm nấm đông cô':{'Hải sâm':('.150','kg'),'Nấm':('.080','kg'),'Nước dùng':('.250','l'),'Tỏi':('.005','kg')},
 'Sò điệp áp chảo sốt chanh bơ':{'Sò điệp':('.180','kg'),'Bơ':('.020','kg'),'Chanh':('.030','kg'),'Muối':('.002','kg')},
 'Tôm hùm nướng phô mai':{'Tôm hùm':('.400','kg'),'Phô mai':('.050','kg'),'Bơ':('.020','kg'),'Tỏi':('.005','kg')},
 'Tôm hùm sốt bơ tỏi':{'Tôm hùm':('.400','kg'),'Bơ':('.040','kg'),'Tỏi':('.015','kg'),'Muối':('.002','kg')},
 'Cua sốt tiêu đen':{'Cua':('.350','kg'),'Tiêu đen':('.005','kg'),'Nước tương':('.015','l'),'Tỏi':('.010','kg'),'Dầu ăn':('.010','l')},
 'Hàu nướng phô mai':{'Hàu':('.250','kg'),'Phô mai':('.050','kg'),'Bơ':('.015','kg'),'Tỏi':('.005','kg')},
 'Cá hồi áp chảo sốt chanh dây':{'Cá hồi':('.200','kg'),'Chanh dây':('.060','kg'),'Bơ':('.020','kg'),'Đường':('.010','kg'),'Muối':('.002','kg')},
 'Thăn bò áp chảo sốt tiêu xanh':{'Thịt bò':('.200','kg'),'Tiêu xanh':('.010','kg'),'Bơ':('.020','kg'),'Nước dùng':('.060','l'),'Muối':('.002','kg')},
 'Bít tết bò Ribeye sốt nấm':{'Thịt bò':('.250','kg'),'Nấm':('.080','kg'),'Bơ':('.020','kg'),'Sữa':('.050','l'),'Muối':('.002','kg')},
 'Cơm chiên hải sản sốt XO':{'Gạo':('.100','kg'),'Tôm':('.060','kg'),'Cua':('.040','kg'),'Trứng':('1','piece'),'Sốt XO':('.020','kg'),'Dầu ăn':('.015','l')},
 'Mì xào hải sản kiểu Hồng Kông':{'Mì':('.150','kg'),'Tôm':('.060','kg'),'Sò điệp':('.060','kg'),'Dầu hào':('.020','l'),'Dầu ăn':('.015','l'),'Tỏi':('.005','kg')},
 'Bào ngư hấp tỏi':{'Bào ngư':('.200','kg'),'Tỏi':('.020','kg'),'Nước tương':('.015','l'),'Dầu ăn':('.005','l')},
 'Tôm càng xanh nướng bơ tỏi':{'Tôm càng xanh':('.250','kg'),'Bơ':('.030','kg'),'Tỏi':('.010','kg'),'Muối':('.002','kg')},
}

class Command(BaseCommand):
    help='Seed 15 named representative recipes; skip existing recipes, never change stock.'
    @transaction.atomic
    def handle(self,*args,**options):
        menus=list(MenuItem.objects.select_for_update().filter(name__in=RECIPES).order_by('pk'))
        if len(menus)!=len(RECIPES): raise CommandError('Không tìm đủ 15 món theo tên chính thức; không seed từng phần.')
        created=0; ingredients_created=0
        for menu in menus:
            if menu.recipe_lines.exists(): continue
            for index,(name,(quantity,unit)) in enumerate(RECIPES[menu.name].items()):
                matches=list(Ingredient.objects.filter(name=name).order_by('pk'))
                if matches:
                    ingredient=matches[0]
                    if len(matches)!=1 or ingredient.unit!=unit or not ingredient.is_active: raise CommandError(f'Kiểm tra nguyên liệu {name}: trùng tên/sai đơn vị/inactive.')
                else:
                    import hashlib
                    code='M07-'+hashlib.sha256(name.encode()).hexdigest()[:10].upper()
                    ingredient=Ingredient.objects.create(code=code,name=name,unit=unit,current_stock=0,minimum_stock=0)
                    ingredients_created+=1
                RecipeIngredient.objects.create(menu_item=menu,ingredient=ingredient,quantity_required=Decimal(quantity))
            created+=1
        have=MenuItem.objects.filter(recipe_lines__isnull=False).distinct().count()
        self.stdout.write(self.style.SUCCESS(f'Recipes added: {created}; ingredients added: {ingredients_created}; menus with recipe: {have}; without: {MenuItem.objects.count()-have}. Stock unchanged.'))
