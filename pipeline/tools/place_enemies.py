"""Enemy placement for a district room (0.7.0+).

Silent Hill 1's Old Silent Hill street enemies are represented by native Twilight Princess
enemies that already have full AI, damage and death handling:
  Groaner (zombie dog)      -> Stalhound  "E_sh"  params 0x00081E00
                                (byte1 0x1E: leash 30 m from home, byte2 0x08: rises within 8 m)
  Air Screamer (fog flyer)  -> Guay       "E_ge"  params 0x0000FF01
                                (move type 1 = starts flying at its height and attacks; switch 0xFF = always respawns)
Positions are chosen on open, flat, reachable street floor (district_coverage.analyse), at least
4 m inside the perimeter, 15 m from spawns/doors and 12 m apart (seeded random, reproducible). Guays are placed 4.5 m above the floor.
Record layout follows stage_actor_data_class (include/d/d_stage.h): name[8], params u32,
pos f32[3], angle s16[3], set id u16 = 0x20 bytes.
"""
import struct
import numpy as np

ENEMY_TYPES = {
    'groaner': {'name': b'E_sh', 'params': 0x00081E00, 'lift_cm': 0.0},
    'air_screamer': {'name': b'E_ge', 'params': 0x0000FF01, 'lift_cm': 450.0},
}


def choose_positions(cov, keep_away_xz, count, min_spacing_cm=1200.0, keep_away_cm=1500.0, seed=7):
    H, reach, lo = cov['H'], cov['reach'], cov['lo']
    from district_coverage import STEP
    rows, cols = np.nonzero(reach)
    pts = np.stack([lo[0] + cols * STEP, lo[2] + rows * STEP, H[rows, cols]], 1)
    # Prefer open street cells: all 8 neighbours within 1 m reachable and flat.
    ok = np.ones(len(pts), bool)
    for dr in range(-4, 5, 2):
        for dc in range(-4, 5, 2):
            rr = np.clip(rows + dr, 0, H.shape[0] - 1); cc = np.clip(cols + dc, 0, H.shape[1] - 1)
            ok &= reach[rr, cc] & (np.abs(H[rr, cc] - H[rows, cols]) < 10)
    pts = pts[ok]
    for x, z in keep_away_xz:
        pts = pts[np.hypot(pts[:, 0] - x, pts[:, 1] - z) > keep_away_cm]
    # Stay well inside the district perimeter walls.
    xmin, xmax = lo[0] + 400.0, lo[0] + H.shape[1] * STEP - 400.0
    zmin, zmax = lo[2] + 400.0, lo[2] + H.shape[0] * STEP - 400.0
    pts = pts[(pts[:, 0] > xmin) & (pts[:, 0] < xmax) & (pts[:, 1] > zmin) & (pts[:, 1] < zmax)]
    # Poisson-disk style: random order, accept points at least min_spacing from all chosen.
    rng = np.random.default_rng(seed)
    chosen = []
    for i in rng.permutation(len(pts)):
        c = pts[i]
        if all(np.hypot(c[0] - o[0], c[1] - o[1]) >= min_spacing_cm for o in chosen):
            chosen.append(c)
            if len(chosen) == count:
                break
    return [tuple(map(float, c)) for c in chosen]


def actor_record(kind, x, floor_y, z, yaw):
    t = ENEMY_TYPES[kind]
    yaw = ((int(yaw) + 0x8000) % 0x10000) - 0x8000
    return struct.pack('>8sI3f3hH', t['name'].ljust(8, b'\0'), t['params'],
                       x, floor_y + t['lift_cm'] + 5.0, z, 0, yaw, 0, 0xFFFF)


def add_actors(dzr, records):
    """Append ACTR records. Bytes before the ACTR chunk are kept verbatim; ACTR and every chunk
    stored after it are rewritten with updated offsets (they hold no internal pointers)."""
    n = struct.unpack_from('>I', dzr, 0)[0]
    chunks = [list(struct.unpack_from('>4sII', dzr, 4 + i * 12)) for i in range(n)]
    actr = [c for c in chunks if c[0] == b'ACTR']
    assert len(actr) == 1, 'expected one ACTR chunk'
    actr = actr[0]
    later = sorted([c for c in chunks if c[2] > actr[2]], key=lambda c: c[2])
    for c in chunks:
        assert c is actr or c[2] < actr[2] or c in later
    ends = [c[2] for c in later] + [len(dzr)]
    blobs = [bytes(dzr[c[2]:ends[k + 1]]) for k, c in enumerate(later)]
    out = bytearray(dzr[:actr[2]])
    out.extend(dzr[actr[2]:actr[2] + actr[1] * 0x20])
    out.extend(b''.join(records))
    actr[1] += len(records)
    for c, blob in zip(later, blobs):
        while len(out) % 4:
            out.append(0)
        c[2] = len(out)
        out.extend(blob)
    for i, c in enumerate(chunks):
        struct.pack_into('>4sII', out, 4 + i * 12, *c)
    while len(out) % 32:
        out.append(0)
    return bytes(out)


def read_actors(dzr):
    n = struct.unpack_from('>I', dzr, 0)[0]
    for i in range(n):
        tag, cnt, off = struct.unpack_from('>4sII', dzr, 4 + i * 12)
        if tag == b'ACTR':
            return [struct.unpack_from('>8sI3f3hH', dzr, off + k * 0x20) for k in range(cnt)]
    return []
