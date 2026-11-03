"""Vendor pinned Leaflet 1.9.4; record source/license/hash, no Python dependency changes."""
import hashlib,json,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parent.parent/'static/vendor/leaflet'; root.mkdir(parents=True,exist_ok=True)
names=['leaflet.js','leaflet.css','images/marker-icon.png','images/marker-icon-2x.png','images/marker-shadow.png','images/layers.png','images/layers-2x.png']
manifest={'version':'1.9.4','source':'https://github.com/Leaflet/Leaflet/tree/v1.9.4','files':{}}
for name in names:
    url='https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/'+name
    data=urllib.request.urlopen(url,timeout=60).read(); target=root/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(data)
    manifest['files'][name]={'url':url,'sha256':hashlib.sha256(data).hexdigest()}
license_url='https://raw.githubusercontent.com/Leaflet/Leaflet/v1.9.4/LICENSE'; (root/'LICENSE').write_bytes(urllib.request.urlopen(license_url,timeout=60).read())
(root/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('Leaflet 1.9.4 cached locally with hashes/license.')
