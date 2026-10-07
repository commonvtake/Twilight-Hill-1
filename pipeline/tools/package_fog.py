"""Fog milestone: preserve connected 0.3.1 mechanics and patch outdoor appearance only."""
from pathlib import Path
from io import BytesIO
import sys,struct,json,zipfile,hashlib
ROOT=Path(__file__).resolve().parents[2];P=ROOT/'sh_tp_project'
sys.path.insert(0,str(ROOT/'gclib'))
from gclib.rarc import RARC
from gclib.j3d import BMD
from gclib.gx_enums import FogType

settings=json.loads((P/'fog/settings.json').read_text())
color=settings['color_rgb'];start=settings['start_cm'];end=settings['end_cm']
assert len(color)==3 and all(isinstance(c,int) and 0<=c<=255 for c in color)
assert 0<=start<end<=10000

def bmd_chunks(raw):
 off=32;chunks=[]
 for i in range(struct.unpack_from('>I',raw,12)[0]):
  size=struct.unpack_from('>I',raw,off+4)[0];chunks.append(raw[off:off+size]);off+=size
 assert off==len(raw)
 return chunks

def material_fog(raw):
 model=BMD(BytesIO(raw))
 for m in model.mat3.materials:
  fog=m.fog_info
  assert fog is not None
  fog.fog_type=FogType.LINEAR
  fog.start_z=start;fog.end_z=end
  fog.color.r,fog.color.g,fog.color.b=color;fog.color.a=255
  # 'enable' is GX fog RANGE ADJUSTMENT, not the fog on/off switch.
  # Nonzero fog_type enables fog; native lighting updates camera/adjustment data.
 model.mat3.save()
 chunks=[model.mat3.data.getvalue() if c[:4]==b'MAT3' else c for c in bmd_chunks(raw)]
 header=bytearray(raw[:32]);struct.pack_into('>I',header,8,32+sum(map(len,chunks)))
 result=bytes(header)+b''.join(chunks)
 check=BMD(BytesIO(result))
 assert all(m.fog_info.fog_type==FogType.LINEAR and m.fog_info.start_z==start and m.fog_info.end_z==end for m in check.mat3.materials)
 return result

def palette_fog(raw):
 b=bytearray(raw);counts={'palettes':0,'sky_palettes':0}
 for i in range(struct.unpack_from('>I',b)[0]):
  tag,count,offset=struct.unpack_from('>4sII',b,4+i*12)
  if tag[:3]==b'PAL':
   for j in range(count):
    at=offset+j*0x34
    b[at+0x21:at+0x24]=bytes(color)
    struct.pack_into('>2f',b,at+0x24,start,end)
    counts['palettes']+=1
  if tag[:3]==b'VRB':
   for j in range(count):
    at=offset+j*0x18
    for field in (0,3,6,9,13,17):b[at+field:at+field+3]=bytes(color)
    counts['sky_palettes']+=1
 assert counts['palettes']>0 and counts['sky_palettes']>0
 return bytes(b),counts

source=P/'ConnectedMods/SilentHillConnected.dusk'
with zipfile.ZipFile(source) as z:files={n:z.read(n) for n in z.namelist()}
room_key='overlay/res/Stage/R_SP109/R00_00.arc';stage_key='overlay/res/Stage/R_SP109/STG_00.arc'
room=RARC(BytesIO(files[room_key]));entry=room.get_file_entry('model.bmd')
entry.data=BytesIO(material_fog(entry.data.getvalue()));room.save_changes();files[room_key]=room.data.getvalue()
stage=RARC(BytesIO(files[stage_key]));entry=stage.get_file_entry('stage.dzs')
raw,counts=palette_fog(entry.data.getvalue());entry.data=BytesIO(raw)
stage.save_changes();files[stage_key]=stage.data.getvalue()
metadata={'id':'local.silent_hill.fog','name':'Silent Hill Fog and Door Test', 'version':'0.4.0',
 'author':'Personal crossover project','description':'One foggy street tile and cafe with 0.3.1 door fix. Full campaign is not implemented. Native runtime playtest pending.'}
files['mod.json']=(json.dumps(metadata,indent=2)+'\n').encode()
(P/'FogMods').mkdir(exist_ok=True)
with zipfile.ZipFile(P/'FogMods/SilentHillFogTest.dusk','w',zipfile.ZIP_DEFLATED) as z:
 for name,data in files.items():z.writestr(name,data)
report={'version':'0.4.0','source_version':'0.3.1','settings':settings,**counts,
 'model_materials':7,'runtime':'Not yet user tested','scope':'One street tile plus cafe; no full campaign',
 'files':{n:hashlib.sha256(b).hexdigest() for n,b in files.items()}}
(P/'fog/build_report.json').write_text(json.dumps(report,indent=2)+'\n')
print('Built 0.4.0: outdoor distance fog and sky palette; original door patch retained')
