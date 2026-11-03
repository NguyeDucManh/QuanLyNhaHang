from pathlib import Path
root=Path(__file__).resolve().parent.parent
for directory in ['templates/admin/business','templates/admin/module07','templates/admin/restaurant']:
    for path in (root/directory).glob('*.html'):
        source=path.read_text(encoding='utf-8').replace('{% extends "index.html" %}','{% extends management_base %}').replace("{% extends 'index.html' %}",'{% extends management_base %}')
        path.write_text(source,encoding='utf-8')
path=root/'templates/customer/ai/face_attendance.html';source=path.read_text(encoding='utf-8').replace("{% extends 'customer/base.html' %}",'{% extends personal_base %}');path.write_text(source,encoding='utf-8')
for relative in ['templates/staff/base.html','templates/index.html','templates/customer/base.html']:
    path=root/relative;source=path.read_text(encoding='utf-8')
    if 'ui/product-polish.css' not in source:source=source.replace('</head>','<link rel="stylesheet" href="{% static \'ui/product-polish.css\' %}"></head>')
    if relative.endswith('customer/base.html'):source=source.replace('<body>','<body class="customer-shell">')
    path.write_text(source,encoding='utf-8')
path=root/'templates/customer/auth/login.html';source=path.read_text(encoding='utf-8').replace('WELCOME BACK','CHÀO MỪNG TRỞ LẠI');path.write_text(source,encoding='utf-8')
(root/'templates/shared/module07/chat_content.html').write_text("{% include 'shared/module07/chat_app.html' %}\n",encoding='utf-8')
(root/'templates/shared/module07/chat_messages.html').write_text('''{% load ui_vi %}{% for m in chat_messages reversed %}<article class="human-message {% if m.sender_id == request.user.pk %}own{% endif %}"><span class="human-message-avatar">{{ m.sender.get_full_name|default:m.sender.username|first }}</span><div class="human-message-bubble"><strong>{{ m.sender.get_full_name|default:m.sender.username }}</strong><p>{{ m.content|linebreaksbr }}</p><time>{{ m.created_at|ui_vi }}</time></div></article>{% empty %}<p class="chat-empty">Chưa có tin nhắn.</p>{% endfor %}{% if pagination %}{% include 'admin/restaurant/_pagination.html' %}{% endif %}''',encoding='utf-8')
