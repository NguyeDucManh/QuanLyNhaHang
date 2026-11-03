(() => {
'use strict';
const paths={
menu:'M4 6h16M4 12h16M4 18h16',
grid:'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
utensils:'M4 3v6c0 3 5 3 5 0V3M6.5 3v18M16 21V3c-5 3-5 10 0 10M20 3v18',
search:'m21 21-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
bell:'M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4',
chat:'M21 11a9 9 0 0 1-9 9H8l-5 2 1-6a9 9 0 1 1 17-5M8 10h.01M12 10h.01M16 10h.01',
chevron:'m7 10 5 5 5-5',
calendar:'M4 5h16v16H4zM16 3v4M8 3v4M4 10h16M8 14h3M8 17h6',
money:'M12 3v18M16 7c-1-3-9-3-9 1 0 5 10 2 10 7 0 4-8 4-10 1',
cart:'M2 3h3l3 12h11l3-9H6M10 20h.01M18 20h.01',
table:'M3 8h18v5H3zM5 13v8M19 13v8M5 8V5h14v3',
users:'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0M17 3a4 4 0 0 1 0 8M22 21v-2a4 4 0 0 0-3-4',
box:'m12 3 9 5v10l-9 5-9-5V8zM3 8l9 5 9-5M12 13v10M7 5l10 6',
up:'m7 10 5-5 5 5M12 5v14',
book:'M12 5c-4-3-8-2-9-1v16c3-2 6-2 9 0 3-2 6-2 9 0V4c-3-2-6-2-9 1v15',
receipt:'M5 3h14v19l-3-2-4 2-4-2-3 2zM8 7h8M8 11h8M8 15h5',
wallet:'M3 6h17v15H3zM3 6V4h14v2M15 11h6v5h-6z',
leaf:'M20 3C9 2 2 7 5 16c6 8 16 0 15-13ZM4 21 16 8',
truck:'M3 4h11v13H3zM14 9h4l4 5v3h-8M8 19a2 2 0 1 1-4 0 2 2 0 0 1 4 0M20 19a2 2 0 1 1-4 0 2 2 0 0 1 4 0',
tools:'m4 3 17 18M20 3l-6 6M16 3l5 5M3 21l6-6',
alert:'m12 3 10 18H2zM12 9v5M12 18h.01',
user:'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0M4 21v-2a8 8 0 0 1 16 0v2',
briefcase:'M3 7h18v14H3zM8 7V3h8v4M3 12c5 3 13 3 18 0M12 11v5',
pin:'M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0M15 10a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
chart:'M4 3v18h18M8 16v-5M13 16V7M18 16V4',
spark:'m12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3z',
bot:'M5 7h14v13H5zM12 3v4M10 3h4M8 12h.01M16 12h.01M9 16h6M2 11v5M22 11v5',
settings:'M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1zM16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
eye:'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
close:'m6 6 12 12M18 6 6 18',
clock:'M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0M12 6v6l4 2',
shield:'m12 2 9 4v6c0 6-9 10-9 10S3 18 3 12V6zM8 12l3 3 5-6'
};
const icon=(name,cls='')=>'<svg class="icon '+cls+'" viewBox="0 0 24 24" aria-hidden="true"><path d="'+(paths[name]||paths.grid)+'"/></svg>';
const escapeHTML=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const readJSON=(id,fallback)=>{
const element=document.getElementById(id);
if(!element)return fallback;
try{const value=JSON.parse(element.textContent);return value&&typeof value==='object'?value:fallback;}
catch{return fallback;}
};
const access=readJSON('rbac-access',{});
const adminRoutes=readJSON('admin-routes',{home:location.pathname});
const tableSummary=readJSON('table-summary',{total:0,available:0,occupied:0,maintenance:0,inactive:0});
const businessSummary=readJSON('business-summary',{revenue_today:0,order_count_today:0,low_stock_count:0,revenue_days:[]});
const serverPage=document.body.dataset.adminPage;
const serverContent=document.getElementById('server-content')?.innerHTML||'';
const pageHref=page=>adminRoutes[page]||adminRoutes.home+'#'+page;
const groups=[
['QUẢN LÝ NHÀ HÀNG',[['menu','book','Thực đơn'],['categories','book','Danh mục'],['toppings','book','Topping'],['combos','book','Combo'],['promotions','money','Khuyến mãi / Voucher'],['reviews','chat','Đánh giá'],['restaurant-info','pin','Thông tin nhà hàng'],['areas','pin','Quản lý khu vực'],['tables','table','Quản lý bàn'],['bookings','calendar','Đặt bàn'],['orders','receipt','Đơn hàng'],['kitchen','utensils','Bếp'],['payments','wallet','Hóa đơn & Thanh toán']]],
['QUẢN LÝ KHO',[['ingredients','leaf','Nguyên liệu'],['transactions','truck','Nhập / Xuất kho'],['suppliers','users','Nhà cung cấp'],['recipes','tools','Công thức món'],['stock-alerts','alert','Tồn kho & Cảnh báo']]],
['NHÂN SỰ',[['employees','user','Danh sách nhân viên'],['positions','briefcase','Chức vụ'],['shifts','clock','Ca làm việc'],['schedules','calendar','Lịch làm việc'],['attendance','clock','Chấm công'],['payroll','wallet','Bảng lương']]],

['AI',[['ai-dashboard','bot','Tổng quan trí tuệ nhân tạo'],['ai-schedule','calendar','Xếp lịch AI'],['recommendation-demo','spark','Gợi ý món'],['ai-forecast','chart','Dự báo'],['ai-inventory','leaf','Đề xuất nguyên liệu'],['ai-faces','user','Quản lý khuôn mặt'],['ai-chatbot','bot','Trợ lý nhà hàng']]],
['BÁO CÁO',[['reports','chart','Thống kê & Báo cáo']]],
['HỆ THỐNG',[['messages','chat','Chat hỗ trợ'],['location-settings','pin','Vị trí & chấm công'],['accounts','shield','Quản lý tài khoản']]]
];
const moduleAccess={menu:'view_menu',areas:'view_areas',tables:'view_tables',bookings:'view_bookings',orders:'view_orders',kitchen:'view_kitchen',payments:'view_payments',ingredients:'view_ingredients',transactions:'view_transactions',suppliers:'view_suppliers',recipes:'view_recipes','stock-alerts':'view_stock_alerts'};
Object.assign(moduleAccess,{'ai-schedule':'ai-schedule','recommendation-demo':'recommendation-demo'});
Object.assign(moduleAccess,Object.fromEntries(['ai-dashboard','ai-forecast','ai-inventory','ai-faces'].map(k=>[k,k])));
Object.assign(moduleAccess,{'categories':'view_menu','location-settings':'ai-dashboard','ai-chatbot':'ai-dashboard'});
Object.assign(moduleAccess,Object.fromEntries(['toppings','combos','combo-items','promotions','reviews','restaurant-info','employees','positions','shifts','schedules','attendance','payroll','periods','messages','reports'].map(k=>[k,k])));
const visibleGroups=groups.map(g=>[g[0],g[1].filter(e=>access.is_admin||access[moduleAccess[e[0]]])]).filter(g=>g[1].length);
const entries=[...(access.role==='STAFF'?[]:[['dashboard','grid','Tổng quan']]),...visibleGroups.flatMap(g=>g[1])];
const orders=readJSON('recent-orders',[]);
const statusNames={PENDING:'Chờ xác nhận',CONFIRMED:'Đã xác nhận',PREPARING:'Đang chuẩn bị',COMPLETED:'Hoàn thành',CANCELLED:'Đã hủy'};
const dishes=readJSON('restaurant-catalog',[]);
const stocks=readJSON('low-stocks',[]);
const currency=n=>n === null ? 'Liên hệ' : new Intl.NumberFormat('vi-VN').format(n)+' ₫';
const foodImage=d=>escapeHTML(d.image);
const pill=s=>'<span class="status '+({PENDING:'pending',CONFIRMED:'pending',PREPARING:'preparing',COMPLETED:'complete',CANCELLED:'pending'}[s]||'pending')+'">'+escapeHTML(statusNames[s]||s)+'</span>';
const navLink=e=>'<a class="nav-link" href="'+escapeHTML(pageHref(e[0]))+'" data-page="'+e[0]+'">'+icon(e[1])+'<span>'+e[2]+'</span></a>';
document.getElementById('app').innerHTML=`
<aside class="sidebar" aria-label="Điều hướng chính"><a href="${escapeHTML(pageHref('dashboard'))}" class="brand"><span class="brand-mark">${icon('utensils')}</span><span><strong>SMART RESTAURANT</strong><small>Không gian quản trị</small></span></a>
<nav class="navigation">${access.role==='STAFF'?'':navLink(entries[0])}${visibleGroups.map(g=>'<p class="nav-group">'+g[0]+'</p>'+g[1].map(navLink).join('')).join('')}</nav><div class="sidebar-foot"><span class="live-dot"></span>Không gian quản trị nhà hàng</div></aside>
<button class="sidebar-backdrop" aria-label="Đóng menu"></button>
<div class="workspace"><header class="topbar"><div class="top-left"><button class="icon-button" id="menu-toggle" aria-label="Ẩn hoặc hiện menu" aria-expanded="true">${icon('menu')}</button><form class="search" id="search-form" role="search">${icon('search')}<input id="global-search" type="search" aria-label="Tìm kiếm" placeholder="Tìm kiếm món ăn, đơn hàng, nhân viên, bàn..." autocomplete="off"><kbd>Ctrl K</kbd></form></div><div class="top-right"><button class="icon-button" data-action="notifications" aria-label="Thông báo">${icon('bell')}<span class="badge">${businessSummary.low_stock_count}</span></button><button class="icon-button" data-action="messages" aria-label="Tin nhắn">${icon('chat')}</button><span class="top-divider"></span><button class="profile" data-action="profile" aria-label="Thông tin quản trị viên"><span class="avatar">ĐM</span><span class="profile-text"><strong>Nguyễn Đức Mạnh</strong><small>Quản trị viên</small></span>${icon('chevron')}</button></div></header>
<main id="main" tabindex="-1"></main></div>
<dialog id="detail-dialog" aria-labelledby="dialog-title"><div class="dialog-head"><h2 id="dialog-title"></h2><button class="icon-button" id="close-dialog" aria-label="Đóng">${icon('close')}</button></div><div class="dialog-body" id="dialog-body"></div></dialog>`;
const main=document.getElementById('main');
const dialog=document.getElementById('detail-dialog');
function openDialog(title,body){document.getElementById('dialog-title').textContent=title;document.getElementById('dialog-body').innerHTML=body;if(!dialog.open)dialog.showModal();}
function stat(color,ic,label,value,change,extra=''){return '<article class="stat"><div class="stat-icon '+color+'">'+icon(ic)+'</div><div><p class="stat-label">'+label+'</p><div class="stat-value '+extra+'">'+value+'</div><div class="stat-change '+extra+'">'+change+'</div></div></article>';}
function ordersTable(all=false){return '<div class="table-scroll"><table><caption class="sr-only" style="position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)">Danh sách đơn hàng</caption><thead><tr><th scope="col">#</th><th scope="col">Thời gian</th><th scope="col">Bàn</th><th scope="col">Khách hàng</th><th scope="col">Tổng tiền</th><th scope="col">Trạng thái</th><th scope="col">Thao tác</th></tr></thead><tbody>'+orders.slice(0,all?7:5).map(o=>'<tr><td>'+escapeHTML(o.order_number||('#'+o.id))+'</td><td>'+o.time+'</td><td>'+escapeHTML(o.table)+'</td><td>'+escapeHTML(o.customer)+'</td><td>'+currency(o.total)+'</td><td>'+pill(o.status)+'</td><td><button class="view-button" data-order="'+o.id+'" aria-label="Xem đơn hàng '+o.id+'">'+icon('eye')+' Xem</button></td></tr>').join('')+'</tbody></table></div>';}
function stockRows(all=false){return stocks.slice(0,all?5:3).map(s=>'<div class="stock-row">'+icon('alert')+'<div><strong>'+escapeHTML(s[0])+'</strong><p>Còn '+s[1]+' '+escapeHTML(s[3])+' (Ngưỡng: '+s[2]+' '+escapeHTML(s[3])+')</p></div></div>').join('');}
function shifts(){return (businessSummary.shifts_today||[]).map(s=>'<div class="shift"><div class="shift-content"><strong>'+escapeHTML(s.name)+'</strong><p>'+escapeHTML(s.employee)+' · '+escapeHTML(s.start)+'–'+escapeHTML(s.end)+'</p></div></div>').join('')||'<p>Chưa có lịch đã duyệt hôm nay.</p>';}
function menuActions(d){
if(!access.change_menu)return '';
const token=escapeHTML(document.querySelector('#admin-logout-form input[name=csrfmiddlewaretoken]').value);
return '<p><a class="primary-button" href="'+escapeHTML(d.edit_url)+'">Sửa món</a></p><form method="post" action="'+escapeHTML(d.toggle_url)+'"><input type="hidden" name="csrfmiddlewaretoken" value="'+token+'"><input type="hidden" name="is_available" value="'+(!d.is_available)+'"><button class="view-button">'+(d.is_available?'Ngừng phục vụ':'Bật phục vụ')+'</button></form>';
}
function foodRows(){return (businessSummary.top_items||[]).map(d=>'<li class="food-row"><span class="food-name">'+escapeHTML(d.name)+'</span><span class="food-count">'+d.quantity+' phần</span></li>').join('')||'<li class="empty-state">Chưa có món bán trong đơn đã thanh toán.</li>';}
function footer(){return '<footer class="page-footer"><span>© '+new Date().getFullYear()+' <b>Smart Restaurant.</b> Quản lý thông minh, phục vụ tận tâm.</span><span>Nhà hàng & kho • Dữ liệu thực</span></footer>';}
function tableDonut(){
if(!tableSummary.total)return '#edf1f6';
let percent=0;const segments=[];
for(const [key,color] of [['available','#40b975'],['occupied','#2475ff'],['maintenance','#b5bac4'],['inactive','#b5bac4']]){const next=percent+tableSummary[key]/tableSummary.total*100;segments.push(color+' '+percent+'% '+next+'%');percent=next;}
return 'conic-gradient('+segments.join(',')+')';
}
function dashboard(){
const links=items=>items.filter(([key])=>access.is_admin||access[moduleAccess[key]]).map(([key,label])=>'<a class="view-button" href="'+escapeHTML(pageHref(key))+'">'+label+'</a>').join('');
main.innerHTML=`<section class="hero" aria-labelledby="welcome"><div class="hero-content"><p class="hero-kicker">Tổng quan nhà hàng</p><h1 id="welcome">${escapeHTML(adminName())}!</h1><p class="hero-description">Theo dõi kinh doanh, vận hành và đội ngũ theo từng nhóm công việc.</p><div class="hero-date">${icon('calendar')}<span>${new Intl.DateTimeFormat('vi-VN',{dateStyle:'full',timeZone:'Asia/Ho_Chi_Minh'}).format(new Date())}</span></div></div></section>
<section class="stats" aria-label="Bốn chỉ số chính hôm nay">${stat('green','money','Doanh thu hôm nay',currency(businessSummary.revenue_today),'Thanh toán đã xác nhận')}${stat('blue','cart','Đơn hàng hôm nay',businessSummary.order_count_today,'Đơn được tạo hôm nay')}${stat('orange','table','Bàn đang sử dụng',tableSummary.occupied+' / '+tableSummary.total,'Theo trạng thái hiện tại')}${stat('green','calendar','Đặt bàn hôm nay',businessSummary.booking_today||0,'Không tính đặt bàn hủy')}</section>
<section class="work-group admin-group"><header class="work-group-heading"><div><h2>Tổng quan kinh doanh</h2><p>Doanh thu, khách hàng và hóa đơn theo dữ liệu DB</p></div></header><div class="dashboard-grid"><section class="panel chart-panel"><div class="panel-head"><h3>Doanh thu 7 ngày gần nhất</h3><select id="revenue-period" aria-label="Khoảng thời gian doanh thu"><option value="7">7 ngày</option><option value="30">30 ngày</option></select></div><div id="chart"></div></section><section class="panel"><div class="work-facts"><div><small>Hóa đơn thanh toán hôm nay</small><strong>${businessSummary.paid_invoices_today||0}</strong></div><div><small>Khách đã mua</small><strong>${businessSummary.customers||0}</strong></div></div><h3>Món được chọn trong đơn đã thanh toán</h3><ol class="best-sellers" id="food-list">${foodRows()}</ol></section></div><div class="admin-group-links">${links([['reports','Báo cáo'],['payments','Hóa đơn & thanh toán']])}</div></section>
<section class="work-group admin-group"><header class="work-group-heading"><div><h2>Vận hành nhà hàng</h2><p>Đơn đang xử lý, bếp, bàn và khách sắp tới</p></div></header><div id="dashboard-operational-body"></div><div class="dashboard-grid"><section class="panel"><h3>Trạng thái bàn</h3><div class="table-status"><div class="donut" style="background:${tableDonut()}"><div class="donut-center"><strong>${tableSummary.total}</strong><span>Tổng bàn</span></div></div><div class="legend">${[['Trống',tableSummary.available],['Đang sử dụng',tableSummary.occupied],['Bảo trì',tableSummary.maintenance],['Ngừng hoạt động',tableSummary.inactive]].map(([label,value])=>'<div class="legend-row">'+label+'<b>'+value+'</b></div>').join('')}</div></div></section><section class="panel"><h3>Đơn hàng gần đây</h3>${orders.slice(0,5).map(o=>'<article class="dashboard-order"><div><strong>'+escapeHTML(o.order_number||('#'+o.id))+'</strong><small>'+escapeHTML(o.customer)+' · '+escapeHTML(o.time)+' · '+escapeHTML(o.table)+'</small><small>'+currency(o.total)+'</small></div><div>'+pill(o.status)+'<button class="view-button" data-order="'+o.id+'">Xem</button></div></article>').join('')||'<p>Chưa có đơn hàng.</p>'}</section></div><div class="admin-group-links">${links([['bookings','Đặt bàn'],['kitchen','Bếp'],['orders','Đơn hàng'],['tables','Bàn & khu vực']])}</div></section>
${access.view_ingredients?`<section class="work-group admin-group"><header class="work-group-heading"><div><h2>Kho & nguyên liệu</h2><p>Tồn kho và các cảnh báo cần xử lý</p></div><span class="staff-badge waiting">${businessSummary.low_stock_count} loại sắp hết</span></header><section class="panel alerts-panel">${stockRows()||'<p>Chưa có cảnh báo kho.</p>'}</section><div class="admin-group-links">${links([['ingredients','Nguyên liệu'],['transactions','Lịch sử nhập/xuất'],['stock-alerts','Cảnh báo tồn kho']])}</div><h3>Nhập/xuất gần nhất</h3>${(businessSummary.recent_stock||[]).map(row=>'<div class="stock-activity"><div><strong>'+escapeHTML(row.ingredient)+'</strong><small>'+escapeHTML(row.time)+'</small></div><span>'+escapeHTML(row.kind)+' · '+escapeHTML(row.quantity)+' '+escapeHTML(row.unit)+'</span></div>').join('')||'<p class="help-text">Chưa có hoạt động kho.</p>'}</section>`:''}
${access.employees||access.schedules?`<section class="work-group admin-group"><header class="work-group-heading"><div><h2>Nhân sự</h2><p>Ca được duyệt và chấm công hôm nay</p></div><span class="staff-badge">${businessSummary.employee_present||0} / ${businessSummary.employee_active||0} nhân viên đang làm</span></header><section class="panel shifts-panel">${shifts()}</section><div class="admin-group-links">${links([['employees','Nhân viên'],['schedules','Lịch làm'],['attendance','Chấm công']])}</div></section>`:''}
<section class="work-group admin-group work-income"><header class="work-group-heading"><div><h2>AI & cảnh báo</h2><p>Kết quả nghiên cứu giữ nguyên nguồn dữ liệu và giới hạn kiểm chứng</p></div></header><div class="admin-group-links">${links([['recommendation-demo','Gợi ý món'],['ai-forecast','Dự báo'],['ai-inventory','Đề xuất nguyên liệu'],['ai-faces','Nhận diện khuôn mặt'],['ai-chatbot','Trợ lý nhà hàng']])}</div></section>${footer()}`;
drawChart(7);
}
function drawChart(days){
const raw=businessSummary.revenue_days.slice(-days);
const values=Array.from({length:days},(_,i)=>Number(raw[i]||0)/1000000);
const maximum=Math.max(1,Math.ceil(Math.max(...values)/4)*4);
const left=38,right=492,top=14,bottom=160;
const points=values.map((v,i)=>[left+i*(right-left)/(values.length-1),bottom-v/maximum*(bottom-top)]);
let svg='<svg class="revenue-chart" viewBox="0 0 510 192" preserveAspectRatio="none" role="img" aria-label="Biểu đồ doanh thu '+days+' ngày, đơn vị triệu đồng"><defs><linearGradient id="area-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#145443" stop-opacity=".22"/><stop offset="100%" stop-color="#145443" stop-opacity=".04"/></linearGradient></defs>';
for(let step=0;step<=4;step++){const v=maximum*step/4;const y=bottom-v/maximum*(bottom-top);svg+='<line class="chart-grid" x1="'+left+'" y1="'+y+'" x2="'+right+'" y2="'+y+'"/><text class="chart-axis" x="28" y="'+(y+4)+'" text-anchor="end">'+(v?v+'M':'0')+'</text>';}
const labelIndices=days===7?[0,1,2,3,4,5,6]:[0,5,10,15,20,25,29];
labelIndices.forEach(i=>{const x=points[i][0];const date=new Date();date.setDate(date.getDate()-(days-1-i));const label=new Intl.DateTimeFormat('vi-VN',{day:'2-digit',month:'2-digit'}).format(date);svg+='<line class="chart-grid" x1="'+x+'" y1="'+top+'" x2="'+x+'" y2="'+bottom+'"/><text class="chart-axis" x="'+x+'" y="183" text-anchor="middle">'+label+'</text>';});
const line=points.map((p,i)=>(i?'L':'M')+p[0]+','+p[1]).join(' ');
svg+='<path d="'+line+' L'+right+','+bottom+' L'+left+','+bottom+' Z" fill="url(#area-fill)"/><path class="chart-line" d="'+line+'"/>';
points.forEach((p,i)=>{svg+='<circle class="chart-dot" cx="'+p[0]+'" cy="'+p[1]+'" r="'+(days===7?4:2.5)+'"><title>'+values[i]+' triệu đồng</title></circle>';});
document.getElementById('chart').innerHTML=svg+'</svg>';
}
function heading(title,description){return '<div class="module-heading"><div><h1>'+title+'</h1><p>'+description+'</p></div><a class="view-button" href="#dashboard">Về tổng quan</a></div>';}
function route(){
const page=serverPage||location.hash.slice(1)||(access.role==='STAFF'?entries[0]?.[0]:'dashboard');
const entry=entries.find(e=>e[0]===({'combo-items':'combos',periods:'payroll'}[page]||page));
if(!entry){main.innerHTML='<section class="panel module-placeholder"><h1>Không có quyền truy cập khu vực này</h1></section>';return;}
if(adminRoutes[page]&&page!==serverPage){location.href=adminRoutes[page];return;}
document.querySelectorAll('.nav-link').forEach(a=>{const active=a.dataset.page===entry[0];a.classList.toggle('active',active);if(active)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
document.title=entry[2]+' | Smart Restaurant';
document.body.classList.remove('mobile-open');syncMenu();
if(serverPage){main.innerHTML=serverContent;}
else if(entry[0]==='dashboard')dashboard();
else{
let body='';
if(page==='orders')body='<section class="panel">'+ordersTable(true)+'</section>';
else if(page==='menu'||page==='recommendations')body=(access.add_menu?'<p><a class="primary-button" href="'+escapeHTML(document.getElementById('menu-add-link').href)+'">Thêm món</a></p>':'')+'<div class="module-grid">'+dishes.map((d,i)=>'<button class="table-card menu-card" data-dish="'+i+'"><img src="'+foodImage(d,600)+'" alt="'+escapeHTML(d.name)+'"><div><h2>'+escapeHTML(d.name)+'</h2><p>'+escapeHTML(d.category_label)+'</p><p>'+escapeHTML(d.status)+'</p><strong>'+currency(d.price)+'</strong></div></button>').join('')+'</div>';

else if(page==='shifts'||page==='ai-schedule')body='<section class="panel"><div class="panel-head"><h2>Phân bổ ca làm việc hôm nay</h2></div>'+shifts()+'<p class="dialog-note">Dữ liệu ca làm việc minh họa. Chưa kết nối hệ thống nhân sự.</p></section>';
else body='<section class="panel module-placeholder">'+icon(entry[1])+'<h2>'+entry[2]+'</h2><p>Không gian quản lý '+entry[2].toLocaleLowerCase('vi-VN')+'. Chức năng này chưa có dữ liệu và cần kết nối hệ thống để sử dụng.</p><a class="primary-button" href="#dashboard">Trở về tổng quan</a></section>';
main.innerHTML=heading(entry[2],'Smart Restaurant / '+entry[2]+((page==='menu'||page==='recommendations')?' · Thực đơn chính thức':' · Dữ liệu minh họa'))+body+footer();
}
updateIdentity();
const crumb=document.createElement('nav');crumb.className='breadcrumb';crumb.setAttribute('aria-label','Breadcrumb');crumb.innerHTML='<a href="'+escapeHTML(adminRoutes.home)+'">Smart Restaurant</a> / '+escapeHTML(entry[2]);main.prepend(crumb);
window.scrollTo(0,0);
}
function syncMenu(){const mobile=window.matchMedia('(max-width:720px)').matches;document.getElementById('menu-toggle').setAttribute('aria-expanded',String(mobile?document.body.classList.contains('mobile-open'):!document.body.classList.contains('compact')));}
document.getElementById('menu-toggle').addEventListener('click',()=>{document.body.classList.toggle(window.matchMedia('(max-width:720px)').matches?'mobile-open':'compact');syncMenu();});
document.querySelector('.sidebar-backdrop').addEventListener('click',()=>{document.body.classList.remove('mobile-open');syncMenu();});
document.getElementById('close-dialog').addEventListener('click',()=>dialog.close());
dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();}});
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();document.getElementById('global-search').focus();}if(e.key==='Escape'){document.body.classList.remove('mobile-open');syncMenu();}});
document.addEventListener('change',e=>{if(e.target.id==='revenue-period'){const days=Number(e.target.value);document.querySelector('.chart-panel h3').textContent='Doanh thu '+days+' ngày gần nhất';drawChart(days);}if(e.target.id==='food-period')document.getElementById('food-list').innerHTML=foodRows(e.target.value);});
document.addEventListener('click',e=>{
if(e.target.closest('[data-add-line]')){
const total=document.getElementById('id_items-TOTAL_FORMS');
const template=document.getElementById('business-empty-line');
if(total&&template&&Number(total.value)<100){document.getElementById('business-lines').insertAdjacentHTML('beforeend',template.innerHTML.replaceAll('__prefix__',total.value));total.value=Number(total.value)+1;}
}

const orderButton=e.target.closest('[data-order]');if(orderButton){const o=orders.find(x=>x.id===Number(orderButton.dataset.order));if(o)location.href=o.url;}
const dishButton=e.target.closest('[data-dish]');if(dishButton){const d=dishes[Number(dishButton.dataset.dish)];openDialog(d.name,'<img src="'+foodImage(d)+'" alt="'+escapeHTML(d.name)+'" style="width:100%;height:220px;object-fit:cover;border-radius:10px"><div class="detail-row"><span>Giá bán</span><strong>'+currency(d.price)+'</strong></div><div class="detail-row"><span>Danh mục</span><strong>'+escapeHTML(d.category_label)+'</strong></div><div class="detail-row"><span>Trạng thái</span><strong>'+escapeHTML(d.status)+'</strong></div>'+menuActions(d));}
const action=e.target.closest('[data-action]')?.dataset.action;
if(action==='notifications')openDialog('Thông báo','<p>Cảnh báo tồn kho hiện tại: '+businessSummary.low_stock_count+' nguyên liệu. Xem mục Tồn kho & Cảnh báo.</p>');
if(action==='messages')location.href=pageHref('messages');
if(action==='profile')openDialog('Tài khoản','<div class="detail-row"><span>Họ và tên</span><strong>'+escapeHTML(adminName())+'</strong></div><div class="detail-row"><span>Vai trò</span><strong>'+escapeHTML(({ADMIN:'Quản trị viên',MANAGER:'Quản lý',STAFF:'Nhân viên',CUSTOMER:'Khách hàng'}[access.role]||access.role))+'</strong></div><div class="dialog-actions"><button type="button" onclick="document.getElementById(\'admin-logout-form\').requestSubmit()">Đăng xuất</button></div>');
if(e.target.closest('[data-search-page]')){location.href=pageHref(e.target.closest('[data-search-page]').dataset.searchPage);dialog.close();}
});
const normalize=s=>s.toLocaleLowerCase('vi-VN').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d');
document.getElementById('search-form').addEventListener('submit',e=>{
e.preventDefault();const query=document.getElementById('global-search').value.trim();if(!query)return;
const q=normalize(query);
const matches=entries.filter(x=>normalize(x[2]).includes(q));
const matchingOrders=orders.filter(o=>normalize((o.order_number||o.id)+' '+escapeHTML(o.customer)+' '+o.table).includes(q));
const matchingDishes=dishes.map((d,i)=>({...d,index:i})).filter(d=>normalize(d.name).includes(q));
const results=matches.map(x=>'<button class="search-result" data-search-page="'+x[0]+'">'+icon(x[1])+'<span>'+x[2]+'<small>Chức năng quản lý</small></span></button>').join('')+matchingOrders.map(o=>'<button class="search-result" data-order="'+o.id+'">'+icon('receipt')+'<span>Đơn '+escapeHTML(o.order_number||('#'+o.id))+'<small>'+escapeHTML(o.customer)+' · '+escapeHTML(o.table)+'</small></span></button>').join('')+matchingDishes.map(d=>'<button class="search-result" data-dish="'+d.index+'">'+icon('book')+'<span>'+escapeHTML(d.name)+'<small>'+currency(d.price)+'</small></span></button>').join('');
openDialog('Kết quả tìm kiếm', '<p>Kết quả cho “'+escapeHTML(query)+'”</p>'+(results||'<div class="empty-state">Không tìm thấy kết quả. Thử tên món, mã đơn hoặc tên chức năng.</div>'));
});
function adminName(){
  const identity = document.getElementById('admin-identity');
  return identity ? JSON.parse(identity.textContent).name : 'Tài khoản';
}
function updateIdentity(){
  const name = adminName();
  const profile = document.querySelector('.profile strong');
  if(profile) profile.textContent = name;
  const roleLabel=document.querySelector('.profile-text small');if(roleLabel)roleLabel.textContent=({ADMIN:'Quản trị viên',MANAGER:'Quản lý',STAFF:'Nhân viên',CUSTOMER:'Khách hàng'}[access.role]||access.role);
  const welcome = document.getElementById('welcome');
  if(welcome) welcome.textContent = name + '!';
  const avatar = document.querySelector('.avatar');
  if(avatar) avatar.textContent = name.split(/\s+/).slice(-2).map(word => word[0]).join('').toUpperCase();
}
const logoutButton = document.createElement('button');
logoutButton.type = 'submit';
logoutButton.setAttribute('form','admin-logout-form');
logoutButton.className = 'view-button';
logoutButton.textContent = 'Đăng xuất';
document.querySelector('.top-right').appendChild(logoutButton);
window.addEventListener('hashchange',route);
window.addEventListener('resize',syncMenu);
route();
})();
