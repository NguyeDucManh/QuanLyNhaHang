"""Apply the remaining presentation changes without touching runtime data."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def edit(name, transform):
    path = ROOT / name
    path.write_text(transform(path.read_text(encoding='utf-8')), encoding='utf-8')

def admin(source):
    start = source.index("['AI',[")
    end = source.index("\n['BÁO CÁO'", start)
    source = source[:start] + "['AI',[['ai-faces','user','Quản lý khuôn mặt'],['ai-chatbot','bot','Trợ lý nhà hàng']]]," + source[end:]
    source = source.replace('Xin ch?o,', 'Xin chào,')
    source = source.replace('Theo dõi kinh doanh, vận hành và đội ngũ theo từng nhóm công việc.', 'Cùng theo dõi hoạt động nhà hàng hôm nay.')
    for old, new in [('??t b?n nhanh ?', 'Đặt bàn nhanh →'), ('T?o ??n h?ng ?', 'Tạo đơn hàng →'), ('Nh?p kho ?', 'Nhập kho →'), ('Xem b?o c?o ?', 'Xem báo cáo →')]:
        source = source.replace(old, new)
    source = source.replace("['recommendation-demo','Gợi ý món'],['ai-forecast','Dự báo'],['ai-inventory','Đề xuất nguyên liệu'],", '')
    source = source.replace('AI & cảnh báo', 'Trợ lý & khuôn mặt').replace('Kết quả nghiên cứu giữ nguyên nguồn dữ liệu và giới hạn kiểm chứng', 'Công cụ hỗ trợ vận hành nhà hàng')
    source = source.replace('Doanh thu, khách hàng và hóa đơn theo dữ liệu DB', 'Kết quả kinh doanh từ các giao dịch đã ghi nhận')
    source = source.replace("['occupied','#2475ff']", "['occupied','#e8b552']")
    return source

edit('static/admin/js/main.js', admin)

def customer(source):
    a = source.index('<section class="hero">')
    b = source.index('<section class="section container">', a)
    source = source[:a] + '''<section class="hero reference-hero"><div class="hero-shade"></div><div class="container hero-inner"><div class="hospitality-copy"><p class="hero-eyebrow">SMART RESTAURANT · GOOD FOOD, GOOD MOOD</p><h1>Trải nghiệm ẩm thực<br><span>thông minh</span></h1><p class="hero-description">Hương vị tuyệt hảo · Dịch vụ tận tâm · Không gian ấm cúng</p><div class="hero-buttons"><a class="button" href="{% url 'customer_booking' %}?view=new">Đặt bàn ngay →</a><a class="button button-outline" href="{% url 'customer_menu' %}">Xem thực đơn</a></div></div><aside class="home-booking"><h2>Đặt bàn ngay</h2><p>Chọn thời gian và số khách</p><form action="{% url 'customer_booking' %}" method="get"><input type="hidden" name="view" value="new"><div class="booking-quick-fields"><label>Ngày<input name="date" type="date" required></label><label>Giờ<input name="time" type="time" required></label></div><label>Số khách<input name="guests" type="number" min="1" max="100" value="2" required></label><button class="button">Tiếp tục đặt bàn →</button></form></aside></div></section>
<nav class="container home-quick" aria-label="Dịch vụ nhà hàng"><a href="{% url 'customer_booking' %}?view=new"><svg class="icon"><use href="#i-calendar"/></svg>Đặt bàn nhanh</a><a href="{% url 'customer_menu' %}"><svg class="icon"><use href="#i-food"/></svg>Đặt món online</a><a href="{% url 'customer_offers' %}"><svg class="icon"><use href="#i-cart"/></svg>Ưu đãi hấp dẫn</a><a href="{% url 'customer_combos' %}"><svg class="icon"><use href="#i-user"/></svg>Combo sum họp</a></nav>
''' + source[b:]
    a = source.index('<section class="suggestions">')
    b = source.index('<section class="container section home-combos">', a)
    source = source[:a] + source[b:]
    source = source.replace('{% endfor %}</div></section>', '{% empty %}<p class="empty-state">Thực đơn đang được cập nhật.</p>{% endfor %}</div></section>', 1)
    return source.replace('MÓN ĂN NỔI BẬT', 'Thực đơn nổi bật')

edit('templates/customer/home.html', customer)

def header(source):
    source = source.replace('<a href="{% url \'customer_combos\' %}{% if booking_menu %}?from=booking{% endif %}">Combo</a>', '')
    source = source.replace('>Giới thiệu</a>', '>Về chúng tôi</a>').replace('>Ưu đãi</a>', '>Khuyến mãi</a>')
    return source.replace('<a href="{% url \'ai_chat\' %}">Trợ lý AI</a>', '<a href="{% url \'customer_home\' %}#home-reviews">Đánh giá</a>')

edit('templates/customer/header.html', header)
edit('templates/customer/home.html', lambda s: s.replace('{% if home_reviews %}<section class="container section">', '<section id="home-reviews" class="container section"><div class="section-heading"><h2>Đánh giá từ khách hàng</h2></div>{% if home_reviews %}').replace('{% endfor %}</div></section>{% endif %}', '{% endfor %}</div>{% else %}<p class="empty-state">Chưa có đánh giá được công khai.</p>{% endif %}</section>'))

def map_fallback(source):
    a = source.index("tiles.on('tileerror'")
    b = source.index('const marker=', a)
    return source[:a] + """tiles.on('tileerror',()=>{if(tileFailure)return;tileFailure=true;map.removeLayer(tiles);const notice=document.createElement('p');notice.className='map-unavailable';notice.setAttribute('role','status');notice.textContent='Không thể tải bản đồ. Tọa độ và bán kính bên dưới vẫn sử dụng được.';host.after(notice);host.classList.add('map-fallback');});""" + source[b:]

edit('static/location/maps.js', map_fallback)
