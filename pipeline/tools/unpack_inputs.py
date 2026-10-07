"""Reassemble user-provided volumes and unpack known game images without replacing originals."""
from pathlib import Path
import shutil,sys,py7zr
root=Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve()
up=root/'upload'; tp=root/'tp_work'; sh=root/'sh_work';tp.mkdir(exist_ok=True);sh.mkdir(exist_ok=True)
def extract(archive,out):
 out.mkdir(parents=True,exist_ok=True)
 with py7zr.SevenZipFile(archive) as z:
  for n in z.getnames():
   if not (out/n).resolve().is_relative_to(out.resolve()):raise ValueError('Unsafe path in archive')
  z.extractall(out)
 print('Extracted',archive.name,flush=True)
extract(up/'Silent Hill (USA).7z',sh/'disc')
parts=[up/f'Legend of Zelda, The - Twilight Princess (USA)_2.7z.{i:03}' for i in range(1,5)]
with (tp/'combined.7z').open('wb') as dst:
 for part in parts:
  with part.open('rb') as src:shutil.copyfileobj(src,dst)
extract(tp/'combined.7z',tp/'nested')
extract(tp/'nested'/'Legend of Zelda, The - Twilight Princess (USA).7z',tp/'game')
