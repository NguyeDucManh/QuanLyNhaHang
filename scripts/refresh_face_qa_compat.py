from pathlib import Path
root=Path(__file__).resolve().parent.parent
path=root/'scripts/final_live_e2e.py';source=path.read_text(encoding='utf-8')
source=source.replace('[data-location-check]','[data-location-start]').replace('[data-run-verify]','[data-punch=in]')
source=source.replace('.textContent.includes("trong phạm vi")','.textContent.includes("trong phạm vi")')
path.write_text(source,encoding='utf-8')
path=root/'templates/customer/header.html';source=path.read_text(encoding='utf-8')
link='<a href="{% url \'face_attendance\' %}">Nhân sự → Chấm công</a>'
while link+link in source:source=source.replace(link+link,link)
path.write_text(source,encoding='utf-8')
