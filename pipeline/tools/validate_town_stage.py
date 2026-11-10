"""Static validation of the packaged Old Silent Hill stage (0.8.0). Writes town/town_map.png and town/town_map_layers.npz.

Per room: model parses (C8/RGB5A3 textures), DZB parses with the right room index, room archive
fits the memory budget, spawn ids unique, every spawn on reachable floor; every scnChg trigger
references an existing exit, every exit an existing room + spawn, arrivals are outside every
trigger of the destination room (no ping-pong), trigger boxes overlap reachable floor.
Stage: RTBL/Env0/Enve have one entry per room and decode as the engine reads them; cafe exits
point at D_SB01 room 0 spawn 1; the town graph is connected from room 0.
"""
from pathlib import Path
from io import BytesIO
import sys, json, struct, zipfile, math
from collections import deque
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]; P = ROOT / 'sh_tp_project'
sys.path.insert(0, str(ROOT / 'gclib')); sys.path.insert(0, str(ROOT / 'dzb_tools/dzb_tools')); sys.path.insert(0, str(Path(__file__).resolve().parent))
from gclib.rarc import RARC
from gclib.j3d import BMD
from gclib.texture_utils import ImageFormat
from dzb import DZB
from district_coverage import analyse, STEP
from build_town import STAGE, HALF

BUDGET = 3_300_000
z = zipfile.ZipFile(P / 'OldTownMods/SilentHillOldTown.dusk')
names = z.namelist()
rep = {'rooms': {}, 'errors': []}


def table(d):
    n = struct.unpack_from('>I', d, 0)[0]
    return {struct.unpack_from('>4sII', d, 4 + i * 12)[0]: struct.unpack_from('>4sII', d, 4 + i * 12)[1:] for i in range(n)}


def rows(d, tag, size):
    t = table(d)
    if tag not in t: return []
    cnt, off = t[tag]
    return [d[off + k * size: off + (k + 1) * size] for k in range(cnt)]


room_keys = sorted(n for n in names if n.startswith(f'overlay/res/Stage/{STAGE}/R'))
rooms = {}
for key in room_keys:
    r = int(key.split('/R')[1][:2])
    data = z.read(key)
    assert len(data) < BUDGET, f'room {r} archive {len(data)} exceeds budget'
    arc = RARC(BytesIO(data)); arc.read()
    files = {f.name: f.data.getvalue() for f in arc.file_entries if not f.is_dir}
    model = BMD(BytesIO(files['model.bmd']))
    assert all(t.image_format == ImageFormat.C8 for t in model.tex1.textures)
    dzb = DZB(); dzb.read(BytesIO(files['room.dzb']))
    assert all(g.room_index == r for g in dzb.groups), f'room {r} collision room index'
    dzr = files['room.dzr']
    plyr = [struct.unpack('>8sI3f3hH', x) for x in rows(dzr, b'PLYR', 0x20)]
    scls = [struct.unpack('>8s5B', x) for x in rows(dzr, b'SCLS', 13)]
    tgsc = [struct.unpack('>8sI3f3hH4B', x) for x in rows(dzr, b'TGSC', 0x24)]
    actr = [struct.unpack('>8sI3f3hH', x) for x in rows(dzr, b'ACTR', 0x20)]
    ids = [p[7] & 0xFF for p in plyr]
    assert len(ids) == len(set(ids)), f'room {r} duplicate spawn ids'
    src = np.load(P / f'town/chunks/{r:02d}/collision_source.npz')
    rooms[r] = dict(bytes=len(data), plyr=plyr, scls=scls, tgsc=tgsc, actr=actr, V=src['vertices'], F=src['faces'])


def box_contains(t, x, y, z_):
    px, py, pz = t[2], t[3], t[4]; yaw = t[6] * math.pi / 32768
    dx, dz = x - px, z_ - pz
    # inverse of YrotM(yaw): local x = c*dx - s*dz, local z = s*dx + c*dz
    c, s = math.cos(yaw), math.sin(yaw)
    lx = c * dx - s * dz; lz = s * dx + c * dz
    return abs(lx) <= t[9] / 10 * 75 and abs(lz) <= t[11] / 10 * 75 and 0 <= y - py <= t[10] / 10 * 150


town = json.loads((P / 'town/town_report.json').read_text())
grid_of = {x['room']: tuple(x['grid_cm']) for x in town['rooms'] if 'skipped' not in x}
global_exits = rooms[0]['scls']
graph = {r: set() for r in rooms}
covs = {}
door_count = 0


