"""Check appearance changes while preserving the door repair and terrain payloads."""
from pathlib import Path
from io import BytesIO
import sys,struct,json,zipfile
ROOT=Path(__file__).resolve().parents[2];P=ROOT/'sh_tp_project'
sys.path.insert(0,str(ROOT/'gclib'))
from gclib.rarc import RARC
from gclib.j3d import BMD
from gclib.gx_enums import FogType
s=json.loads((P/'fog/settings.json').read_text())
def chunks(b):
 off=32;result={}
 for i in range(struct.unpack_from('>I',b,12)[0]):
  n=struct.unpack_from('>I',b,off+4)[0];result[b[off:off+4]]=b[off:off+n];off+=n
 return result
with zipfile.ZipFile(P/'FogMods/SilentHillFogTest.dusk') as fog,zipfile.ZipFile(P/'ConnectedMods/SilentHillConnected.dusk') as base:
 assert fog.testzip() is None
 for filename in ('R00_00.arc','STG_00.arc'):
  key='overlay/res/Stage/R_SP108/'+filename
  assert fog.read(key)==base.read(key), 'Cafe changed'
 key='overlay/res/Stage/R_SP109/R00_00.arc'
 fr=RARC(BytesIO(fog.read(key)));br=RARC(BytesIO(base.read(key)))
 for name in ('room.dzr','room.dzb'):assert fr.get_file_entry(name).data.getvalue()==br.get_file_entry(name).data.getvalue()
 assert fr.get_file_entry('room.dzb').parent_node.type=='DZB '
 model=fr.get_file_entry('model.bmd').data.getvalue();original=br.get_file_entry('model.bmd').data.getvalue()
 original_chunks=chunks(original)
 for tag,data in chunks(model).items():
  if tag!=b'MAT3':assert data==original_chunks[tag],tag
 for m in BMD(BytesIO(model)).mat3.materials:
  f=m.fog_info
  assert f.fog_type==FogType.LINEAR
  assert f.start_z==s['start_cm'] and f.end_z==s['end_cm']
  assert [f.color.r,f.color.g,f.color.b]==s['color_rgb']
 key='overlay/res/Stage/R_SP109/STG_00.arc'
 fr=RARC(BytesIO(fog.read(key)));br=RARC(BytesIO(base.read(key)))
 for e in fr.file_entries:
  if not e.is_dir and e.name!='stage.dzs':assert e.data.getvalue()==br.get_file_entry(e.name).data.getvalue()
 b=fr.get_file_entry('stage.dzs').data.getvalue();old=br.get_file_entry('stage.dzs').data.getvalue();expected=bytearray(old)
 for i in range(struct.unpack_from('>I',b)[0]):
  tag,n,off=struct.unpack_from('>4sII',b,4+i*12)
  if tag[:3]==b'PAL':
   for j in range(n):
    at=off+j*0x34;expected[at+0x21:at+0x24]=bytes(s['color_rgb']);struct.pack_into('>2f',expected,at+0x24,s['start_cm'],s['end_cm'])
  if tag[:3]==b'VRB':
   for j in range(n):
    for field in (0,3,6,9,13,17):at=off+j*0x18+field;expected[at:at+3]=bytes(s['color_rgb'])
 assert b==bytes(expected), 'Changes beyond palettes'
print('PASS 0.4.0: all 7 street materials use native fog; every palette updated; geometry, textures, doors, exits and collision unchanged')
