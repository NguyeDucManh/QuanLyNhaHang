from pathlib import Path
root=Path(__file__).resolve().parent.parent
path=root/'templates/staff/base.html';source=path.read_text(encoding='utf-8').replace('</head>', '<link rel="stylesheet" href="{% static \'ui/staff-refinements.css\' %}"></head>')
path.write_text(source,encoding='utf-8')
path=root/'templates/staff/work.html';source=path.read_text(encoding='utf-8')
source=source.replace('<section class="staff-card"><div class="staff-week-heading">',"{% if not request.GET.tab or request.GET.tab == 'schedule' %}<section class=\"staff-card\"><div class=\"staff-week-heading\">")
source=source.replace('<section class="staff-card" id="attendance">',"{% endif %}{% if not request.GET.tab or request.GET.tab == 'attendance' %}<section class=\"staff-card\" id=\"attendance\">")
source=source.replace('<section class="staff-card" id="payroll">',"{% endif %}{% if not request.GET.tab or request.GET.tab == 'payroll' %}<section class=\"staff-card\" id=\"payroll\">")
source=source.replace('</section>{% endblock %}','</section>{% endif %}{% endblock %}');path.write_text(source,encoding='utf-8')
