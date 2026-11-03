from pathlib import Path
root=Path(__file__).resolve().parent.parent
p=root/'templates/customer/header.html'; s=p.read_text(encoding='utf-8').replace('Tr? l? AI','Trợ lý AI'); p.write_text(s,encoding='utf-8')
p=root/'templates/customer/food-detail.html'; s=p.read_text(encoding='utf-8').replace('<label>Quantity<input','<label>Số lượng<input'); p.write_text(s,encoding='utf-8')
p=root/'static/ui/product.js';s=p.read_text(encoding='utf-8').replace("table.closest('[data-realtime-kitchen]')||table.querySelector('input,select')", "table.closest('[data-realtime-root]')").replace('Tìm trong bảng…','Tìm trong trang bảng…');p.write_text(s,encoding='utf-8')
p=root/'static/admin/js/main.js';s=p.read_text(encoding='utf-8');s=s.replace("['GIAO TIẾP',[['messages','chat','Chat / Tin nhắn']]],",'');p.write_text(s,encoding='utf-8')
p=root/'static/ui/dashboard.js';s=p.read_text(encoding='utf-8').replace("main.querySelector('.page-footer')?.before(panel)||main.append(panel)","main.insertBefore(panel,main.querySelector('.page-footer'))");p.write_text(s,encoding='utf-8')
p=root/'templates/admin/ai/inventory.html';s=p.read_text(encoding='utf-8');s=s.replace("{% include 'admin/ai/nav.html' %}","{% include 'admin/ai/nav.html' %}{% include 'admin/ai/provenance.html' %}") if 'provenance.html' not in s else s;p.write_text(s,encoding='utf-8')
