"""Build a multi-tile Old Silent Hill district for one TP room (0.6.0+).

Steps (all driven by district/config.json):
  1. Export the configured SH tiles with the pinned sh_ipd2obj (belek666, 0be5820) and merge them
     in original SH grid coordinates (no repositioning), exactly like build_town_source.py.
  2. Encode a compact single-joint J3D BMD:
       - C8 textures with RGB5A3 palettes (SH textures have <=128 colours: lossless vs RGB5A3)
       - S16 fixed-point positions and UVs, one shared white vertex colour (INDEX8)
       - no normal array (materials are unlit, as in 0.5.0)
  3. Build mesh-derived DZB collision limited to geometry Link can reach (triangles whose lowest
     point is under collision_max_low_point_cm), plus a solid perimeter at the district edge.
  4. Write reports and a ground-coverage map used by validate_district.py.
"""
from pathlib import Path
from io import BytesIO
import sys, struct, copy, json, shutil, subprocess, math
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / 'sh_tp_project'
sys.path.insert(0, str(ROOT / 'gclib'))
sys.path.insert(0, str(ROOT / 'dzb_tools/dzb_tools'))
from gclib.bunfoe import BUNFOE, fields
from gclib.rarc import RARC
from gclib.j3d import BMD
from gclib import fs_helpers as fs
from gclib.j3d_chunks.mat3 import TexCoord, TevOrder, TevSwapMode
from gclib.bunfoe_types import Vec3float
from gclib.texture_utils import ImageFormat
from gclib.gx_enums import FilterMode, WrapMode, PaletteFormat
import gclib.gx_enums as GX
from dzb import DZB, OctreeNode, OctreeBlock
sys.path.insert(0, str(Path(__file__).resolve().parent))
from district_coverage import analyse, barrier_quads

CFG = json.loads((P / 'district/config.json').read_text())
SRC = P / 'district/source'
OUT = P / 'district/assets'
WORK = ROOT / 'tp_work/district'
for d in (SRC, OUT, WORK):
    d.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------ 1. export + merge
def export_tiles():
    bg = ROOT / 'sh_work/assets/BG'
    for p in list(bg.glob('*.TIM')) + list(bg.glob('*.PLM')):
        shutil.copy2(p, WORK / p.name)
    lines = ['mtllib DISTRICT.MTL']
    materials = {}
    vo = uo = 0
    for name in CFG['tiles']:
        shutil.copy2(bg / (name + '.IPD'), WORK / (name + '.IPD'))
        with (WORK / (name + '.log')).open('w') as log:
            subprocess.run([str(ROOT / 'tp_work/ipd2obj'), name + '.IPD'], cwd=WORK,
                           stdout=log, stderr=log, check=True)
        mat = None
        for line in (WORK / (name + '.MTL')).read_text().splitlines():
            s = line.split()
            if not s:
                continue
            if s[0] == 'newmtl':
                mat = s[1]
            elif s[0] == 'map_Kd':
                assert mat not in materials or materials[mat] == s[1]
                materials[mat] = s[1]
                shutil.copy2(WORK / s[1], SRC / s[1])
        nv = nu = 0
        for line in (WORK / (name + '.OBJ')).read_text().splitlines():
            s = line.split()
            if not s:
                continue
            if s[0] == 'v':
                nv += 1; lines.append(line)
            elif s[0] == 'vt':
                nu += 1; lines.append(line)
            elif s[0] == 'usemtl':
                lines.append(line)
            elif s[0] == 'f':
                idx = []
                for item in s[1:]:
                    a = item.split('/'); assert int(a[0]) > 0
                    idx.append(str(int(a[0]) + vo) + ('/' + str(int(a[1]) + uo) if len(a) > 1 and a[1] else '/'))
                lines.append('f ' + ' '.join(idx))
        vo += nv; uo += nu
    (SRC / 'DISTRICT.OBJ').write_text('\n'.join(lines) + '\n')
    (SRC / 'DISTRICT.MTL').write_text('\n'.join('newmtl ' + k + '\nmap_Kd ' + v for k, v in materials.items()) + '\n')
    (SRC / 'manifest.json').write_text(json.dumps({
        'source_tiles': CFG['tiles'], 'origin_metres': CFG['origin_metres'],
        'alignment': 'Original SH grid, 40 metres per tile; no tile repositioning',
        'exporter': 'belek666/sh_ipd2obj 0be58209 patched by tools/export_cafe.py'}, indent=2) + '\n')
    return vo


