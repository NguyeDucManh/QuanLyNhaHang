from pathlib import Path
root=Path(__file__).resolve().parent.parent
path=root/'templates/customer/ai/realtime_attendance.html';source=path.read_text(encoding='utf-8')
if 'data-server-distance' not in source:source=source.replace('<span data-geo-distance>','<span data-server-distance>Khoảng cách server: chờ kiểm tra</span><span data-geo-distance>')
if 'data-location-server' not in source:source=source.replace('<button type="button" class="button-secondary" data-stop>', '<button type="button" class="button-secondary" data-location-server>Kiểm tra phạm vi server</button><button type="button" class="button-secondary" data-stop>')
path.write_text(source,encoding='utf-8')
(root/'templates/admin/ai/faces.html').write_text("{% extends 'index.html' %}{% block admin_content %}{% include 'admin/ai/operational_faces.html' %}{% endblock %}\n",encoding='utf-8')
(root/'templates/admin/ai/face_test.html').write_text("{% extends 'index.html' %}{% block admin_content %}{% include 'admin/ai/straight_test.html' %}{% endblock %}\n",encoding='utf-8')
(root/'templates/customer/ai/face_attendance.html').write_text("{% extends 'customer/base.html' %}{% load static %}{% block content %}{% include 'customer/ai/realtime_attendance.html' %}{{ location_config|json_script:'location-config' }}<script defer src=\"{% static 'ai/face-realtime.js' %}\"></script>{% endblock %}\n",encoding='utf-8')
path=root/'static/ai/face-flow.js'
source=path.read_text(encoding='utf-8').replace("querySelectorAll('[data-face-flow]')","querySelectorAll('[data-face-flow=\"enrollment\"]')")
source=source.replace("const saved=await post(host.dataset.saveUrl,{frames});", "if(!host.querySelector('[data-consent]')?.checked)throw new Error('Cần xác nhận consent trước khi lưu FaceID.');const saved=await post(host.dataset.saveUrl,{frames,consent:true});")
path.write_text(source,encoding='utf-8')
for name in ['templates/index.html','templates/customer/ai/face_attendance.html']:
    path=root/name;source=path.read_text(encoding='utf-8')
    if 'ai/face-realtime.css' not in source:
        source=source.replace('{% block content %}', '{% block content %}<link rel="stylesheet" href="{% static \'ai/face-realtime.css\' %}">') if name.endswith('face_attendance.html') else source.replace('</head>','<link rel="stylesheet" href="{% static \'ai/face-realtime.css\' %}">\n</head>')
    path.write_text(source,encoding='utf-8')
path=root/'templates/index.html';source=path.read_text(encoding='utf-8')
if "ai/face-realtime.js" not in source:source=source.replace("<script defer src=\"{% static 'ai/face-flow.js' %}\"></script>","<script defer src=\"{% static 'ai/face-flow.js' %}\"></script>\n  <script defer src=\"{% static 'ai/face-realtime.js' %}\"></script>")
path.write_text(source,encoding='utf-8')
path=root/'templates/admin/ai/enrollment.html';source=path.read_text(encoding='utf-8').replace('Sau enrollment, cần ảnh validation/test riêng để hiệu chỉnh threshold trước khi chấm công.','Sau enrollment có thể test bằng ngưỡng PROVISIONAL; cần validation/test riêng để hiệu chỉnh thật.')
if 'data-consent' not in source: source=source.replace('<button type="button" data-save-face disabled>','<label><input type="checkbox" data-consent> Người được đăng ký đã đồng ý thu và sử dụng mẫu FaceID.</label><button type="button" data-save-face disabled>')
path.write_text(source,encoding='utf-8')
path=root/'templates/customer/header.html';source=path.read_text(encoding='utf-8')
if 'Nhân sự → Chấm công' not in source: source=source.replace('<a href="{% url \'my_work\' %}">','<a href="{% url \'face_attendance\' %}">Nhân sự → Chấm công</a><a href="{% url \'my_work\' %}">')
path.write_text(source,encoding='utf-8')
