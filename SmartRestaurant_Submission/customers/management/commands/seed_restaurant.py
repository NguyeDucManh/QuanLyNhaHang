from django.core.management.base import BaseCommand
from django.db import transaction
from customers.models import Area,RestaurantTable,Supplier,Ingredient


class Command(BaseCommand):
    help='Create missing initial Areas/Tables/Suppliers/Ingredients without updating existing rows or stock.'

    @transaction.atomic
    def handle(self,*args,**options):
        created={'areas':0,'tables':0,'suppliers':0,'ingredients':0}
        for i,name in enumerate(['Tầng trệt','Tầng 1','Phòng VIP','Ngoài trời']):
            area,new=Area.objects.get_or_create(name=name)
            created['areas']+=new
            for j in range(5):
                table,new=RestaurantTable.objects.get_or_create(code=f'B{i*5+j+1:02d}',defaults={'area':area,'capacity':[2,4,4,6,8][j]})
                created['tables']+=new
        for code,name in [('NCC001','Nhà cung cấp hải sản'),('NCC002','Nhà cung cấp rau củ'),('NCC003','Nhà cung cấp thực phẩm khô')]:
            _,new=Supplier.objects.get_or_create(code=code,defaults={'name':name})
            created['suppliers']+=new
        ingredients=[('NL001','Cá hồi','kg'),('NL002','Bơ','kg'),('NL003','Chanh dây','kg'),('NL004','Thịt bò','kg'),('NL005','Tôm','kg'),('NL006','Cua','kg'),('NL007','Bào ngư','kg'),('NL008','Hải sâm','kg'),('NL009','Sò điệp','kg'),('NL010','Hàu','kg'),('NL011','Gạo','kg'),('NL012','Mì','kg'),('NL013','Phô mai','kg'),('NL014','Nấm','kg'),('NL015','Tỏi','kg'),('NL016','Dầu ăn','l'),('NL017','Sữa','l'),('NL018','Trứng','piece')]
        for code,name,unit in ingredients:
            _,new=Ingredient.objects.get_or_create(code=code,defaults={'name':name,'unit':unit,'minimum_stock':1})
            created['ingredients']+=new
        self.stdout.write(self.style.SUCCESS(f'Created: {created}. Existing rows unchanged; initial stock = 0; no orders, invoices, payments or recipes seeded.'))
