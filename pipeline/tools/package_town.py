"""Replace the street scene in the fog build with three aligned street tiles."""
from pathlib import Path
from io import BytesIO
import sys,struct,json,zipfile,hashlib
ROOT=Path(__file__).resolve().parents[2];P=ROOT/'sh_tp_project'
sys.path.insert(0,str(ROOT/'gclib'))
from gclib.rarc import RARC
from gclib.j3d import BMD
from gclib.gx_enums import FogType
from door_threshold import supported_collision
settings=json.loads((P/'fog/settings.json').read_text())
raw=(P/'town/assets/town.bmd').read_bytes();model=BMD(BytesIO(raw))
for m in model.mat3.materials:
 f=m.fog_info;f.fog_type=FogType.LINEAR;f.start_z=settings['start_cm'];f.end_z=settings['end_cm']
 f.color.r,f.color.g,f.color.b=settings['color_rgb'];f.color.a=255
model.mat3.save();chunks=[];off=32
for _ in range(struct.unpack_from('>I',raw,12)[0]):
 size=struct.unpack_from('>I',raw,off+4)[0];c=raw[off:off+size]
 chunks.append(model.mat3.data.getvalue() if c[:4]==b'MAT3' else c);off+=size
header=bytearray(raw[:32]);struct.pack_into('>I',header,8,32+sum(map(len,chunks)))
model_data=bytes(header)+b''.join(chunks)
area={'door':[-60.,14.84375,-350.],'facing':16384}
collision,added=supported_collision((P/'town/assets/town.dzb').read_bytes(),area)
(P/'town/assets/town_supported.dzb').write_bytes(collision)
with zipfile.ZipFile(P/'FogMods/SilentHillFogTest.dusk') as z:files={n:z.read(n) for n in z.namelist()}
key='overlay/res/Stage/R_SP109/R00_00.arc';room=RARC(BytesIO(files[key]))
room.get_file_entry('model.bmd').data=BytesIO(model_data)
room.get_file_entry('room.dzb').data=BytesIO(collision)
room.save_changes();files[key]=room.data.getvalue()
files['mod.json']=(json.dumps({'id':'local.silent_hill.town','name':'Silent Hill Three-Tile Town Test','version':'0.5.0','author':'Personal crossover project','description':'Three original street tiles, native distance fog, cafe and experimental door repair. No campaign progression. Windows playtest required.'},indent=2)+'\n').encode()
(P/'TownMods').mkdir(exist_ok=True)
with zipfile.ZipFile(P/'TownMods/SilentHillTown.dusk','w',zipfile.ZIP_DEFLATED) as z:
 for n,b in files.items():z.writestr(n,b)
report={'version':'0.5.0','tiles':['THR0000','THR0001','THR0002'],'route_length_m':120,'model_bytes':len(model_data),'collision_bytes':len(collision),'door_support_faces':len(added),'runtime_tested':False,'full_campaign':False,'files':{n:hashlib.sha256(b).hexdigest() for n,b in files.items()}}
(P/'town/build_report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
