"""Validate reciprocal destinations and loader-critical data in the actual mod ZIP."""
from pathlib import Path
from io import BytesIO
import json,struct,sys,zipfile
ROOT=Path(__file__).resolve().parents[2];P=ROOT/'sh_tp_project'
sys.path.insert(0,str(ROOT/'gclib'))
from gclib.rarc import RARC
from gclib.j3d import BMD

def chunks(b):
 return {tag:(count,off) for tag,count,off in [struct.unpack_from('>4sII',b,4+i*12) for i in range(struct.unpack_from('>I',b)[0])]}

with zipfile.ZipFile(P/'ConnectedMods/SilentHillConnected.dusk') as z:
 assert z.testzip() is None
 assert json.loads(z.read('mod.json'))['version']=='0.3.1'
 targets={};report=json.loads((P/'connected/connection_report.json').read_text())
 for name,area in report['areas'].items():
  stage_name=area['stage'];prefix='overlay/res/Stage/'+stage_name+'/'
  r=RARC(BytesIO(z.read(prefix+'R00_00.arc')))
  assert r.get_file_entry('room.dzb').parent_node.type=='DZB '
  original=RARC(str(P/area['source']/'res/Stage/R_SP108/R00_00.arc'))
  for filename in ('model.bmd',):
   assert r.get_file_entry(filename).data.getvalue()==original.get_file_entry(filename).data.getvalue()
  assert r.get_file_entry('room.dzb').data.getvalue()==(P/'connected/assets'/(name+'.dzb')).read_bytes()
  b=r.get_file_entry('room.dzr').data.getvalue();c=chunks(b)
  assert c[b'TGSC'][0]==1
  from door_threshold import trigger_record
  assert b[c[b'TGSC'][1]:c[b'TGSC'][1]+36]==trigger_record(area)
  assert c[b'ACTR'][0]==1 and c[b'SCLS'][0]==1
  actor,param,x,y,zz,rx,ry,rz,sid=struct.unpack_from('>8sI3f3hH',b,c[b'ACTR'][1])
  assert actor.rstrip(b'\0')==b'kdoor' and ((param>>25)&63)==0
  assert ((param>>5)&7)==0 and rx==-1 and ry==area['facing']
  assert (x,y,zz)==tuple(area['door'])
  dest,start,room,time_a,time_b,wipe=struct.unpack_from('>8s5B',b,c[b'SCLS'][1])
  dest=dest.rstrip(b'\0').decode()
  assert dest==area['destination'] and (start,room,time_b&15)==(1,0,0)
  assert (((time_a>>4)&15)|(time_b&16))==31
  starts={}
  for i in range(c[b'PLYR'][0]):
   off=c[b'PLYR'][1]+i*32
   actor,param,x,y,zz,rx,ry,rz,sid=struct.unpack_from('>8sI3f3hH',b,off)
   starts[rz&255]=(x,y,zz,ry)
  assert starts[1]==(*area['arrival'],area['facing'])
  assert ((param>>12)&31)==0, 'Arrival should use normal standing mode'
  stage=RARC(BytesIO(z.read(prefix+'STG_00.arc')))
  BMD(stage.get_file_entry('door-knob_00.bmd').data)
  sb=stage.get_file_entry('stage.dzs').data.getvalue();sc=chunks(sb)
  assert sc[b'SCLS'][0]==1
  assert sb[sc[b'SCLS'][1]:sc[b'SCLS'][1]+13]==b[c[b'SCLS'][1]:c[b'SCLS'][1]+13]
  assert not any(tag in chunks(stage.get_file_entry('stage.dzs').data.getvalue()) for tag in (b'ACTR',b'TGSC'))
  targets[stage_name]=(dest,start,starts)
 for name,(dest,start,starts) in targets.items():
  assert dest in targets and start in targets[dest][2]
  assert targets[dest][0]==name
print('PASS connected 0.3.1: reciprocal exits, destination spawns, unrestricted kdoor actors, door models, unchanged model payloads; matching stage/room exits and threshold triggers')
