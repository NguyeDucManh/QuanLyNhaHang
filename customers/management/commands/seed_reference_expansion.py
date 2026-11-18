"""Reference catalog for demonstration only. No fabricated supplier contacts or stock."""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from customers.models import Ingredient, Supplier, RecipeReference

# Completely separate from the customer-facing menu and inventory consumption.
BASES = [
 ("Gỏi cá hồi", "Khai vị", 18, [("Cá hồi","0.180","kg"),("Xà lách","0.060","kg"),("Chanh","0.025","kg")]),
 ("Súp cua", "Súp", 30, [("Thịt cua","0.120","kg"),("Nước dùng","0.300","l"),("Trứng","1","piece")]),
 ("Tôm nướng", "Hải sản", 25, [("Tôm","0.250","kg"),("Tỏi","0.012","kg"),("Bơ","0.025","kg")]),
 ("Cá chẽm hấp", "Cá", 35, [("Cá chẽm","0.300","kg"),("Gừng","0.015","kg"),("Hành lá","0.020","kg")]),
 ("Bò áp chảo", "Bò", 25, [("Thịt bò","0.220","kg"),("Bơ","0.025","kg"),("Tiêu đen","0.003","kg")]),
 ("Mì xào", "Món chính", 20, [("Mì","0.150","kg"),("Cải thìa","0.080","kg"),("Tỏi","0.010","kg")]),
 ("Cơm chiên", "Món chính", 18, [("Gạo","0.120","kg"),("Trứng","1","piece"),("Hành lá","0.015","kg")]),
 ("Salad rau củ", "Khai vị", 15, [("Xà lách","0.080","kg"),("Cà chua bi","0.070","kg"),("Dưa leo","0.070","kg")]),
 ("Gà nướng", "Gia cầm", 40, [("Thịt gà","0.250","kg"),("Tỏi","0.015","kg"),("Mật ong","0.020","kg")]),
 ("Panna cotta", "Tráng miệng", 25, [("Kem tươi","0.120","l"),("Sữa","0.080","l"),("Gelatin","0.006","kg")]),
]
STYLES = [
 ("sốt chanh", ("Chanh","0.025","kg"), "Pha nước cốt chanh, nêm vừa khẩu vị rồi hoàn thiện món."),
 ("sốt tiêu", ("Tiêu xanh","0.008","kg"), "Làm nóng sốt tiêu, điều chỉnh độ cay rồi hoàn thiện món."),
 ("sốt mè rang", ("Mè rang","0.012","kg"), "Rang mè thơm, phối cùng sốt rồi hoàn thiện món."),
 ("sốt tỏi", ("Tỏi","0.012","kg"), "Phi tỏi thơm ở nhiệt vừa rồi hoàn thiện món."),
 ("thảo mộc", ("Hương thảo","0.004","kg"), "Thêm thảo mộc, nêm vừa khẩu vị rồi hoàn thiện món."),
]
# 20 potential new catalog ingredients: zero stock; no automatic receipts or valuation.
EXTRA_INGREDIENTS = [
 ("Bột paprika","kg"),("Lá húng quế","kg"),("Lá oregano","kg"),
 ("Lá thyme","kg"),("Ngò rí","kg"),("Rau mầm","kg"),
 ("Cà chua bi","kg"),("Dưa leo","kg"),("Cải thìa","kg"),
 ("Thịt gà","kg"),("Thịt cua","kg"),("Gelatin","kg"),
 ("Dấm táo","l"),("Dấm balsamic","l"),("Dầu ô liu","l"),
 ("Hạt điều","kg"),("Măng tây","kg"),("Khoai tây","kg"),
 ("Hạt sen","kg"),("Đậu Hà Lan","kg"),
]
SUPPLIERS = [
 ("DEMO-NCC004","DEMO - Nguồn hải sản đông lạnh"),
 ("DEMO-NCC005","DEMO - Nguồn thịt và gia cầm"),
 ("DEMO-NCC006","DEMO - Nguồn rau củ hữu cơ"),
 ("DEMO-NCC007","DEMO - Nguồn gia vị và thực phẩm khô"),
 ("DEMO-NCC008","DEMO - Nguồn nguyên liệu làm bánh"),
]

def build_references():
    for base_index, (name,category,minutes,ingredients) in enumerate(BASES,1):
        for style_index,(style,extra,finish) in enumerate(STYLES,1):
            code=f"DEMO-CT{(base_index-1)*5+style_index:03}"
            yield dict(code=code,name=f"{name} {style} (tham khảo)",category=category,
                estimated_minutes=minutes + (style_index-1)*2,
                ingredients=[dict(name=n,quantity=q,unit=u) for n,q,u in [*ingredients,extra]],
                steps=[
                    "Kiểm tra chất lượng, cân nguyên liệu theo định lượng minh họa.",
                    "Sơ chế, làm sạch và chuẩn bị dụng cụ riêng cho thực phẩm sống và chín.",
                    f"Chế biến phần chính của {name.lower()} đến nhiệt độ an toàn phù hợp.",
                    finish,
                    "Kiểm tra hương vị và trình bày. Bếp trưởng duyệt định lượng trước khi áp dụng thực tế.",
                ])

REFERENCES=tuple(build_references())
assert len(REFERENCES)==50 and len({x["name"] for x in REFERENCES})==50

class Command(BaseCommand):
    help="Seed 50 separate DEMO recipe references, 5 DEMO suppliers, 20 demo ingredients. Never touches menus, stock or transactions."

    def add_arguments(self,parser):
        parser.add_argument("--apply",action="store_true",help="Explicitly apply changes; default preview only")

    def handle(self,*args,**options):
        summary={"reference_recipes":len(REFERENCES),"suppliers":len(SUPPLIERS),
                 "ingredient_catalog":len(EXTRA_INGREDIENTS),"mode":"apply" if options["apply"] else "preview",
                 "no_changes_to":"MenuItem, RecipeIngredient, stock, prices, purchases, payments, bookings"}
        if not options["apply"]:
            self.stdout.write(str(summary)); return
        with transaction.atomic():
            # Never rewrite pre-existing or user-edited records.
            for row in REFERENCES:
                existing=RecipeReference.objects.filter(code=row["code"]).first()
                if existing and existing.name!=row["name"]:
                    raise CommandError(f"Recipe reference code conflict: {row['code']}")
                if RecipeReference.objects.filter(name=row["name"]).exclude(code=row["code"]).exists():
                    raise CommandError(f"Recipe reference name conflict: {row['name']}")
                RecipeReference.objects.get_or_create(code=row["code"],defaults={k:v for k,v in row.items() if k!="code"})
            for code,name in SUPPLIERS:
                existing=Supplier.objects.filter(code=code).first()
                if existing and existing.name!=name: raise CommandError(f"Supplier code conflict: {code}")
                Supplier.objects.get_or_create(code=code,defaults={"name":name,"is_active":True})
            for index,(name,unit) in enumerate(EXTRA_INGREDIENTS,1):
                code=f"DEMO-NL{index:03}"
                same_code=Ingredient.objects.filter(code=code).first()
                if same_code and (same_code.name!=name or same_code.unit!=unit):
                    raise CommandError(f"Ingredient code conflict: {code}")
                by_name=list(Ingredient.objects.filter(name=name))
                if len(by_name)>1 or (by_name and by_name[0].unit!=unit):
                    raise CommandError(f"Ingredient duplicate/unit conflict: {name}")
                if not by_name:
                    Ingredient.objects.create(code=code,name=name,unit=unit,current_stock=0,minimum_stock=0,is_active=True)
        self.stdout.write(self.style.SUCCESS(str(summary)))
