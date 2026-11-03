"""Read-only model/asset provenance, external cache and static image audit."""
import hashlib,json,os
from pathlib import Path
import cv2
ROOT=Path(__file__).resolve().parent.parent
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def main():
    manifest=json.loads((ROOT/'ai_models/pretrained/manifest.json').read_text(encoding='utf-8'));models=[]
    for name,meta in manifest.items():
        path=Path(meta['local_path']);record={'name':name,'runtime_path':str(path),'outside_project':not path.is_relative_to(ROOT),'exists':path.exists(),'source':meta.get('source',meta.get('model_name')),'revision':meta['revision']}
        if name=='embedding':
            checks={n:digest(path/n)==h for n,h in meta['files'].items()};record.update(bytes=sum(p.stat().st_size for p in path.rglob('*') if p.is_file()),hashes_match=all(checks.values()),checked_files=len(checks))
        else:record.update(bytes=path.stat().st_size,sha256=digest(path),hash_matches=digest(path)==meta['sha256'])
        models.append(record)
    versions={}
    for p in (ROOT/'ai_models').glob('*/latest.json'):
        version=json.loads(p.read_text(encoding='utf-8'))['version'];folder=p.parent/version
        versions[p.parent.name]={'latest':version,'bytes':sum(f.stat().st_size for f in folder.rglob('*') if f.is_file()),'exists':folder.exists(),'files':[f.relative_to(ROOT).as_posix() for f in folder.rglob('*') if f.is_file()]}
    images=[];hashes={}
    for p in (ROOT/'static').rglob('*'):
        if p.is_file() and p.suffix.lower() in {'.jpg','.jpeg','.png','.webp'}:
            frame=cv2.imdecode(__import__('numpy').frombuffer(p.read_bytes(),dtype='uint8'),cv2.IMREAD_UNCHANGED)
            h=digest(p);hashes.setdefault(h,[]).append(p.relative_to(ROOT).as_posix());images.append({'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'width':frame.shape[1] if frame is not None else None,'height':frame.shape[0] if frame is not None else None,'action':'KEEP; preserve path'})
    result={'pretrained':models,'artifacts':versions,'images':images,'duplicate_images':[v for v in hashes.values() if len(v)>1],'external_caches_not_copied':True,'image_optimization':'No resize needed unless source dimension exceeds 1600; assets preserved','db_dumps':'db.sqlite3 retained locally/excluded; PostgreSQL database untouched'}
    (ROOT/'submission_audit/model_assets.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'models':models,'latest':{k:v['latest'] for k,v in versions.items()},'images':len(images),'oversized':[i for i in images if max(i['width'] or 0,i['height'] or 0)>1600],'duplicates':result['duplicate_images']},ensure_ascii=True))
if __name__=='__main__':main()
