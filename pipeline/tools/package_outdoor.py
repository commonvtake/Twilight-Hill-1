"""Build a separate outdoor test mod from the user-verified cafe room template."""
from pathlib import Path
from io import BytesIO
import sys, struct, json, zipfile, hashlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'gclib'))
from gclib.rarc import RARC
P = ROOT/'sh_tp_project'
OUT = P/'outdoor/overlay/res/Stage/R_SP108'
OUT.mkdir(parents=True, exist_ok=True)
spawn = json.loads((P/'outdoor/assets/collision_report.json').read_text())['spawn_cm']

def position(data, kind):
    data = bytearray(data)
    for i in range(struct.unpack_from('>I', data)[0]):
        tag, count, offset = struct.unpack_from('>4sII', data, 4+i*12)
        if tag == b'PLYR' and kind == 'room':
            for j in range(count):
                struct.pack_into('>3f', data, offset+j*32+12, *spawn)
                struct.pack_into('>h', data, offset+j*32+26, 0)
        if tag == b'RARO' and kind == 'stage':
            struct.pack_into('>3f', data, offset, spawn[0], spawn[1]+160, spawn[2]-420)
    return BytesIO(data)

room = RARC(str(P/'overlay/res/Stage/R_SP108/R00_00.arc'))
room.get_file_entry('model.bmd').data = BytesIO((P/'outdoor/assets/outdoor.bmd').read_bytes())
entry = room.get_file_entry('room.dzb')
assert entry.parent_node.type == 'DZB ', 'Must use native DZB resource loader'
entry.data = BytesIO((P/'outdoor/assets/outdoor.dzb').read_bytes())
entry = room.get_file_entry('room.dzr')
entry.data = position(entry.data.getvalue(), 'room')
room.save_changes()
(OUT/'R00_00.arc').write_bytes(room.data.getvalue())
stage = RARC(str(P/'overlay/res/Stage/R_SP108/STG_00.arc'))
entry = stage.get_file_entry('stage.dzs')
entry.data = position(entry.data.getvalue(), 'stage')
stage.save_changes()
(OUT/'STG_00.arc').write_bytes(stage.data.getvalue())
metadata = {'id':'local.silent_hill.outdoor', 'name':'Silent Hill Street - Outdoor Test',
            'version':'0.2.0', 'author':'Personal crossover project',
            'description':'One Old Silent Hill street tile in Twilight Princess. Separate test stage R_SP108 room 0. Gameplay validation pending.'}
(P/'outdoor/mod.json').write_text(json.dumps(metadata,indent=2)+'\n')
(P/'OutdoorMods').mkdir(exist_ok=True)
with zipfile.ZipFile(P/'OutdoorMods/SilentHillOutdoor.dusk','w',zipfile.ZIP_DEFLATED) as z:
    z.write(P/'outdoor/mod.json','mod.json')
    for file in sorted(OUT.glob('*.arc')):
        z.write(file,'overlay/res/Stage/R_SP108/'+file.name)
report = {'version':'0.2.0', 'stage':'R_SP108,0,0,0', 'spawn_cm':spawn,
          'runtime_test':'pending user playtest', 'files':{}}
for file in sorted(OUT.glob('*.arc')):
    arc = RARC(str(file))
    report['files'][file.name] = {'bytes':file.stat().st_size,
        'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),
        'entries':[e.name for e in arc.file_entries if not e.is_dir]}
(P/'outdoor/package_report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
