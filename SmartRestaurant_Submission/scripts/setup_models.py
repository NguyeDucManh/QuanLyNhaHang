"""Explicit pretrained setup outside source; --reuse-existing is offline/hash checked."""
import argparse,json,hashlib,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cache-root',type=Path,default=Path.home()/'.cache'/'smart-restaurant');parser.add_argument('--reuse-existing',action='store_true');args=parser.parse_args()
    cache=args.cache_root.resolve();manifest_file=ROOT/'ai_models/pretrained/manifest.json';manifest=json.loads(manifest_file.read_text(encoding='utf-8'))
    targets={'facenet.onnx':cache/'face-assets'/'facenet.onnx','face_landmarker.task':cache/'face-assets'/'face_landmarker.task','embedding':cache/'paraphrase-multilingual-MiniLM-L12-v2-e8f8c211'}
    if args.reuse_existing:
        def sha(p):
            h=hashlib.sha256()
            with p.open('rb') as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
            return h.hexdigest()
        for name,path in targets.items():
            if name=='embedding':
                for filename,expected in manifest[name]['files'].items():
                    if sha(path/filename.replace('\\','/'))!=expected:raise ValueError('Embedding hash mismatch')
            elif sha(path)!=manifest[name]['sha256']:raise ValueError('Asset hash mismatch: '+name)
        for name,path in targets.items():manifest[name]['local_path']=str(path)
        manifest_file.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Offline pretrained cache verified and configured; no models copied.')
    else:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE','restaurant_system.settings')
        import django;django.setup()
        from django.core.management import call_command
        call_command('download_ai_models',assets_cache=str(cache/'face-assets'),embedding_cache=str(targets['embedding']))
if __name__=='__main__':main()