def resolve_exit(r, ex):
    assert ex < len(global_exits), f'room {r}: exit {ex} outside the exit table'
    dest = global_exits[ex]; stage = dest[0].rstrip(b'\0').decode(); spawn, droom = dest[1], dest[2]
    if stage != STAGE:
        assert stage == 'R_SP108' and ex == 0, f'room {r}: unexpected exit stage {stage}'
        return None
    assert droom in rooms, f'room {r}: exit to missing room {droom}'
    target = [p for p in rooms[droom]['plyr'] if (p[7] & 0xFF) == spawn]
    assert target, f'room {r}: exit to room {droom} missing spawn {spawn}'
    for t2 in rooms[droom]['tgsc']:
        assert not box_contains(t2, target[0][2], target[0][3], target[0][4]), f'room {droom}: arrival {spawn} inside a trigger'
    return droom


door_exits_of = {}
for r, R in rooms.items():
    assert R['scls'] == global_exits, f'room {r}: exit table differs from the shared table'
    seeds = [(p[2], p[4]) for p in R['plyr']]
    cov = analyse(R['V'], R['F'], seeds, bounds=grid_of[r]); covs[r] = cov
    door_exits = set(); door_exits_of[r] = door_exits
    for a in R['actr']:
        if a[0].rstrip(b'\0') == b'kdoor':
            ex = (a[1] >> 25) & 0x3F; door_exits.add(ex); door_count += 1
            assert ex <= 62, f'room {r}: door exit {ex} does not fit the 6-bit kdoor field'
            droom = resolve_exit(r, ex)
            # Link stands on the street/room side (door local +Z) to open it
            yaw = a[6] * math.pi / 32768
            fx, fz = a[2] + math.sin(yaw) * 100, a[4] + math.cos(yaw) * 100
            rc = cov['cell'](fx, fz)
            assert cov['reach'][rc], f'room {r}: no reachable floor in front of door exit {ex}'
            if droom is not None:
                graph[r].add(droom)
    H, reach, cell = cov['H'], cov['reach'], cov['cell']
    assert not cov['drops'], f'room {r}: {len(cov["drops"])} open drops'
    for p in R['plyr']:
        rc = cell(p[2], p[4])
        assert reach[rc] and abs(H[rc] + 5 - p[3]) < 2, f'room {r}: spawn {p[7] & 0xFF} not on floor'
    for t in R['tgsc']:
        if t[0].rstrip(b'\0') != b'scnChg': continue
        ex = t[1] & 0xFF
        droom = resolve_exit(r, ex)
        if ex in door_exits or droom is None:
            continue   # door fallback trigger sits behind its door, inside the wall
        assert ex <= 255, f'room {r}: street portal exit {ex} does not fit scnChg arg0'
        # trigger overlaps reachable floor (sample its footprint)
        yaw = t[6] * math.pi / 32768; c, s = math.cos(yaw), math.sin(yaw)
        hw, hd = t[9] / 10 * 75, t[11] / 10 * 75; hit = False
        for lx in np.linspace(-hw, hw, 9):
            for lz in np.linspace(-hd, hd, 5):
                x = t[2] + c * lx + s * lz; zz = t[4] - s * lx + c * lz
                rc = cell(x, zz)
                if 0 <= rc[0] < H.shape[0] and 0 <= rc[1] < H.shape[1] and reach[rc]:
                    hit = True
        assert hit, f'room {r}: trigger {ex} not reachable'
        graph[r].add(droom)
    rep['rooms'][r] = {'archive_bytes': R['bytes'], 'spawns': len(R['plyr']), 'exits': len(R['scls']),
                       'triggers': len(R['tgsc']), 'enemies': sum(1 for a in R['actr'] if a[0].startswith(b'E_')),
                       'reachable_m2': float(reach.sum() * STEP * STEP / 1e4)}

# connectivity
seen = {0}; q = deque([0])
while q:
    u = q.popleft()
    for v in graph[u]:
        if v not in seen: seen.add(v); q.append(v)
rep['unreachable_rooms'] = sorted(set(rooms) - seen)
assert not rep['unreachable_rooms'], f"unreachable rooms {rep['unreachable_rooms']}"
rep['doors'] = door_count
for u in graph:
    for v in graph[u]:
        assert u in graph[v], f'one-way connection {u}->{v}'

# stage tables
stg = RARC(BytesIO(z.read(f'overlay/res/Stage/{STAGE}/STG_00.arc'))); stg.read()
dzs = stg.get_file_entry('stage.dzs').data.getvalue(); t = table(dzs)
N = max(rooms) + 1
cnt, off = t[b'RTBL']; assert cnt == N
for r in range(N):
    eo = struct.unpack_from('>I', dzs, off + 4 * r)[0]
    num, f1, f2, lp = struct.unpack_from('>BBBxI', dzs, eo)
    assert num == 1 and dzs[lp] & 0x3F == r and dzs[lp] & 0x80, f'RTBL entry {r}'
