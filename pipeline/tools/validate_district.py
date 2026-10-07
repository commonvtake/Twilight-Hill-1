"""Static validation for the district room (0.6.0+). Writes district/coverage.png.

Checks
  1. Model parses; every texture is C8/RGB5A3 and decodes identically to the RGB5A3 encoding the
     0.5.0 pipeline used (the paletted format must be lossless relative to the shipped look).
  2. Collision parses (DZB FourCC retained), indices are in bounds, room index matches.
  3. Both existing R_SP109 spawn points and the cafe door still stand on floor with headroom.
  4. Ground coverage: walkable floor is rasterised on a 25 cm grid; a flood fill from spawn 0
     (step height <= 45 cm) marks reachable ground. Reachable cells next to ground-less cells are
     reported as potential drop-offs unless a wall triangle separates them.
"""
from pathlib import Path
from io import BytesIO
import sys, json, struct, copy
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]; P = ROOT / 'sh_tp_project'
sys.path.insert(0, str(ROOT / 'gclib')); sys.path.insert(0, str(ROOT / 'dzb_tools/dzb_tools'))
from gclib.j3d import BMD
from gclib.texture_utils import ImageFormat, decode_image, encode_image
from gclib.gx_enums import PaletteFormat
from dzb import DZB

CFG = json.loads((P / 'district/config.json').read_text())
A = P / 'district/assets'
SPAWNS = [(500.0, 0.0), (160.0, -350.0)]
DOOR = (-60.0, -350.0)
report = {'version': CFG['version']}

# 1. model + textures
model = BMD(BytesIO((A / 'district.bmd').read_bytes()))
src = P / 'district/source'
names = {}
for line in (src / 'DISTRICT.MTL').read_text().splitlines():
    s = line.split()
    if s and s[0] == 'newmtl': cur = s[1]
    elif s and s[0] == 'map_Kd': names[cur] = s[1]
build = json.loads((A / 'build_report.json').read_text())
sources = build['model']['texture_sources']
assert len(sources) == len(model.tex1.textures)
max_diff = 0
for tex, name in zip(model.tex1.textures, sources):
    assert tex.image_format == ImageFormat.C8 and tex.palette_format == PaletteFormat.RGB5A3
    got = np.asarray(tex.render().convert('RGBA'), dtype=int)
    if name is None:
        continue
    # Reference: the same image through the RGB5A3 encoding used by 0.5.0.
    from gclib.bti import BTI
    ref_t = copy.deepcopy(tex); ref_t.image_format = ImageFormat.RGB5A3
    ref_t.replace_image(Image.open(src / name).convert('RGBA'))
    ref = np.asarray(ref_t.render().convert('RGBA'), dtype=int)
    # Fully transparent texels are discarded by the alpha test (ref0 = 128); compare the rest.
    assert ((got[..., 3] >= 128) == (ref[..., 3] >= 128)).all(), f'cut-out mask differs in {name}'
    vis = ref[..., 3] >= 128
    max_diff = max(max_diff, int(np.abs(got - ref)[vis].max()) if vis.any() else 0)
assert max_diff == 0, f'visible texels differ from RGB5A3 by {max_diff}'
report['textures'] = {'count': len(model.tex1.textures), 'format': 'C8/RGB5A3', 'max_visible_difference_vs_rgb5a3': max_diff, 'cutout_mask': 'identical'}

# 2. collision
raw = (A / 'district_supported.dzb').read_bytes() if (A / 'district_supported.dzb').exists() else (A / 'district.dzb').read_bytes()
dzb = DZB(); dzb.read(BytesIO(raw))
assert all(g.room_index == CFG['room'] for g in dzb.groups)
src_npz = np.load(A / 'district_collision_source.npz'); V = src_npz['vertices']; F = src_npz['faces']
assert F.max() < len(V)
report['collision'] = {'faces': len(dzb.faces), 'groups': len(dzb.groups), 'bytes': len(raw)}

# 3/4. floors and reachability (shared analysis), on the final collision source
sys.path.insert(0, str(Path(__file__).resolve().parent))
from district_coverage import analyse, STEP
cov = analyse(V, F, SPAWNS[0]); H = cov['H']; reach = cov['reach']; cell = cov['cell']
for (x, z) in SPAWNS + [DOOR]:
    assert not np.isnan(H[cell(x, z)]), f'no floor at {x},{z}'
