"""Export and merge three adjacent Old Silent Hill tiles in original coordinates."""
from pathlib import Path
import shutil,json,subprocess
ROOT=Path(__file__).resolve().parents[2];src=ROOT/'tp_work/town';out=ROOT/'sh_tp_project/town/source';bg=ROOT/'sh_work/assets/BG'
src.mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=True)
names=['THR0000','THR0001','THR0002']
for p in list(bg.glob('*.TIM'))+list(bg.glob('*.PLM')):shutil.copy2(p,src/p.name)
for name in names:
 shutil.copy2(bg/(name+'.IPD'),src/(name+'.IPD'))
 with (src/(name+'.log')).open('w') as log:subprocess.run([str(ROOT/'tp_work/ipd2obj'),name+'.IPD'],cwd=src,stdout=log,stderr=log,check=True)
lines=['mtllib TOWN.MTL'];materials={};vo=uo=0
for name in names:
 mat=None
 for line in (src/(name+'.MTL')).read_text().splitlines():
  s=line.split()
  if not s:continue
  if s[0]=='newmtl':mat=s[1]
  elif s[0]=='map_Kd':
   assert mat not in materials or materials[mat]==s[1]
   materials[mat]=s[1];shutil.copy2(src/s[1],out/s[1])
 nv=nu=0
 for line in (src/(name+'.OBJ')).read_text().splitlines():
  s=line.split()
  if not s:continue
  if s[0]=='v':nv+=1;lines.append(line)
  elif s[0]=='vt':nu+=1;lines.append(line)
  elif s[0]=='usemtl':lines.append(line)
  elif s[0]=='f':
   indices=[]
   for item in s[1:]:
    a=item.split('/');assert int(a[0])>0
    indices.append(str(int(a[0])+vo)+('/'+str(int(a[1])+uo) if len(a)>1 and a[1] else '/'))
   lines.append('f '+' '.join(indices))
 vo+=nv;uo+=nu
(out/'TOWN.OBJ').write_text('\n'.join(lines)+'\n')
(out/'TOWN.MTL').write_text('\n'.join('newmtl '+k+'\nmap_Kd '+v for k,v in materials.items())+'\n')
(out/'manifest.json').write_text(json.dumps({'source_tiles':names,'origin_metres':[-20,0,60],'alignment':'Original SH grid, 40 metres per tile; no tile repositioning'},indent=2)+'\n')
print('Merged',names,'vertices',vo,'textures',len(materials))
