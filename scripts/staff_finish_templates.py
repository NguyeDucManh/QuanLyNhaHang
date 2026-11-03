from pathlib import Path
root=Path(__file__).resolve().parent.parent
path=root/'templates/admin/business/kitchen.html';source=path.read_text(encoding='utf-8').replace('{% include "admin/business/_kitchen_content.html" %}',"{% if business_role == 'STAFF' %}{% include 'staff/kitchen_board.html' %}{% else %}{% include 'admin/business/_kitchen_content.html' %}{% endif %}").replace('Bếp | Kitchen Queue','Bếp').replace('Đang kết nối realtime','Đang kết nối trực tiếp');path.write_text(source,encoding='utf-8')
for relative in ['templates/staff/profile.html','templates/customer/account/profile.html']:
    path=root/relative;source=path.read_text(encoding='utf-8')
    form='<section class="staff-card"><h2>Cập nhật thông tin liên hệ</h2><form method="post">{% csrf_token %}{{ profile_form.as_p }}<button>Lưu thông tin cá nhân</button></form><p class="help-text">Mã nhân viên và chức vụ do quản lý cập nhật. Tên tài khoản và quyền không thay đổi tại đây.</p></section>'
    if 'profile_form' not in source:source=source.replace('{% endblock %}',form+'{% endblock %}') if relative.startswith('templates/staff') else source.replace('</div></section>',form+'</div></section>')
    source=source.replace('Username:','Tên tài khoản:').replace('Email:','Thư điện tử:').replace('{{ business_role }}','{{ business_role|ui_vi }}')
    if relative.endswith('account/profile.html') and 'load ui_vi' not in source:source=source.replace('{% block title %}','{% load ui_vi %}{% block title %}',1)
    path.write_text(source,encoding='utf-8')
