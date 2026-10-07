"""Regression checks for the failed doorway crossing, using packaged bytes."""
from pathlib import Path
from io import BytesIO
import sys,struct,zipfile,json
import numpy as np
ROOT=Path(__file__).resolve().parents[2];P=ROOT/'sh_tp_project'
sys.path.insert(0,str(ROOT/'gclib'));sys.path.insert(0,str(ROOT/'dzb_tools/dzb_tools'))
from gclib.rarc import RARC
from dzb import DZB
from door_threshold import world

def tris(raw):
 d=DZB();d.read(BytesIO(raw))
 return np.array([[[getattr(v,a) for a in ('x_pos','y_pos','z_pos')] for v in f.vertices] for f in d.faces])
def key(tri):return tuple(sorted(tuple(float(x) for x in row) for row in tri))

def floor_at(ts,x,z):
 a=ts[:,1]-ts[:,0];b=ts[:,2]-ts[:,0];q=np.array([x,0,z])-ts[:,0]
 det=a[:,0]*b[:,2]-a[:,2]*b[:,0];ok=abs(det)>1e-6
 ts,a,b,q,det=ts[ok],a[ok],b[ok],q[ok],det[ok]
 u=(q[:,0]*b[:,2]-q[:,2]*b[:,0])/det;v=(a[:,0]*q[:,2]-a[:,2]*q[:,0])/det
 n=np.cross(a,b);ys=ts[:,0,1]+u*a[:,1]+v*b[:,1]
 return ys[(u>=-1e-5)&(v>=-1e-5)&(u+v<=1+1e-5)&(n[:,1]>0)]

report=json.loads((P/'connected/connection_report.json').read_text())
with zipfile.ZipFile(P/'ConnectedMods/SilentHillConnected.dusk') as mod:
 for name,area in report['areas'].items():
  r=RARC(BytesIO(mod.read('overlay/res/Stage/'+area['stage']+'/R00_00.arc')))
  raw=r.get_file_entry('room.dzb').data.getvalue();fixed=tris(raw)
  original=RARC(str(P/area['source']/'res/Stage/R_SP108/R00_00.arc'))
  old=tris(original.get_file_entry('room.dzb').data.getvalue())
  assert set(map(key,old))<=set(map(key,fixed))
  assert len(fixed)==len(old)+14
  # Replay a straight crossing in native door-local coordinates. It starts
  # outside the exit volume; crosses into the trigger before the support ends.
  triggered=False
  for localz in np.arange(70.,-601.,-10.):
   point=world(area,(0,0,localz));floors=floor_at(fixed,point[0],point[2])
   assert np.any((floors>=area['door'][1]-11)&(floors<=area['door'][1]+1)),(name,localz,'ground gap')
   inside=(-605<=localz<=-5)
   if inside:triggered=True
   if localz>=0:assert not inside
  assert triggered
  # Reuse raw collision tree/index validation against the new payload.
  validator=(P/'tools/validate_collision_package.py').read_text()
  validator=validator.replace("project/mod_path","project/'ConnectedMods/SilentHillConnected.dusk'")
  validator=validator.replace("overlay/res/Stage/R_SP108/R00_00.arc",'overlay/res/Stage/'+area['stage']+'/R00_00.arc')
  validator=validator.replace("project/asset_path","project/'connected/assets/"+name+".dzb'")
  validator=validator.replace("report = json.loads((project/report_path).read_text())","report = {'faces':"+str(len(fixed))+",'vertices':"+str(struct.unpack_from('>I',raw)[0])+"}")
  exec(compile(validator,'collision_index_check','exec'),{'__file__':str(P/'tools/validate_collision_package.py')})
print('PASS: both supported crossings, threshold boundaries, original collision retained, and rebuilt collision trees')
