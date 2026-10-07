"""Package the converted cafe as a Dusklight asset-only test mod.
Keep DZX body offsets fixed so nested RTBL references stay correct.
"""
from pathlib import Path
from io import BytesIO
import sys, struct, json, zipfile, hashlib
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'gclib'))
from gclib.rarc import RARC
P = ROOT/'sh_tp_project'
SOURCE = ROOT/'tp_work/extracted/files/res/Stage/R_SP108'
OUT = P/'overlay/res/Stage/R_SP108'
OUT.mkdir(parents=True, exist_ok=True)

def sanitize(data, kind):
    data = bytearray(data)
    n = struct.unpack_from('>I', data)[0]
    entries = [struct.unpack_from('>4sII', data, 4+i*12) for i in range(n)]
    allowed = {'STAG', 'RTBL', 'MULT', 'FILI', 'LBNK'}
    if kind == 'stage': allowed |= {'RCAM', 'RARO'}
    if kind == 'room': allowed.add('PLYR')
    kept = []
    for tag, num, off in entries:
        name = tag.decode('ascii')
        if name not in allowed and name[:3] not in ('VRB', 'Env', 'Col', 'PAL'): continue
        if name == 'PLYR':
            for i in range(num):
                struct.pack_into('>I3f3hH', data, off+i*32+8,
                                 0xff000000, 200., 5., 200., 0, -16384, -256+i, 65535)
        if name == 'RCAM': data[off:off+8] = b'Room\0\0\0\0'
        if name == 'RARO': struct.pack_into('>3f', data, off, 200., 160., 420.)
        if name == 'FILI' and kind == 'room': data[off+0x1a] = 0xff
        kept.append((tag, num, off))
    struct.pack_into('>I', data, 0, len(kept))
    for i, entry in enumerate(kept): struct.pack_into('>4sII', data, 4+i*12, *entry)
    return bytes(data)

stage = RARC(str(SOURCE/'STG_00.arc'))
for name, kind in [('stage.dzs','stage'), ('room0.dzs','summary')]:
    e = stage.get_file_entry(name)
    e.data = BytesIO(sanitize(e.data.getvalue(), kind))
stage.save_changes()
(OUT/'STG_00.arc').write_bytes(stage.data.getvalue())
room = RARC(str(SOURCE/'R00_00.arc'))
room.get_file_entry('model.bmd').data = BytesIO((P/'assets/cafe.bmd').read_bytes())
e = room.get_file_entry('room.dzr')
e.data = BytesIO(sanitize(e.data.getvalue(), 'room'))
parent = room.get_file_entry('room.kcl').parent_node
# Resource loading dispatches on the directory's FourCC, not the filename.
# Reusing KCL here sends DZB bytes through initKCollision and corrupts the header.
parent.type = 'DZB '
for e in list(room.file_entries):
    if not e.is_dir and e.name not in ('model.bmd','room.dzr'): room.delete_file(e)
room.add_new_file('room.dzb', BytesIO((P/'assets/cafe.dzb').read_bytes()), parent)
room.save_changes()
(OUT/'R00_00.arc').write_bytes(room.data.getvalue())
metadata = {'id':'local.silent_hill.cafe', 'name':'Silent Hill Cafe - Experimental Room',
            'version':'0.1.1', 'author':'Personal crossover project',
            'description':'Silent Hill cafe in Twilight Princess. Test stage R_SP108 room 0. Experimental room conversion; not a completed game.'}
(P/'mod.json').write_text(json.dumps(metadata, indent=2)+'\n')
(P/'mods').mkdir(exist_ok=True)
with zipfile.ZipFile(P/'mods/SilentHillCafe.dusk','w',zipfile.ZIP_DEFLATED) as z:
    z.write(P/'mod.json','mod.json')
    for path in sorted((P/'overlay').rglob('*')):
        if path.is_file(): z.write(path,path.relative_to(P))
report = {'target':'R_SP108,0,0,0','files':{}}
for path in OUT.glob('*.arc'):
    check = RARC(str(path))
    report['files'][path.name] = {'bytes':path.stat().st_size,
        'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'entries':[e.name for e in check.file_entries if not e.is_dir]}
assert RARC(str(OUT/'R00_00.arc')).get_file_entry('room.dzb').parent_node.type == 'DZB '
assert set(report['files']['R00_00.arc']['entries']) == {'model.bmd','room.dzb','room.dzr'}
(P/'reports/package.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
