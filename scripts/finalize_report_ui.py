from pathlib import Path

root = Path(__file__).resolve().parent.parent
(root/'templates/admin/module07/reports.html').write_text('''{% extends 'index.html' %}{% load static l10n %}{% block admin_content %}
<h1>Dashboard / Báo cáo</h1><p>Dữ liệu PostgreSQL hiện tại. Thực thu chỉ từ Payment SUCCEEDED; doanh số món theo danh mục là giá dòng món trước giảm giá.</p>
{% for title,rows in sections %}<section class="panel"><h2>{{ title }}</h2><div class="report-bars" aria-label="Biểu đồ {{ title }}">{% for label,value in rows %}<div class="report-bar" data-value="{{ value|unlocalize }}"><span>{{ label }}</span><div class="report-bar-track"><i></i></div><strong>{{ value }}</strong></div>{% endfor %}</div><div class="table-scroll"><table><tbody>{% for label,value in rows %}<tr><th>{{ label }}</th><td>{{ value }}</td></tr>{% empty %}<tr><td>Chưa có dữ liệu (0).</td></tr>{% endfor %}</tbody></table></div></section>{% endfor %}
<script src="{% static 'ui/reports.js' %}" defer></script>{% endblock %}
''', encoding='utf-8')
css=root/'static/ui/design-system.css'
source=css.read_text(encoding='utf-8')
if '.report-bar-track' not in source:
    css.write_text(source+'''\n.report-bars{display:grid;gap:12px;margin:20px 0}.report-bars[hidden]{display:none}.report-bar{display:grid;grid-template-columns:minmax(110px,1fr) 2fr auto;align-items:center;gap:14px;font-size:13px}.report-bar-track{height:12px;background:#edf2ee;border-radius:8px;overflow:hidden}.report-bar-track i{display:block;height:100%;background:#257153;border-radius:8px}.report-bar strong{font-variant-numeric:tabular-nums}@media(max-width:600px){.report-bar{grid-template-columns:1fr auto}.report-bar-track{grid-column:1/-1;grid-row:auto}.report-bar strong{grid-column:2;grid-row:1}}\n''',encoding='utf-8')
for name in ['AI_REPORT.md','AI_PHASE.md']:
    path=root/'docs'/name
    if path.exists():
        source=path.read_text(encoding='utf-8')
        marker='## Cập nhật hoàn thiện 14/10/2026'
        if marker not in source:
            path.write_text(source+'\n\n'+marker+'\n\nXem [FINAL_REPORT.md](FINAL_REPORT.md) và [FINAL_DEMO.md](FINAL_DEMO.md): redesign, chatbot, FaceID UX, GIS và live Edge E2E. Hạn chế browser trong báo cáo cũ là lịch sử; live HTTP đã kiểm tra được ở giai đoạn này. Webcam/GPS thật, enrollment và threshold calibration vẫn chưa được kiểm chứng. Các metric AI cũ giữ nguyên provenance.\n',encoding='utf-8')
path=root/'docs/FINAL_REPORT.md'
source=path.read_text(encoding='utf-8').replace('Existing reports được đồng bộ UI, chưa bổ sung toàn bộ biến thể biểu đồ danh mục/phương thức thanh toán theo spec. ','Reports có bar charts cho dữ liệu numeric cùng bảng; danh mục dùng doanh số dòng món trước giảm giá, phương thức dùng thực thu, không cộng lẫn đại lượng này. ')
path.write_text(source,encoding='utf-8')