for tag in (b'Env0', b'Enve'):
    assert t[tag][0] == N, f'{tag} count'
sc = [struct.unpack('>8s5B', x) for x in rows(dzs, b'SCLS', 13)]
assert sc == global_exits, 'stage exit table differs from the rooms'
stag = rows(dzs, b'STAG', 0x3C)[0]
assert (struct.unpack_from('>I', stag, 0x0c)[0] >> 16) & 7 == 0, 'stage type is not ST_FIELD'
for arcname, inner in (('R00_00.arc', 'room.dzr'), ('STG_00.arc', 'stage.dzs')):
    a = RARC(BytesIO(z.read(f'overlay/res/Stage/R_SP108/{arcname}'))); a.read()
    d = a.get_file_entry(inner).data.getvalue()
    ex = [struct.unpack('>8s5B', x) for x in rows(d, b'SCLS', 13)]
    assert ex and all(e[0] == STAGE.encode().ljust(8, b'\0') and e[1] == 1 and e[2] == 0 for e in ex), f'cafe {inner} exits'

# overview map
town = json.loads((P / 'town/town_report.json').read_text())
chunk_of_room = {r['room']: tuple(r['chunk']) for r in town['rooms'] if 'skipped' not in r and r.get('kind', 'town') == 'town'}
cxs = [c[0] for c in chunk_of_room.values()]; cys = [c[1] for c in chunk_of_room.values()]
cell_px = int(2 * HALF / STEP)
W = (max(cxs) - min(cxs) + 1) * cell_px; Hh = (max(cys) - min(cys) + 1) * cell_px
# layer codes: 0 none, 1 floor (unreachable), 2 walkable, 3 wall, 4 load zone, 5 Stalhound, 6 Guay, 7 door
lay = np.zeros((Hh, W), np.uint8)
for r, c in chunk_of_room.items():
    cov = covs[r]; H, reach = cov['H'], cov['reach']
    tile = np.zeros(H.shape, np.uint8)
    tile[~np.isnan(H)] = 1; tile[reach] = 2; tile[cov['wall_grid']] = 3
    for t_ in rooms[r]['tgsc']:
        if t_[0].rstrip(b'\0') != b'scnChg' or (t_[1] & 0xFF) in door_exits_of.get(r, ()):
            continue
        rc = cov['cell'](t_[2], t_[4]); tile[max(0, rc[0] - 6):rc[0] + 7, max(0, rc[1] - 6):rc[1] + 7] = 4
    for a in rooms[r]['actr']:
        if a[0].startswith(b'E_') or a[0].rstrip(b'\0') == b'kdoor':
            code = 7 if a[0].startswith(b'kdoor') else (5 if a[0].startswith(b'E_sh') else 6)
            rad = 7 if code == 7 else 5
            rc = cov['cell'](a[2], a[4]); tile[max(0, rc[0] - rad):rc[0] + rad + 1, max(0, rc[1] - rad):rc[1] + rad + 1] = code
    tile = tile[:cell_px, :cell_px][::-1, ::-1]   # north up, SH x grid increases leftwards in exporter space
    gx = (max(cxs) - c[0]) * cell_px; gy = (max(cys) - c[1]) * cell_px
    lay[gy:gy + tile.shape[0], gx:gx + tile.shape[1]] = tile
np.savez_compressed(P / 'town/town_map_layers.npz', layers=lay, cell_px=cell_px, step_cm=STEP)
pal = np.array([(0, 0, 0), (80, 80, 80), (70, 150, 80), (30, 30, 30), (240, 200, 40), (200, 40, 200),
                (60, 120, 230), (255, 255, 255)], np.uint8)
img = pal[lay]
for gx in range(0, W, cell_px): img[:, gx] = 255
for gy in range(0, Hh, cell_px): img[gy, :] = 255
Image.fromarray(img).resize((W // 3, Hh // 3), Image.NEAREST).save(P / 'town/town_map.png')
rep['connected_rooms'] = len(seen); rep['links'] = sum(len(v) for v in graph.values())
rep['total_reachable_m2'] = sum(v['reachable_m2'] for v in rep['rooms'].values())
rep['largest_room_archive_bytes'] = max(v['archive_bytes'] for v in rep['rooms'].values())
(P / 'town/validation_report.json').write_text(json.dumps(rep, indent=1) + '\n')
print(json.dumps({k: v for k, v in rep.items() if k != 'rooms'}, indent=1))
print('PASS: all rooms, exits, arrivals, stage tables and cafe links')