def load_obj():
    vs, uv, faces, paths = [], [], [], {}
    mat = None
    for line in (SRC / 'DISTRICT.MTL').read_text().splitlines():
        s = line.split()
        if s and s[0] == 'newmtl':
            mat = s[1]
        elif s and s[0] == 'map_Kd':
            paths[mat] = SRC / s[1]
    for line in (SRC / 'DISTRICT.OBJ').read_text().splitlines():
        s = line.split()
        if not s:
            continue
        if s[0] == 'v':
            vs.append([float(x) for x in s[1:4]])
        elif s[0] == 'vt':
            uv.append([float(s[1]), 1 - float(s[2])])
        elif s[0] == 'usemtl':
            mat = s[1]
        elif s[0] == 'f':
            idx = [tuple(int(x) - 1 if x else -1 for x in a.split('/')[:2]) for a in s[1:]]
            for i in range(1, len(idx) - 1):
                tri = [idx[0], idx[i], idx[i + 1]]
                faces.append((tri, mat if all(v[1] >= 0 for v in tri) else '_untextured'))
    vs = (np.asarray(vs) - CFG['origin_metres']) * 100.0
    uv.append([0.0, 0.0])
    groups = {}
    for tri, m in faces:
        p = vs[[a[0] for a in tri]]
        if np.linalg.norm(np.cross(p[1] - p[0], p[2] - p[0])) < 1e-6:
            continue  # degenerate
        groups.setdefault(m, []).append([(a, b if b >= 0 else len(uv) - 1) for a, b in tri])
    return vs, np.asarray(uv), groups, paths


# ------------------------------------------------------------------ 2. compact BMD
def pack(fmt, *a): return struct.pack('>' + fmt, *a)
def pad(b, n=32): b.extend(b'\0' * ((-len(b)) % n)); return b
def s32(b, o, v): struct.pack_into('>I', b, o, v)
def chunk(tag, b):
    b = pad(bytearray(b)); b[:4] = tag.encode(); struct.pack_into('>I', b, 4, len(b)); return bytes(b)


def bind(value, stream, seen=None):
    seen = set() if seen is None else seen
    if id(value) in seen:
        return
    seen.add(id(value))
    if isinstance(value, BUNFOE):
        value.data = stream
        for f in fields(value):
            if f.name not in ('data', 'mat3'):
                bind(getattr(value, f.name, None), stream, seen)
    elif isinstance(value, (list, tuple)):
        for v in value:
            bind(v, stream, seen)


def frac_bits(maxabs):
    for frac in range(15, -1, -1):
        if maxabs * (1 << frac) < 32000:
            return frac
    raise ValueError('coordinates too large for S16')


