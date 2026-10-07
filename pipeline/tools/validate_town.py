"""Check package preservation, fog, road joins, and registered PC configuration."""
from pathlib import Path
from io import BytesIO
import sys,zipfile,json
import numpy as np
ROOT=Path(__file__).resolve().parents[2];P=ROOT/'sh_tp_project';sys.path.insert(0,str(ROOT/'gclib'))
from gclib.rarc import RARC
from gclib.j3d import BMD
from gclib.gx_enums import FogType
key='overlay/res/Stage/R_SP109/R00_00.arc'
with zipfile.ZipFile(P/'FogMods/SilentHillFogTest.dusk') as old,zipfile.ZipFile(P/'TownMods/SilentHillTown.dusk') as new:
 assert new.testzip() is None
 for n in old.namelist():
  if n not in [key,'mod.json']:assert old.read(n)==new.read(n),n
 a=RARC(BytesIO(old.read(key)));b=RARC(BytesIO(new.read(key)))
 assert a.get_file_entry('room.dzr').data.getvalue()==b.get_file_entry('room.dzr').data.getvalue()
 model=BMD(b.get_file_entry('model.bmd').data)
 assert len(model.mat3.materials)==9
 for m in model.mat3.materials:assert m.fog_info.fog_type==FogType.LINEAR and m.fog_info.start_z==500 and m.fog_info.end_z==1800
# Road-centre footprints, including joins at z +/- 2000 cm.
a=np.load(P/'town/assets/town_collision_source.npz');t=a['vertices'][a['faces']]
ab=t[:,1]-t[:,0];ac=t[:,2]-t[:,0];normal=np.cross(ab,ac)
den=ab[:,0]*ac[:,2]-ab[:,2]*ac[:,0];valid=abs(den)>1e-5
samples=0
for z in list(range(-5900,5901,25))+[-2000,2000]:
 for dx,dz in [(0,0),(-30,-30),(-30,30),(30,-30),(30,30)]:
  x=1000+dx;zz=z+dz;px=x-t[:,0,0];pz=zz-t[:,0,2]
  u=np.divide(px*ac[:,2]-pz*ac[:,0],den,out=np.zeros_like(den),where=valid)
  v=np.divide(ab[:,0]*pz-ab[:,2]*px,den,out=np.zeros_like(den),where=valid)
  y=t[:,0,1]+u*ab[:,1]+v*ac[:,1];mask=valid&(u>=-1e-5)&(v>=-1e-5)&(u+v<=1.00001)
  assert np.any(mask&(normal[:,1]>0)&(abs(y)<2)),('Missing road floor',x,zz)
  assert not np.any(mask&(y>10)&(y<190)),('Obstructed road',x,zz)
  samples+=1
profile=json.loads((P/'profiles/i5-12400F-RTX3060.json').read_text())
settings=(ROOT/'dusklight_src/src/dusk/settings.cpp').read_text()
for key in profile:assert '"'+key+'"' in settings,key
assert profile['game.enableFrameInterpolation']==1 and profile['video.maxFrameRate']==60
assert profile['video.lastWindowWidth']==1920 and profile['video.lastWindowHeight']==1080
report={'package_preservation':'cafe, exits, actors and stage palettes unchanged from 0.4.0','road_footprint_samples':samples,'road_sample_spacing_cm':25,'road_headroom_cm':190,'materials':9,'pc_config_keys':'all registered in pinned Dusklight 2.0.3 source','windows_runtime_tested':False,'powershell_executed':False}
(P/'town/validation_report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
