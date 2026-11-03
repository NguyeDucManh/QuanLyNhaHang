from pathlib import Path
root=Path(__file__).resolve().parent.parent
path=root/'templates/staff/base.html';source=path.read_text(encoding='utf-8').replace('{% block content %}{% endblock %}','<div id="server-content">{% block content %}{% endblock %}</div>');path.write_text(source,encoding='utf-8')