report['spawn_floor_cm'] = [float(H[cell(x, z)]) for x, z in SPAWNS]
for (x, z) in SPAWNS:
    assert reach[cell(x, z)], f'spawn {x},{z} not connected to the street network'
wall_grid = cov['wall_grid']
open_edge = np.zeros(H.shape, bool)
for r, c, dr, dc in cov['drops']:
    open_edge[r, c] = True
assert not cov['drops'], f"{len(cov['drops'])} open drop edges remain"
report['coverage'] = {
    'grid_cm': STEP, 'cells': int(H.size), 'floor_cells': int((~np.isnan(H)).sum()),
    'reachable_cells': int(reach.sum()), 'reachable_m2': float(reach.sum() * STEP * STEP / 1e4),
    'open_drop_edges': len(cov['drops'])}

# Coverage image: grey = floor, green = reachable, red = open drop edge, black = no floor.
img = np.zeros(H.shape + (3,), np.uint8)
img[~np.isnan(H)] = (90, 90, 90); img[reach] = (70, 150, 80); img[wall_grid] = (30, 30, 30)
img[open_edge] = (230, 40, 40)
for x, z in SPAWNS: r, c = cell(x, z); img[max(0, r - 3):r + 4, max(0, c - 3):c + 4] = (250, 220, 60)
Image.fromarray(img[::-1]).resize((H.shape[1] * 2, H.shape[0] * 2), Image.NEAREST).save(P / 'district/coverage.png')
# 5. enemies (0.7.0+): room.dzr ACTR records in the packaged mod
import zipfile, place_enemies
from gclib.rarc import RARC
with zipfile.ZipFile(P / 'DistrictMods/SilentHillDistrict.dusk') as zf, zipfile.ZipFile(P / 'TownMods/SilentHillTown.dusk') as zt:
    new_room = RARC(BytesIO(zf.read('overlay/res/Stage/R_SP109/R00_00.arc'))); new_room.read()
    old_room = RARC(BytesIO(zt.read('overlay/res/Stage/R_SP109/R00_00.arc'))); old_room.read()
new_dzr = new_room.get_file_entry('room.dzr').data.getvalue(); old_dzr = old_room.get_file_entry('room.dzr').data.getvalue()
def chunk_data(d, size_of):
    n = struct.unpack_from('>I', d, 0)[0]; out = {}
    for i in range(n):
        tag, cnt, off = struct.unpack_from('>4sII', d, 4 + i * 12)
        if tag in size_of: out[tag] = d[off:off + cnt * size_of[tag]]
    return out
sizes = {b'PLYR': 0x20, b'SCLS': 13, b'TGSC': 0x24, b'FILI': 8}
o, nw = chunk_data(old_dzr, sizes), chunk_data(new_dzr, sizes)
for tag in sizes:
    assert o.get(tag) == nw.get(tag), f'{tag} changed'
old_actors = place_enemies.read_actors(old_dzr); new_actors = place_enemies.read_actors(new_dzr)
assert new_actors[:len(old_actors)] == old_actors, 'original actors (door) changed'
enemies = new_actors[len(old_actors):]
names = [a[0].rstrip(b'\0').decode() for a in enemies]
expected = CFG['enemies']['groaner'] * ['E_sh'] + CFG['enemies']['air_screamer'] * ['E_ge']
assert names == expected, names
for a in enemies:
    x, y, z = a[2], a[3], a[4]
    r, c = cell(x, z)
    assert reach[r, c], f'enemy at {x},{z} not on reachable floor'
    lift = place_enemies.ENEMY_TYPES['groaner' if a[0].startswith(b'E_sh') else 'air_screamer']['lift_cm']
    assert abs((y - lift - 5) - H[r, c]) < 1, f'enemy height mismatch at {x},{z}'
    for sx, sz in SPAWNS + [DOOR]:
        assert np.hypot(x - sx, z - sz) >= 1500, 'enemy too close to spawn/door'
report['enemies'] = {'stalhounds': names.count('E_sh'), 'guays': names.count('E_ge'),
                     'door_actor_preserved': True, 'other_room_records_identical': True}
for a in enemies:
    r, c = cell(a[2], a[4]); img[max(0, r - 4):r + 5, max(0, c - 4):c + 5] = (200, 40, 200) if a[0].startswith(b'E_sh') else (60, 120, 230)
Image.fromarray(img[::-1]).resize((H.shape[1] * 2, H.shape[0] * 2), Image.NEAREST).save(P / 'district/coverage.png')
(P / 'district/validation_report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=1))
