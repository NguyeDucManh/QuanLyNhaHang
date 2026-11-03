"""Read source census; compile every template; verify named links/static/menu images."""
import ast,hashlib,json,os,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT));os.environ.setdefault('DJANGO_SETTINGS_MODULE','restaurant_system.settings')
import django;django.setup()
from django.template.loader import get_template
from django.urls import get_resolver
from django.contrib.staticfiles import finders
from customers.models import MenuItem
files=[];errors=[];names=set(get_resolver().reverse_dict.keys())
for directory in ['customers','restaurant_system','templates','static','docs']:
    for path in (ROOT/directory).rglob('*'):
        if not path.is_file() or '__pycache__' in path.parts or 'vendor' in path.parts or path.suffix not in ['.py','.html','.css','.js','.md']:continue
        source=path.read_text(encoding='utf-8-sig');item={'path':path.relative_to(ROOT).as_posix(),'lines':len(source.splitlines()),'sha256':hashlib.sha256(source.encode()).hexdigest()}
        if path.suffix=='.py':
            try:tree=ast.parse(source);item['definitions']=[node.name for node in ast.walk(tree) if isinstance(node,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef))]
            except SyntaxError as exc:errors.append({'path':item['path'],'error':str(exc)})
        if path.suffix=='.html':
            try:get_template(path.relative_to(ROOT/'templates').as_posix())
            except Exception as exc:errors.append({'path':item['path'],'error':str(exc)})
            for name in re.findall(r"{%\s*url\s+['\"]([^'\"]+)['\"]",source):
                if name not in names:errors.append({'path':item['path'],'missing_url_name':name})
            for asset in re.findall(r"{%\s*static\s+['\"]([^'\"]+)['\"]",source):
                if not finders.find(asset):errors.append({'path':item['path'],'missing_static':asset})
        files.append(item)
for menu in MenuItem.objects.all():
    if menu.image and not finders.find(menu.image):errors.append({'menu_id':menu.pk,'missing_image':menu.image})
result={'source_files_read':len(files),'source_census':files,'errors':errors,'scope':'All local source text (not .env/secrets/vendor). AST/template/named link/static/catalog image audit. Runtime action URLs additionally verified by live E2E.'}
output=ROOT/'qa_final/source_audit.json';output.parent.mkdir(exist_ok=True);output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'source_files_read':len(files),'errors':errors},ensure_ascii=True))
