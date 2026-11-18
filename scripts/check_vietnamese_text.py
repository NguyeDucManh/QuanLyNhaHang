"""Audit UTF-8/NFC and common irreversible/mojibake damage; never rewrite files."""
import json,re,sys,unicodedata
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
PATTERN=re.compile(r'\ufffd|\u00c3[\u0080-\u00bf]|\u00c2[\u0080-\u00bf]|\u00e1\u00ba|\u00e1\u00bb|\u00e2\u20ac|\u00f0\u0178|Ti\?n|Thanh to\?n|tr\?ng th\?i')

def audit(root=ROOT):
    findings=[]
    for folder in ('templates','customers','static'):
        for path in (root/folder).rglob('*'):
            if path.suffix not in ('.py','.html','.js','.css') or any(part in ('vendor','leaflet','vendor_maps','__pycache__') for part in path.parts) or path.name.startswith('test'):
                continue
            relative=path.relative_to(root).as_posix()
            try:text=path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                findings.append({'file':relative,'line':0,'reason':'invalid_utf8'});continue
            # Python explicitly permits a UTF-8 BOM; preserve historical
            # migrations/menu code. A template BOM emits unwanted page bytes.
            if path.suffix=='.html' and text.startswith('\ufeff'):findings.append({'file':relative,'line':1,'reason':'bom'})
            for number,line in enumerate(text.splitlines(),1):
                if PATTERN.search(line):findings.append({'file':relative,'line':number,'reason':'damaged_text'})
                if unicodedata.normalize('NFC',line)!=line:findings.append({'file':relative,'line':number,'reason':'non_nfc'})
    return findings

if __name__=='__main__':
    findings=audit();print(json.dumps({'findings':findings,'passed':not findings},ensure_ascii=True))
    sys.exit(bool(findings))
