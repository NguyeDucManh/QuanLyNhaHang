from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
p = ROOT/'templates/staff/pos.html'
s = p.read_text(encoding='utf-8').replace('{% for dish in dishes %}', '{% for dish in pos_dishes %}')
s = s.replace('<div class="pos-layout">', '<div class="pos-layout" data-kitchen-access="{{ rbac_access.view_kitchen|yesno:\'true,false\' }}">')
s = s.replace('{% if item.extras %}<small>{{ item.extras }}</small>{% endif %}', '{% if item.extras %}<small>Topping / Combo: xem chi tiết đơn hàng</small>{% endif %}')
s = s.replace('<p>{{ table.get_status_display }}</p>', '<p>{% if table.visual_status == \'RESERVED\' %}Đã đặt{% elif table.visual_status == \'OCCUPIED\' %}Đang phục vụ{% elif table.visual_status == \'INACTIVE\' %}Ngừng hoạt động{% else %}{{ table.get_status_display }}{% endif %}</p>')
p.write_text(s, encoding='utf-8')
p=ROOT/'static/admin/js/main.js'
s=p.read_text(encoding='utf-8').replace('(max-width:720px)', '(max-width:1024px)')
s=s.replace(".filter(e=>access.is_admin||access[moduleAccess[e[0]]])", ".filter(e=>(!!adminRoutes[e[0]])&&(access.is_admin||access[moduleAccess[e[0]]]))")
s=s.replace("drawChart(7);", '''const extra = document.createElement('div');
extra.className='reference-dashboard-extra';
const block=(title,content)=>'<section class="panel reference-extra-panel"><h2>'+title+'</h2>'+content+'</section>';
const total=(businessSummary.order_types||[]).reduce((sum,row)=>sum+row.count,0);
extra.innerHTML=block('Tỷ lệ loại đơn hàng hôm nay',total?(businessSummary.order_types||[]).map(row=>'<div class="stock-activity"><strong>'+escapeHTML({DINE_IN:'Ăn tại chỗ',TAKEAWAY:'Mang về'}[row.order_type]||row.order_type)+'</strong><span>'+row.count+' · '+(row.count/total*100).toFixed(1)+'%</span></div>').join(''):'<p class="empty-state">Chưa có đơn hàng hôm nay.</p>')
+block('Top 5 nguyên liệu tiêu thụ · 30 ngày',(businessSummary.top_ingredients||[]).map(row=>'<div class="stock-activity"><strong>'+escapeHTML(row.ingredient__name)+'</strong><span>'+escapeHTML(row.quantity)+' '+escapeHTML(row.ingredient__unit)+'</span></div>').join('')||'<p class="empty-state">Chưa có dữ liệu tiêu thụ nguyên liệu.</p>')
+block('Hoạt động gần đây',orders.slice(0,5).map(order=>'<a class="stock-activity" href="'+escapeHTML(order.url)+'"><strong>Đơn '+escapeHTML(order.order_number)+'</strong><span>'+escapeHTML(order.time)+' · '+escapeHTML(statusNames[order.status]||order.status)+'</span></a>').join('')||'<p class="empty-state">Chưa có hoạt động đơn hàng.</p>');
main.querySelector('.page-footer').before(extra);
drawChart(7);''', 1)
s=s.replace("'<span class=\"food-name\">'", "'<span class=\"food-name\">'")
p.write_text(s,encoding='utf-8')
p=ROOT/'templates/admin/module07/reports.html'
s=p.read_text(encoding='utf-8').replace('{% for label,value in rows %}<div class="report-bar"', '{% for label,value in rows|slice:\":5\" %}<div class="report-bar"')
s=s.replace('<div class="table-scroll"><table>', '<details class="report-all"><summary>Xem tất cả dữ liệu</summary><div class="table-scroll"><table>').replace('</table></div></section>', '</table></div></details></section>')
p.write_text(s,encoding='utf-8')
