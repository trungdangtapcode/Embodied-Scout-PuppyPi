from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,urllib.request,time
out=Path('data/models/tracking')
assets=[
('sam2.1_hiera_tiny.pt','https://huggingface.co/facebook/sam2.1-hiera-tiny/resolve/de431c4043854a71d8101e17995dfe596bf101a5/sam2.1_hiera_tiny.pt',156008466,'sha256','7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69'),
('cutie-base-mega.pth','https://github.com/hkchengrex/Cutie/releases/download/v1.0/cutie-base-mega.pth',140443788,'md5','a6071de6136982e396851903ab4c083a'),
('backbones/resnet18-5c106cde.pth','https://download.pytorch.org/models/resnet18-5c106cde.pth',None,None,None),
('backbones/resnet50-19c8e357.pth','https://download.pytorch.org/models/resnet50-19c8e357.pth',None,None,None),
]
def download(item):
 name,url,size,alg,expected=item;p=out/name;start=time.monotonic()
 if not p.exists():
  tmp=p.with_suffix(p.suffix+'.partial')
  req=urllib.request.Request(url,headers={'User-Agent':'PuppyPi-upstream-probe'})
  with urllib.request.urlopen(req,timeout=60) as src,tmp.open('wb') as dst:
   while block:=src.read(1024*1024):dst.write(block)
  tmp.rename(p)
 raw=p.read_bytes();sha=hashlib.sha256(raw).hexdigest()
 if size is not None and len(raw)!=size:raise RuntimeError(f'Wrong size: {name}')
 if expected and hashlib.new(alg,raw).hexdigest()!=expected:raise RuntimeError(f'Wrong {alg}: {name}')
 rec={'file':str(p),'url':url,'bytes':len(raw),'sha256':sha,'author_metadata_algorithm':alg,'author_metadata_digest':expected,'elapsed_s':time.monotonic()-start}
 print(json.dumps(rec),flush=True);return rec
with ThreadPoolExecutor(max_workers=4) as pool:
 results=list(pool.map(download,assets))
Path('runs/tracking-probe-2026-11-02/assets.json').write_text(json.dumps(results,indent=2)+'\n')
