import re
from pathlib import Path
root=Path(__file__).resolve().parent.parent
path=root/'templates/staff/payroll.html';source=path.read_text(encoding='utf-8');source=re.sub(r'<section class="staff-stats payroll-stats">.*?</section>',"{% include 'staff/payroll_stats.html' %}",source,flags=re.S);path.write_text(source,encoding='utf-8')
path=root/'templates/staff/base.html';source=path.read_text(encoding='utf-8').replace('<a class="staff-notice" href="{% url \'chat\' %}"', '<a class="staff-notice" href="{% url \'my_work\' %}?tab=schedule" aria-label="Lịch và thông báo ca làm"><svg class="staff-icon"><use href="#s-calendar"/></svg></a><a class="staff-notice" href="{% url \'chat\' %}"');path.write_text(source,encoding='utf-8')