def build_model(vs, uv, groups, paths):
    names = list(groups); N = len(names)
    arc = RARC(str(P / 'overlay/res/Stage/R_SP108/R00_00.arc'))
    bmd = BMD(arc.get_file_entry('model.bmd').data)
    base = bmd.mat3.materials[0]; materials = []
    for i, name in enumerate(names):
        m = copy.deepcopy(base); m.mat3 = bmd.mat3; m.data = bmd.mat3.data
        m.num_tex_gens = 1; m.num_tev_stages = 1; m.num_color_chans = 1; m.cull_mode = GX.CullMode.Cull_None
        m.textures = [i] + [None] * 7; m.tex_coord_gens = [TexCoord()] + [None] * 7
        m.post_tex_coord_gens = [None] * 8; m.tex_matrixes = [None] * 10; m.post_tex_matrixes = [None] * 20
        for c in m.color_channels:
            if c:
                c.lighting_enabled = False; c.mat_color_src = GX.ColorSrc.Vertex; c.used_lights = [False] * 8
        st = copy.deepcopy(base.tev_stages[0])
        st.color_in_a = GX.CombineColor.ZERO; st.color_in_b = GX.CombineColor.TEXC
        st.color_in_c = GX.CombineColor.RASC; st.color_in_d = GX.CombineColor.ZERO
        st.alpha_in_a = GX.CombineAlpha.ZERO; st.alpha_in_b = GX.CombineAlpha.TEXA
        st.alpha_in_c = GX.CombineAlpha.RASA; st.alpha_in_d = GX.CombineAlpha.ZERO
        m.tev_stages = [st] + [None] * 15
        m.tev_orders = [TevOrder(channel_id=GX.ColorChannelID.COLOR0A0)] + [None] * 15
        m.tev_swap_modes = [TevSwapMode()] + [None] * 15
        m.tev_swap_mode_tables = [copy.deepcopy(base.tev_swap_mode_tables[0])] + [None] * 15
        m.pixel_engine_mode = GX.PixelEngineMode.Opaque
        m.alpha_compare.comp0 = GX.CompareType.Greater_Equal; m.alpha_compare.ref0 = 128
        m.alpha_compare.comp1 = GX.CompareType.Always; m.alpha_compare.ref1 = 0
        bind(m, bmd.mat3.data); materials.append(m)
    bmd.mat3.materials = materials
    bmd.mat3.mat_names = [f'sh_district_{i:02}' for i in range(N)]
    bmd.mat3.indirects = []; bmd.mat3.save()

    # Textures: C8 + RGB5A3 palette.
    template = bmd.tex1.textures[0]; texs = []
    texdata = BytesIO(b'TEX1' + b'\0' * (0x20 + N * 0x20 - 4))
    fs.write_u16(texdata, 8, N); fs.write_u16(texdata, 10, 0xffff); fs.write_u32(texdata, 12, 0x20)
    for i, name in enumerate(names):
        t = copy.deepcopy(template); t.data = texdata; t.header_offset = 0x20 + i * 0x20
        t.image_format = ImageFormat.C8; t.palette_format = PaletteFormat.RGB5A3; t.mipmap_count = 1
        t.min_filter = FilterMode.Nearest; t.mag_filter = FilterMode.Nearest
        t.wrap_s = WrapMode.ClampToEdge; t.wrap_t = WrapMode.ClampToEdge
        img = Image.open(paths[name]).convert('RGBA') if name in paths else Image.new('RGBA', (8, 8), (100, 97, 90, 255))
        t.replace_image(img); texs.append(t)
    bmd.tex1.data = texdata; bmd.tex1.num_textures = N; bmd.tex1.textures = texs
    bmd.tex1.texture_names = [f'shd_{i:02}' for i in range(N)]; bmd.tex1.save()

    # Vertex arrays: S16 positions and UVs (de-duplicated after quantisation); one white colour.
    pfrac = frac_bits(float(np.abs(vs).max())); tfrac = frac_bits(float(np.abs(uv).max()))
    pos_q = np.round(vs * (1 << pfrac)).astype(np.int32); uv_q = np.round(uv * (1 << tfrac)).astype(np.int32)
    pos_u, pos_map = np.unique(pos_q, axis=0, return_inverse=True)
    uv_u, uv_map = np.unique(uv_q, axis=0, return_inverse=True)
    pos_map = pos_map.reshape(-1); uv_map = uv_map.reshape(-1)
    assert len(pos_u) < 65536 and len(uv_u) < 65536, (len(pos_u), len(uv_u))
    groups = {k: [[(int(pos_map[a]), int(uv_map[t])) for a, t in tri] for tri in g] for k, g in groups.items()}
    pos16 = pos_u.astype('>i2'); uv16 = uv_u.astype('>i2')
    max_err = float(np.abs(pos_q.astype(float) / (1 << pfrac) - vs).max())
    vs_render = pos_u.astype(float) / (1 << pfrac)
    b = bytearray(0x40); s32(b, 8, 0x40)
    for attr, count, typ, frac in [(9, 1, 3, pfrac), (11, 1, 5, 0), (13, 1, 3, tfrac), (255, 0, 0, 0)]:
        b.extend(pack('IIIB3x', attr, count, typ, frac))
    pad(b)
    for index, data in [(0, pos16.tobytes()), (3, bytes([255] * 4)), (5, uv16.tobytes())]:
        s32(b, 0xc + index * 4, len(b)); b.extend(data); pad(b)
    vtx = chunk('VTX1', b)

    # Shapes: one triangle list per material. Descriptor POS idx16, CLR0 idx8, TEX0 idx16.
    desc = [(9, 3), (11, 2), (13, 3), (255, 0)]
    b = bytearray(0x30); struct.pack_into('>HH', b, 8, N, 0xffff)
    shape_off = len(b); b.extend(b'\0' * (N * 0x28)); s32(b, 0xc, shape_off)
    s32(b, 0x10, len(b)); b.extend(b''.join(pack('H', i) for i in range(N))); pad(b, 4); s32(b, 0x14, 0)
    s32(b, 0x18, len(b)); b.extend(b''.join(pack('II', a, t) for a, t in desc))
    s32(b, 0x1c, len(b)); b.extend(pack('H', 0)); pad(b, 4)
    s32(b, 0x24, len(b)); b.extend(b''.join(pack('HHI', 0, 1, 0) for _ in range(N)))
    s32(b, 0x28, len(b)); draw_off = len(b); b.extend(b'\0' * (N * 8)); pad(b)
    prim_off = len(b); s32(b, 0x20, prim_off)
    for i, name in enumerate(names):
        tris = groups[name]; start = len(b)
        verts = [v for tri in tris for v in tri]
        for c0 in range(0, len(verts), 65535 // 3 * 3):  # GX vertex count is u16
            part = verts[c0:c0 + 65535 // 3 * 3]
            b.extend(pack('BH', 0x90, len(part)))
            for p_idx, t_idx in part:
                b.extend(pack('HBH', p_idx, 0, t_idx))
        pad(b)
        struct.pack_into('>II', b, draw_off + i * 8, len(b) - start, start - prim_off)
        pts = vs_render[[v[0] for v in verts]]; lo = pts.min(0); hi = pts.max(0)
        radius = float(np.linalg.norm(pts, axis=1).max())
        struct.pack_into('>BBHHHHHf6f', b, shape_off + i * 0x28, 0, 255, 1, 0, i, i, 65535, radius, *lo, *hi)
    shp = chunk('SHP1', b)

    b = bytearray(0x18); struct.pack_into('>HHIII', b, 8, 0, 0xffff, N, len(vs_render), 0x18)
    b.extend(pack('4H', 0x10, 0, 1, 0))
    for i in range(N):
        b.extend(pack('8H', 0x11, i, 1, 0, 0x12, i, 2, 0))
    b.extend(pack('4H', 2, 0, 0, 0)); inf = chunk('INF1', b)
    evp = chunk('EVP1', bytearray(0x20))
    b = bytearray(0x20); struct.pack_into('>HHII', b, 8, 1, 0xffff, 0x14, 0x16); drw = chunk('DRW1', b)
    assert len(bmd.jnt1.joints) == 1
    j = bmd.jnt1.joints[0]; j.scale = Vec3float(x=1, y=1, z=1); j.rotation.x = j.rotation.y = j.rotation.z = 0
    j.translation = Vec3float(x=0, y=0, z=0)
    j.bounding_box_min = Vec3float(**dict(zip('xyz', vs.min(0))))
    j.bounding_box_max = Vec3float(**dict(zip('xyz', vs.max(0))))
    j.bounding_sphere_radius = float(np.linalg.norm(vs, axis=1).max()); bind(j, bmd.jnt1.data); bmd.jnt1.save()
    chunks = [inf, vtx, evp, drw, bmd.jnt1.data.getvalue(), shp, bmd.mat3.data.getvalue(), bmd.tex1.data.getvalue()]
    header = bytearray(b'J3D2bmd3' + b'\0' * 24); s32(header, 8, 32 + sum(map(len, chunks)))
    s32(header, 12, len(chunks)); header[16:20] = b'SVR3'
    result = bytes(header) + b''.join(chunks)
    verified = BMD(BytesIO(result))
    assert len(verified.shp1.shapes) == N and len(verified.tex1.textures) == N
    for t in verified.tex1.textures:
        assert t.image_format == ImageFormat.C8 and t.palette_format == PaletteFormat.RGB5A3
    return result, {'materials': N, 'position_frac_bits': pfrac, 'uv_frac_bits': tfrac,
                    'max_position_error_cm': max_err, 'unique_positions': len(pos_u), 'unique_uvs': len(uv_u),
                    'texture_format': 'C8 + RGB5A3 palette', 'bytes': len(result),
                    'texture_sources': [paths[n].name if n in paths else None for n in names]}


# ------------------------------------------------------------------ 3. collision
class BoundedDZB(DZB):
    def generate_octree_node(self, faces):
        node = OctreeNode(self.data); self.octree_nodes.append(node)
        if len(faces) <= 10:
            block = OctreeBlock(self.data); block.faces = list(faces); self.octree_blocks.append(block)
            node.is_leaf = True; node.block = block; return node
        centers = np.array([[sum(getattr(v, a) for v in f.vertices) / 3 for a in ['x_pos', 'y_pos', 'z_pos']] for f in faces])
        axis = int(np.ptp(centers, axis=0).argmax()); order = np.argsort(centers[:, axis], kind='stable'); mid = len(order) // 2
        node.child_nodes = [self.generate_octree_node([faces[i] for i in ids]) for ids in [order[:mid], order[mid:]]] + [None] * 6
        return node


def build_collision(vs, groups):
    tris = np.array([[v[0] for v in tri] for g in groups.values() for tri in g])
    low = vs[tris][:, :, 1].min(1)
    keep = low < CFG['collision_max_low_point_cm']
    tris = tris[keep]
    lo = vs.min(0); hi = vs.max(0); inset = CFG['boundary_inset_cm']
    x0, x1, z0, z1 = lo[0] + inset, hi[0] - inset, lo[2] + inset, hi[2] - inset
    corners = [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]
    v = list(map(tuple, vs)); f = [list(t) for t in tris]; added = 0
    for i in range(4):
        a, b_ = corners[i], corners[(i + 1) % 4]; s = len(v)
        v.extend([(a[0], -50, a[1]), (b_[0], -50, b_[1]), (b_[0], 1200, b_[1]), (a[0], 1200, a[1])])
        for face in [(0, 1, 2), (0, 2, 3), (2, 1, 0), (3, 2, 0)]:
            f.append([s + j for j in face]); added += 1
    v = np.array(v, dtype=float); f = np.array(f)
    # Seal walkable edges that drop into floor-less space (e.g. open-backed building blocks).
    cov = analyse(v, f, tuple(CFG['spawn_xz_cm']))
    quads = barrier_quads(cov); v = list(map(tuple, v)); f = [list(x) for x in f]
    for q in quads:
        s = len(v); v.extend(q)
        for face in [(0, 1, 2), (0, 2, 3), (2, 1, 0), (3, 2, 0)]:
            f.append([s + j for j in face])
    v = np.array(v, dtype=float); f = np.array(f)
    d = BoundedDZB(); g = d.add_group('district'); g.room_index = CFG['room']; prop = d.add_property()
    for face in f:
        d.add_face([tuple(map(float, p)) for p in v[face]], prop, g)
    d.save_changes(); raw = bytearray(d.data.getvalue())
    prop_off = struct.unpack_from('>I', raw, 0x2c)[0]; group_off = struct.unpack_from('>I', raw, 0x24)[0]
    struct.pack_into('>4I', raw, prop_off, 0x3fff, 0xff, 0xffffff00, 0)  # same TP words as 0.5.0
    struct.pack_into('>I', raw, group_off + 0x30, 0)
    check = DZB(); check.read(BytesIO(raw)); assert len(check.faces) == len(f)
    np.savez(OUT / 'district_collision_source.npz', vertices=v, faces=f)
    return bytes(raw), {'source_triangles': int(keep.size), 'kept_triangles': int(keep.sum()),
                        'boundary_triangles': added, 'drop_barrier_quads': len(quads), 'faces': len(f), 'tree_nodes': len(d.octree_nodes),
                        'bytes': len(raw), 'bounds_xz_cm': [x0, x1, z0, z1]}


if __name__ == '__main__':
    nverts = export_tiles()
    vs, uv, groups, paths = load_obj()
    model, mrep = build_model(vs, uv, groups, paths)
    (OUT / 'district.bmd').write_bytes(model)
    coll, crep = build_collision(vs, groups)
    (OUT / 'district.dzb').write_bytes(coll)
    report = {'version': CFG['version'], 'tiles': CFG['tiles'], 'vertices': len(vs),
              'triangles': sum(map(len, groups.values())),
              'bounds_cm': [vs.min(0).tolist(), vs.max(0).tolist()], 'model': mrep, 'collision': crep}
    (OUT / 'build_report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=1))
