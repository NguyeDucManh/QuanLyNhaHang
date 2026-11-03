"""Explicit network operation; pinned upstream revisions and local SHA-256 manifest."""
import json
import urllib.request
from django.core.management.base import BaseCommand
from customers.ai.artifacts import root, write_json, read_json, sha256
from pathlib import Path

EMBEDDING='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
REVISION='e8f8c211226b894fcb81acc59f3b34ba3efd5f42'

class Command(BaseCommand):
    help='Download CPU FaceNet ONNX, MediaPipe landmarks and multilingual embedding with provenance.'
    def add_arguments(self,parser):
        parser.add_argument('--embedding-cache',help='Optional cache on a drive with enough free space.')
        parser.add_argument('--assets-cache',help='Optional cache for FaceNet and MediaPipe assets.')
    def handle(self,*args,**options):
        folder=root()/'pretrained'; folder.mkdir(parents=True,exist_ok=True)
        manifest=read_json(folder/'manifest.json') if (folder/'manifest.json').exists() else {}
        commit='b019d5bf79ddb3805f77f7650885b710b333b433'
        sources={
            'facenet.onnx':f'https://raw.githubusercontent.com/NicolasSM-001/faceNet.onnx-/{commit}/faceNet.onnx',
            'face_landmarker.task':'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task',
        }
        for name,url in sources.items():
            path=(Path(options['assets_cache']).resolve()/name) if options.get('assets_cache') else Path(manifest.get(name,{}).get('local_path',str(folder/name)))
            path.parent.mkdir(parents=True,exist_ok=True)
            expected=manifest.get(name,{}).get('sha256')
            if path.exists() and expected and sha256(path)!=expected:
                from django.core.management.base import CommandError
                raise CommandError('Cached model hash mismatch: '+name)
            if not path.exists():
                self.stdout.write('Downloading '+name)
                temporary=path.with_suffix('.download')
                with urllib.request.urlopen(url,timeout=120) as response, temporary.open('wb') as output:
                    while block:=response.read(1024*1024): output.write(block)
                temporary.replace(path)
            manifest[name]={'source':url,'revision':commit if name=='facenet.onnx' else 'float16/1','local_path':str(path),'sha256':sha256(path),'bytes':path.stat().st_size}
        import onnxruntime as ort
        session=ort.InferenceSession(manifest['facenet.onnx']['local_path'],providers=['CPUExecutionProvider'])
        manifest['facenet.onnx']['inputs']=[{'name':i.name,'shape':i.shape,'type':i.type} for i in session.get_inputs()]
        manifest['facenet.onnx']['outputs']=[{'name':i.name,'shape':i.shape} for i in session.get_outputs()]
        write_json(folder/'manifest.json',manifest)
        from huggingface_hub import snapshot_download
        embedding=Path(options['embedding_cache']).resolve() if options.get('embedding_cache') else Path(manifest.get('embedding',{}).get('local_path',str(folder/'embedding')))
        snapshot_download(EMBEDDING,revision=REVISION,local_dir=str(embedding),allow_patterns=['config.json','modules.json','config_sentence_transformers.json','sentence_bert_config.json','tokenizer.json','tokenizer_config.json','special_tokens_map.json','sentencepiece.bpe.model','model.safetensors','1_Pooling/*'])
        manifest['embedding']={'model_name':EMBEDDING,'revision':REVISION,'device':'cpu','local_path':str(embedding),'files':{str(p.relative_to(embedding)):sha256(p) for p in embedding.rglob('*') if p.is_file() and '.cache' not in p.parts}}
        write_json(folder/'manifest.json',manifest)
        self.stdout.write(json.dumps(manifest,ensure_ascii=True))
