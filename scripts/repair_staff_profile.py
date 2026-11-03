from pathlib import Path
path=Path(__file__).resolve().parent.parent/'templates/staff/profile.html'
source=path.read_text(encoding='utf-8')
form='<section class="staff-card"><h2>Cập nhật thông tin liên hệ</h2><form method="post">{% csrf_token %}{{ profile_form.as_p }}<button>Lưu thông tin cá nhân</button></form><p class="help-text">Mã nhân viên và chức vụ do quản lý cập nhật. Tên tài khoản và quyền không thay đổi tại đây.</p></section>'
source=source.replace(form,'');head,marker,tail=source.rpartition('{% endblock %}');path.write_text(head+form+marker+tail,encoding='utf-8')
