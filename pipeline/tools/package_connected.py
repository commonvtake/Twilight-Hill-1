"""Connect the cafe and street with native kdoor actors and reciprocal SCLS exits.

Uses the original Zelda door mesh/animation for this first connection test.
Preserves original DZX offsets (RTBL has nested absolute offsets).
"""
from pathlib import Path
from io import BytesIO
import sys, struct, json, zipfile, hashlib
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
P = ROOT/'sh_tp_project'
sys.path.insert(0, str(ROOT/'gclib'))
from gclib.rarc import RARC
from gclib.j3d import BMD
from door_threshold import trigger_record,supported_collision

AREAS = {
    'cafe': dict(stage='R_SP108', destination='R_SP109', source='overlay',
                 door=[265.,0.,50.], facing=-16384,
                 arrival=[95.,5.,50.], collision='assets/cafe_collision_source.npz'),
    'street': dict(stage='R_SP109', destination='R_SP108', source='outdoor/overlay',
                   door=[-60.,14.84375,-350.], facing=16384,
                   arrival=[160.,19.84375,-350.], collision='outdoor/assets/outdoor_collision_source.npz'),
}

def entries(raw):
    return [struct.unpack_from('>4sII', raw, 4+i*12)
            for i in range(struct.unpack_from('>I',raw)[0])]

def vertical_hits(tris, x, z):
    hits=[]
    for tri in tris:
        p=tri[:,[0,2]]
        matrix=np.array([p[1]-p[0],p[2]-p[0]]).T
        if abs(np.linalg.det(matrix)) < 1e-6: continue
        u,v=np.linalg.solve(matrix,np.array([x,z])-p[0])
        if u>=-1e-5 and v>=-1e-5 and u+v<=1+1e-5:
            n=np.cross(tri[1]-tri[0],tri[2]-tri[0]);n/=np.linalg.norm(n)
            hits.append((float(tri[0,1]+u*(tri[1,1]-tri[0,1])+v*(tri[2,1]-tri[0,1])),n[1]))
    return hits

def check_clearance(area):
    data=np.load(P/area['collision']);tris=data['vertices'][data['faces']]
    x,y,z=area['arrival'];floor=y-5
    for dx in (-30,0,30):
        for dz in (-30,0,30):
            hits=vertical_hits(tris,x+dx,z+dz)
            assert any(abs(h-floor)<2 and ny>.7 for h,ny in hits), 'Arrival has no floor'
            assert not any(floor+10<h<floor+190 for h,ny in hits), 'Arrival obstructed'
    # The door animation places Link 70 cm along its local +Z axis.
    forward=np.array([np.sin(area['facing']*np.pi/32768),np.cos(area['facing']*np.pi/32768)])
    for distance in (70,100,140):
        q=np.array(area['door'])[[0,2]]+forward*distance
        hits=vertical_hits(tris,*q)
        assert any(abs(h-area['door'][1])<2 and ny>.7 for h,ny in hits)
        assert not any(area['door'][1]+10<h<area['door'][1]+190 for h,ny in hits)

def room_data(raw, area):
    b=bytearray(raw); table=entries(b)
    assert not any(tag in (b'ACTR',b'SCLS',b'TGSC') for tag,_,_ in table)
    # There is spare header space left by the original sanitized template.
    assert 4+(len(table)+3)*12 <= min(offset for _,_,offset in table)
    for tag,count,offset in table:
        if tag==b'PLYR':
            assert count>=2
            # Spawn zero remains the original launch position. Spawn one is the return.
            off=offset+32
            struct.pack_into('>I3f3hH',b,off+8,0xff000000,*area['arrival'],
                             0,area['facing'],-255,65535)
    b.extend(b'\0'*((-len(b))%4))
    actor_offset=len(b)
    # Parameter bits 5..7 model=0, 8..10 lighting=0, 25..30 exit index=0.
    # X angle 0xffff disables message-flow restrictions in checkOpenDoor().
    b.extend(struct.pack('>8sI3f3hH',b'kdoor',0,*area['door'],-1,area['facing'],0,65535))
    table.append((b'ACTR',1,actor_offset))
    exit_offset=len(b)
    # 13-byte SCLS: name, spawn, room, packed time/layer, wipe.
    # Time=31 leaves time unchanged; layer=0, black fade=0.
    b.extend(struct.pack('>8s5B',area['destination'].encode(),1,0,0xf0,0x10,0))
    table.append((b'SCLS',1,exit_offset))
    b.extend(b'\0'*((-len(b))%4))
    trigger_offset=len(b);b.extend(trigger_record(area))
    table.append((b'TGSC',1,trigger_offset))
    b.extend(b'\0'*((-len(b))%32))
    struct.pack_into('>I',b,0,len(table))
    for i,row in enumerate(table):struct.pack_into('>4sII',b,4+i*12,*row)
    return BytesIO(b)

