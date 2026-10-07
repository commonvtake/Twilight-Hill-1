"""Package Old Silent Hill (0.7.0): stage D_SB01 with one room per 3 x 3 tile block, plus the cafe.

Base: TownMods/SilentHillTown.dusk (0.5.0) - cafe R_SP108 and the fog STG of R_SP109, both
user-confirmed (door round trip, fog). Changes:
  * D_SB01/STG_00.arc = the R_SP109 fog STG with stage.dzs rebuilt for N rooms:
      RTBL  one entry per room listing only itself (0x80 bg-load flag | room, 0x40 as in source)
      Env0/Enve  the single environment record repeated per room (indexed by room number)
      SCLS  stage-level exit 0 = cafe (fallback while Link has no room during the door demo)
  * D_SB01/Rnn_00.arc = template room archive with model.bmd / room.dzb / room.dzr from build_town.py
  * Cafe exits (room and stage SCLS) retargeted from R_SP109 room 0 to D_SB01 room 0, same spawn.
"""
from pathlib import Path
from io import BytesIO
import sys, struct, json, zipfile, hashlib, shutil

ROOT = Path(__file__).resolve().parents[2]; P = ROOT / 'sh_tp_project'
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'gclib')); sys.path.insert(0, str(TOOLS))
from gclib.rarc import RARC
from build_town import chunk_blobs, write_dz, STAGE

VERSION = '0.7.0'
report = json.loads((P / 'town/town_report.json').read_text())
rooms = [r for r in report['rooms'] if 'skipped' not in r]
N = max(r['room'] for r in rooms) + 1

with zipfile.ZipFile(P / 'TownMods/SilentHillTown.dusk') as z:
    base = {n: z.read(n) for n in z.namelist()}


def retarget_scls(dz):
    """Point every SCLS record that names R_SP109 at D_SB01 (same room 0 / spawn)."""
    b = bytearray(dz); n = struct.unpack_from('>I', b, 0)[0]; changed = 0
    for i in range(n):
        tag, cnt, off = struct.unpack_from('>4sII', b, 4 + i * 12)
        if tag == b'SCLS':
            for k in range(cnt):
                o = off + 13 * k
                if b[o:o + 8] == b'R_SP109\0':
                    b[o:o + 8] = STAGE.encode().ljust(8, b'\0'); changed += 1
    return bytes(b), changed


files = {}
# cafe
cafe_changes = 0
for arcname, inner in (('R00_00.arc', 'room.dzr'), ('STG_00.arc', 'stage.dzs')):
    key = f'overlay/res/Stage/R_SP108/{arcname}'
    arc = RARC(BytesIO(base[key])); arc.read()
    e = arc.get_file_entry(inner); data, n = retarget_scls(e.data.getvalue()); cafe_changes += n
    e.data = BytesIO(data); arc.save_changes(); files[key] = arc.data.getvalue()
assert cafe_changes == 2, cafe_changes

# stage
stg = RARC(BytesIO(base['overlay/res/Stage/R_SP109/STG_00.arc'])); stg.read()
dzs = stg.get_file_entry('stage.dzs').data.getvalue()
ch = chunk_blobs(dzs)
n0 = struct.unpack_from('>I', dzs, 0)[0]
order = [struct.unpack_from('>4sII', dzs, 4 + i * 12)[0] for i in range(n0)]
env_rec = {t: ch[t][1][:0x41] for t in (b'Env0', b'Enve')}
cafe_exit = ch[b'SCLS'][1][:13]
assert cafe_exit[:8] == b'R_SP108\0'


def rtbl_blob(base_off):
    ptrs = bytearray(); entries = bytearray(); lists = bytearray()
    ent_off = base_off + 4 * N; list_off = ent_off + 8 * N
    for r in range(N):
        ptrs += struct.pack('>I', ent_off + 8 * r)
        entries += struct.pack('>BBBxI', 1, 0, 0, list_off + r)
        lists.append(0xC0 | r)
    return bytes(ptrs + entries + lists)


def build_stage(rtbl_off):
    out = []
    for t in order:
        cnt, blob = ch[t]
        if t == b'RTBL':
            out.append((t, N, rtbl_blob(rtbl_off)))
        elif t in env_rec:
            out.append((t, N, env_rec[t] * N))
        elif t == b'SCLS':
            out.append((t, 1, cafe_exit))
        else:
            out.append((t, cnt, blob))
    return out


tmp = write_dz(build_stage(0))
rt = [struct.unpack_from('>4sII', tmp, 4 + i * 12) for i in range(n0)]
rtbl_off = [o for t, c, o in rt if t == b'RTBL'][0]
stage_dzs = write_dz(build_stage(rtbl_off))
assert write_dz(build_stage(rtbl_off)) == stage_dzs
stg.get_file_entry('stage.dzs').data = BytesIO(stage_dzs); stg.save_changes()
files[f'overlay/res/Stage/{STAGE}/STG_00.arc'] = stg.data.getvalue()

# rooms
sizes = {}
for r in rooms:
    d = P / 'town/chunks' / f"{r['room']:02d}"
    arc = RARC(BytesIO(base['overlay/res/Stage/R_SP109/R00_00.arc'])); arc.read()
    for name, src in (('model.bmd', 'model.bmd'), ('room.dzb', 'room.dzb'), ('room.dzr', 'room.dzr')):
        arc.get_file_entry(name).data = BytesIO((d / src).read_bytes())
    arc.save_changes()
    key = f"overlay/res/Stage/{STAGE}/R{r['room']:02d}_00.arc"
    files[key] = arc.data.getvalue(); sizes[r['room']] = len(files[key])

files['mod.json'] = (json.dumps({
    'id': 'local.silent_hill.oldtown', 'name': 'Silent Hill - Old Silent Hill Town',
    'version': VERSION, 'author': 'Personal crossover project',
    'description': f'Old Silent Hill: {sum(len(r["tiles"]) for r in rooms)} original town tiles in {len(rooms)} connected '
                   'areas (walk across street edges), native fog, Cafe 5to2, Stalhounds and Guays for Groaners '
                   'and Air Screamers. Pair with Silent Hill Core. No story progression yet. Windows playtest required.'},
    indent=2) + '\n').encode()
out = P / 'OldTownMods'; out.mkdir(exist_ok=True)
with zipfile.ZipFile(out / 'SilentHillOldTown.dusk', 'w', zipfile.ZIP_DEFLATED) as z:
    for n, b in files.items():
        z.writestr(n, b)
core = ROOT / 'build_inputs/silent_hill_core.dusk'
if core.exists():
    shutil.copy2(core, out / 'silent_hill_core.dusk')
pkg = {'version': VERSION, 'stage': STAGE, 'rooms': len(rooms), 'room_slots_used': N,
       'largest_room_archive_bytes': max(sizes.values()), 'room_archive_bytes': sizes,
       'cafe_exits_retargeted': cafe_changes, 'dusk_bytes': (out / 'SilentHillOldTown.dusk').stat().st_size,
       'silent_hill_core_included': core.exists(), 'runtime_tested': False,
       'files': {n: hashlib.sha256(b).hexdigest() for n, b in files.items()}}
(P / 'town/package_report.json').write_text(json.dumps(pkg, indent=1) + '\n')
print(json.dumps({k: v for k, v in pkg.items() if k != 'files'}, indent=1))
