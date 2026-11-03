"""Inventory every template. Labels are source audit decisions, not hardware QA."""
import json,re
from pathlib import Path
root=Path(__file__).resolve().parent.parent
rows=[]
for path in sorted((root/'templates').rglob('*.html')):
    text=path.read_text(encoding='utf-8');name=path.relative_to(root/'templates').as_posix()
    parent=re.search(r'{%\s*extends\s+([^%]+)%}',text)
    if name.startswith('staff/') or name.startswith('shared/module07/chat') or name in ['customer/portal_footer.html','customer/footer.html','customer/account/profile.html']:
        status='Nâng cấp trong task staff';action='Shared components/layout mới'
    elif name.startswith(('admin/business/','admin/module07/','admin/restaurant/')):
        status='Giữ cấu trúc, đồng bộ staff/admin';action='Base theo vai trò; shared card/table/form polish'
    elif name.startswith(('customer/ai/','admin/ai/','admin/location/')):
        status='Giữ UI đã hoàn thiện';action='Giữ FaceID/GPS/AI logic; staff attendance đổi shell'
    elif name.startswith(('customer/home','customer/menu','customer/cart','customer/booking','customer/food-detail','customer/auth/')):
        status='Giữ bố cục đã có';action='Footer/flex shell/form accent; không rewrite'
    elif name.startswith(('admin/employees/','admin/inventory/','admin/reports/','admin/gis/','customer/orders/')):
        status='Legacy/prototype cần phân biệt với route hiện hành';action='Không xóa; route hiện hành dùng generic/shared templates. Chưa khẳng định mọi prototype có live route.'
    else:
        status='Shared/partial hoặc giữ theo design system';action='Kiểm tra nguồn; browser QA theo route ưu tiên'
    rows.append({'path':name,'parent':parent.group(1).strip() if parent else 'partial/standalone','status':status,'action':action})
out=root/'qa_staff';out.mkdir(exist_ok=True)
(out/'template_audit.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['# Audit templates và quyết định UI','',f'Đã đọc {len(rows)} templates. Phân loại dựa nguồn/layout; không thay cho live QA từng route.','', '| Template | Base | Quyết định | Action |','|---|---|---|---|']
lines.extend(f"| `{r['path']}` | `{r['parent']}` | {r['status']} | {r['action']} |" for r in rows)
(root/'docs/STAFF_TEMPLATE_AUDIT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'templates':len(rows),'report':'docs/STAFF_TEMPLATE_AUDIT.md'}))