out=P/'connected/overlay/res/Stage'
report={'version':'0.3.1','runtime_status':'Pending Windows playtest',
        'interaction':'Native Zelda kdoor plus scnChg threshold behind the closed door',
        'fix':'Explicit doorway exit trigger and supported crossing; log showed no destination room load',
        'areas':AREAS,'files':{}}
for name,area in AREAS.items():
    check_clearance(area)
    source=P/area['source']/'res/Stage/R_SP108'
    dest=out/area['stage'];dest.mkdir(parents=True,exist_ok=True)
    room=RARC(str(source/'R00_00.arc'))
    assert room.get_file_entry('room.dzb').parent_node.type=='DZB '
    collision=room.get_file_entry('room.dzb')
    fixed,added=supported_collision(collision.data.getvalue(),area)
    collision.data=BytesIO(fixed)
    assetdir=P/'connected/assets';assetdir.mkdir(exist_ok=True)
    (assetdir/(name+'.dzb')).write_bytes(fixed)
    np.save(assetdir/(name+'_support.npy'),added)
    dzr=room.get_file_entry('room.dzr');dzr.data=room_data(dzr.data.getvalue(),area)
    room.save_changes();(dest/'R00_00.arc').write_bytes(room.data.getvalue())
    stage=RARC(str(source/'STG_00.arc'))
    # During a door demo Link may temporarily have no room affiliation (-1).
    # Native changeScene then uses stage SCLS instead of room SCLS.
    entry=stage.get_file_entry('stage.dzs');b=bytearray(entry.data.getvalue());table=entries(b)
    assert not any(t[0]==b'SCLS' for t in table)
    assert 4+(len(table)+1)*12 <= min(t[2] for t in table)
    b.extend(b'\0'*((-len(b))%4));off=len(b)
    b.extend(struct.pack('>8s5B',area['destination'].encode(),1,0,0xf0,0x10,0))
    table.append((b'SCLS',1,off));struct.pack_into('>I',b,0,len(table))
    for i,row in enumerate(table):struct.pack_into('>4sII',b,4+i*12,*row)
    b.extend(b'\0'*((-len(b))%32));entry.data=BytesIO(b);stage.save_changes()
    # Required by the kdoor actor; animation/collision come from stock static/DoorK10.
    BMD(stage.get_file_entry('door-knob_00.bmd').data)
    (dest/'STG_00.arc').write_bytes(stage.data.getvalue())
    for file in dest.glob('*.arc'):
        report['files'][str(file.relative_to(P/'connected'))] = hashlib.sha256(file.read_bytes()).hexdigest()

metadata={'id':'local.silent_hill.connected','name':'Silent Hill Cafe and Street - Connected Test',
          'version':'0.3.1','author':'Personal crossover project',
          'description':'Supported door crossings and explicit exit triggers connect cafe R_SP108 and street R_SP109. Native Zelda door appearance. Experimental; playtest required.'}
(P/'connected/mod.json').write_text(json.dumps(metadata,indent=2)+'\n')
(P/'connected/connection_report.json').write_text(json.dumps(report,indent=2)+'\n')
(P/'ConnectedMods').mkdir(exist_ok=True)
with zipfile.ZipFile(P/'ConnectedMods/SilentHillConnected.dusk','w',zipfile.ZIP_DEFLATED) as z:
    z.write(P/'connected/mod.json','mod.json')
    for file in sorted(out.rglob('*.arc')):z.write(file,file.relative_to(P/'connected'))
print('Built connected 0.3.1: cafe <-> street; arrival and interaction ground/headroom checks passed')
