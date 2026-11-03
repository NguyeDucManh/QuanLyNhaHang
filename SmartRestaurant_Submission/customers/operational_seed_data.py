"""Explicit demonstration data, not chef-approved recipes or real contact details."""
from .management.commands.seed_module07_recipes import RECIPES as REPRESENTATIVE_RECIPES

ADDITIONAL_RECIPES={
 'Súp bào ngư hải sâm':{'Bào ngư':('.080','kg'),'Hải sâm':('.080','kg'),'Nấm':('.030','kg'),'Nước dùng':('.300','l'),'Bột bắp':('.010','kg'),'Muối':('.002','kg')},
 'Súp cua tuyết trứng cá':{'Cua tuyết':('.080','kg'),'Trứng cá':('.015','kg'),'Trứng':('1','piece'),'Nước dùng':('.300','l'),'Bột bắp':('.010','kg'),'Muối':('.002','kg')},
 'Gỏi sò điệp kiểu Nhật':{'Sò điệp':('.150','kg'),'Xà lách':('.060','kg'),'Mè rang':('.010','kg'),'Nước tương':('.015','l'),'Chanh':('.020','kg')},
 'Mắt cá ngừ đại dương hầm thuốc Bắc':{'Mắt cá ngừ':('.250','kg'),'Táo đỏ':('.015','kg'),'Kỷ tử':('.005','kg'),'Gừng':('.010','kg'),'Nước dùng':('.250','l'),'Muối':('.002','kg')},
 'Cua rang sốt trứng muối':{'Cua':('.350','kg'),'Lòng đỏ trứng muối':('2','piece'),'Bơ':('.020','kg'),'Tỏi':('.005','kg'),'Dầu ăn':('.015','l')},
 'Bạch tuộc nướng sốt cay':{'Bạch tuộc':('.200','kg'),'Tương ớt':('.020','kg'),'Tỏi':('.010','kg'),'Dầu ăn':('.010','l'),'Muối':('.002','kg')},
 'Cá tuyết nướng sốt Miso':{'Cá tuyết':('.200','kg'),'Miso':('.020','kg'),'Nước tương':('.010','l'),'Đường':('.005','kg'),'Dầu ăn':('.005','l')},
 'Cá chẽm hấp kiểu Hồng Kông':{'Cá chẽm':('.300','kg'),'Gừng':('.015','kg'),'Hành lá':('.015','kg'),'Nước tương':('.020','l'),'Dầu ăn':('.005','l')},
 'Sườn cừu nướng thảo mộc':{'Sườn cừu':('.250','kg'),'Hương thảo':('.003','kg'),'Tỏi':('.010','kg'),'Bơ':('.015','kg'),'Muối':('.002','kg')},
 'Ức vịt áp chảo sốt cam':{'Ức vịt':('.220','kg'),'Cam':('.100','kg'),'Bơ':('.015','kg'),'Đường':('.010','kg'),'Muối':('.002','kg')},
 'Bánh Tiramisu':{'Mascarpone':('.060','kg'),'Bánh ladyfinger':('.030','kg'),'Cà phê':('.025','l'),'Bột cacao':('.005','kg'),'Đường':('.015','kg'),'Kem tươi':('.030','l')},
 'Bánh Lava sô-cô-la':{'Sô-cô-la':('.050','kg'),'Bơ':('.030','kg'),'Bột mì':('.020','kg'),'Đường':('.020','kg'),'Trứng':('1','piece')},
 'Vi cá hầm thịt cua':{'Vi cá':('.050','kg'),'Cua':('.080','kg'),'Nước dùng':('.300','l'),'Bột bắp':('.010','kg'),'Muối':('.002','kg')},
 'Ốc hương rang muối Hồng Kông':{'Ốc hương':('.250','kg'),'Tỏi':('.010','kg'),'Muối':('.004','kg'),'Tiêu đen':('.002','kg'),'Dầu ăn':('.015','l')},
 'Tu hài nướng mỡ hành':{'Tu hài':('.250','kg'),'Hành lá':('.020','kg'),'Dầu ăn':('.020','l'),'Đậu phộng rang':('.010','kg'),'Muối':('.002','kg')},
 'Sashimi cá ngừ đại dương':{'Cá ngừ':('.150','kg'),'Wasabi':('.005','kg'),'Gừng ngâm':('.015','kg'),'Nước tương':('.015','l')},
 'Cá mú hấp xì dầu Hồng Kông':{'Cá mú':('.300','kg'),'Gừng':('.015','kg'),'Hành lá':('.015','kg'),'Nước tương':('.020','l'),'Dầu ăn':('.005','l')},
 'Sườn bò hầm sốt vang':{'Sườn bò':('.250','kg'),'Vang đỏ nấu ăn':('.050','l'),'Cà rốt':('.060','kg'),'Cà chua':('.050','kg'),'Nước dùng':('.200','l'),'Tỏi':('.010','kg'),'Muối':('.002','kg')},
 'Chim câu quay mật ong':{'Chim câu':('1','piece'),'Mật ong':('.020','kg'),'Nước tương':('.015','l'),'Tỏi':('.010','kg'),'Dầu ăn':('.010','l')},
 'Xôi cua hoàng kim':{'Gạo nếp':('.120','kg'),'Cua':('.080','kg'),'Hành lá':('.010','kg'),'Dầu ăn':('.010','l'),'Muối':('.002','kg')},
}
ALL_RECIPES=REPRESENTATIVE_RECIPES | ADDITIONAL_RECIPES
BOTTLED_MENU_IDS=tuple(range(36,46))
MARKER='[DEMO MODULE07 OPERATIONAL]'
POSITIONS=('Quản lý','Phục vụ','Bếp','Thu ngân')
SALARIES={'Quản lý':'18000000','Phục vụ':'8000000','Bếp':'12000000','Thu ngân':'9000000'}
TOPPINGS=[
 ('Phô mai thêm (DEMO)','25000',(9,13)),
 ('Sốt bơ tỏi (DEMO)','30000',(8,9,10,13,32)),
 ('Sốt tiêu (DEMO)','20000',(18,19,20)),
 ('Rau thêm (DEMO)','15000',(15,18,19,20,21,22,23)),
 ('Trứng thêm (DEMO)','15000',(22,23,35)),
]
COMBOS=[
 ('DEMO - Combo 2 người',((3,1),(15,2),(24,2)),'0.90'),
 ('DEMO - Combo hải sản',((9,1),(8,2),(22,2),(45,2)),'0.92'),
 ('DEMO - Combo bò',((19,2),(3,1),(25,2),(45,2)),'0.90'),
 ('DEMO - Combo gia đình',((1,2),(12,1),(31,1),(22,3),(24,3),(45,4)),'0.88'),
]
VOUCHERS=[
 ('WELCOME10','PERCENT','10','300000','100000',100),
 ('GIAM50K','FIXED','50000','500000',None,100),
 ('COMBO15','PERCENT','15','1000000','250000',50),
 ('KHACHVIP','PERCENT','12','2000000','400000',30),
]
