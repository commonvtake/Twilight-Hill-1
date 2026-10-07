"""Package district 0.6.0: replace the street room of the 0.5.0 town mod with the 3 x 3 district.

Everything else (cafe stage R_SP108, stage palettes and fog, room.dzr spawns/doors/exits, door
actor, scene-change triggers) is carried over byte-identical from TownMods 0.5.0. The district
model receives the same native fog settings as 0.4.0+, and the cafe door gets the same supported
crossing collision as 0.3.1+ (door_threshold.supported_collision).
"""
from pathlib import Path
from io import BytesIO
import sys, struct, json, zipfile, hashlib, shutil

ROOT = Path(__file__).resolve().parents[2]; P = ROOT / 'sh_tp_project'
sys.path.insert(0, str(ROOT / 'gclib')); sys.path.insert(0, str(Path(__file__).resolve().parent))
from gclib.rarc import RARC
from gclib.j3d import BMD
from gclib.gx_enums import FogType
from door_threshold import supported_collision
from district_coverage import analyse
import place_enemies
import numpy as np

CFG = json.loads((P / 'district/config.json').read_text())
settings = json.loads((P / 'fog/settings.json').read_text())
A = P / 'district/assets'

raw = (A / 'district.bmd').read_bytes(); model = BMD(BytesIO(raw))
for m in model.mat3.materials:
    f = m.fog_info; f.fog_type = FogType.LINEAR; f.start_z = settings['start_cm']; f.end_z = settings['end_cm']
    f.color.r, f.color.g, f.color.b = settings['color_rgb']; f.color.a = 255
model.mat3.save(); chunks = []; off = 32
for _ in range(struct.unpack_from('>I', raw, 12)[0]):
    size = struct.unpack_from('>I', raw, off + 4)[0]; c = raw[off:off + size]
    chunks.append(model.mat3.data.getvalue() if c[:4] == b'MAT3' else c); off += size
header = bytearray(raw[:32]); struct.pack_into('>I', header, 8, 32 + sum(map(len, chunks)))
model_data = bytes(header) + b''.join(chunks)
assert all(mm.fog_info.fog_type == FogType.LINEAR for mm in BMD(BytesIO(model_data)).mat3.materials)

area = {'door': [-60., 14.84375, -350.], 'facing': 16384}
collision, added = supported_collision((A / 'district.dzb').read_bytes(), area)
(A / 'district_supported.dzb').write_bytes(collision)

with zipfile.ZipFile(P / 'TownMods/SilentHillTown.dusk') as z:
    files = {n: z.read(n) for n in z.namelist()}
key = 'overlay/res/Stage/R_SP109/R00_00.arc'
room = RARC(BytesIO(files[key]))
room.get_file_entry('model.bmd').data = BytesIO(model_data)
room.get_file_entry('room.dzb').data = BytesIO(collision)
# Enemies (0.7.0): SH Groaners -> Stalhounds, Air Screamers -> Guays, on reachable streets.
src = np.load(A / 'district_collision_source.npz')
cov = analyse(src['vertices'], src['faces'], tuple(CFG['spawn_xz_cm']))
en = CFG['enemies']; away = [tuple(p) for p in en['keep_away_xz_cm']]
records = []; placements = []
spots = place_enemies.choose_positions(cov, away, en['groaner'] + en['air_screamer'])
assert len(spots) == en['groaner'] + en['air_screamer'], len(spots)
for k, (x, z, y) in enumerate(spots):
    kind = 'groaner' if k < en['groaner'] else 'air_screamer'
    yaw = int(np.degrees(np.arctan2(CFG['spawn_xz_cm'][0] - x, CFG['spawn_xz_cm'][1] - z)) / 360 * 65536)
    records.append(place_enemies.actor_record(kind, x, y, z, yaw))
    placements.append({'kind': kind, 'xyz_cm': [round(x, 1), round(y, 1), round(z, 1)]})
dzr = room.get_file_entry('room.dzr').data.getvalue()
room.get_file_entry('room.dzr').data = BytesIO(place_enemies.add_actors(dzr, records))
(P / 'district/enemies.json').write_text(json.dumps(placements, indent=2) + '\n')
room.save_changes(); files[key] = room.data.getvalue()
files['mod.json'] = (json.dumps({
    'id': 'local.silent_hill.district', 'name': 'Silent Hill - Central District Test',
    'version': CFG['version'], 'author': 'Personal crossover project',
    'description': 'Nine original Old Silent Hill tiles (3 x 3 blocks), native fog, cafe and doors, '
                   'Stalhounds and Guays standing in for Groaners and Air Screamers. '
                   'Pair with Silent Hill Core for jump, combat gear and pause-screen settings. '
                   'No campaign progression. Windows playtest required.'}, indent=2) + '\n').encode()
out_dir = P / 'DistrictMods'; out_dir.mkdir(exist_ok=True)
with zipfile.ZipFile(out_dir / 'SilentHillDistrict.dusk', 'w', zipfile.ZIP_DEFLATED) as z:
    for n, b in files.items():
        z.writestr(n, b)
core = ROOT / 'build_inputs/silent_hill_core.dusk'
if core.exists():
    shutil.copy2(core, out_dir / 'silent_hill_core.dusk')
report = {'version': CFG['version'], 'tiles': CFG['tiles'], 'enemies': placements, 'room_archive_bytes': len(files[key]),
          'model_bytes': len(model_data), 'collision_bytes': len(collision), 'door_support_faces': len(added),
          'silent_hill_core_included': core.exists(), 'runtime_tested': False, 'full_campaign': False,
          'files': {n: hashlib.sha256(b).hexdigest() for n, b in files.items()}}
(P / 'district/package_report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k != 'files'}, indent=1))
