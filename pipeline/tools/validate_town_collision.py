"""Regression check for the native collision-loader crash, using raw bytes.
No game installation or third-party Python packages required.
"""
from pathlib import Path
import struct, zipfile, json, sys

project = Path(__file__).resolve().parents[1]
outdoor = '--outdoor' in sys.argv
mod_path = 'TownMods/SilentHillTown.dusk'
asset_path = 'town/assets/town_supported.dzb'
with zipfile.ZipFile(project/mod_path) as mod:
    assert mod.testzip() is None
    metadata = json.loads(mod.read('mod.json'))
    archive = mod.read('overlay/res/Stage/R_SP109/R00_00.arc')

def u32(data, at): return struct.unpack_from('>I', data, at)[0]
assert archive[:4] == b'RARC'
node_count = u32(archive, 0x20)
node_table = 0x20 + u32(archive, 0x24)
entry_table = 0x20 + u32(archive, 0x2c)
string_table = 0x20 + u32(archive, 0x34)
data_base = 0x20 + u32(archive, 0x0c)
collision = None
for i in range(node_count):
    node = node_table + i*16
    kind = archive[node:node+4]
    count = struct.unpack_from('>H', archive, node+10)[0]
    first = u32(archive, node+12)
    for j in range(first, first+count):
        entry = entry_table + j*20
        attributes = archive[entry+4]
        if not attributes & 1: continue
        name_at = string_table + struct.unpack_from('>H', archive, entry+6)[0]
        name = archive[name_at:archive.index(0, name_at)].decode()
        if name == 'room.dzb':
            assert kind == b'DZB ', f'Wrong native loader: {kind!r}'
            at, size = struct.unpack_from('>II', archive, entry+8)
            collision = archive[data_base+at:data_base+at+size]
assert collision is not None
assert collision == (project/asset_path).read_bytes()

vnum, voff, tnum, toff, bnum, boff, nnum, noff, gnum, goff, pnum, poff, flags = struct.unpack_from('>13I', collision)
for count, offset, size in [(vnum,voff,12),(tnum,toff,10),(bnum,boff,2),
                            (nnum,noff,20),(gnum,goff,52),(pnum,poff,16)]:
    assert count > 0 and offset >= 52 and offset+count*size <= len(collision)
report_path = 'town/assets/collision_report.json'
report = json.loads((project/report_path).read_text())
assert tnum == 12328 and vnum < 65536 and not flags & 0x80000000
for i in range(tnum):
    a,b,c,prop,group = struct.unpack_from('>5H', collision, toff+i*10)
    assert max(a,b,c) < vnum and prop < pnum and group < gnum
starts = list(struct.unpack_from('>'+str(bnum)+'H', collision, boff))
assert starts[0] == 0 and starts == sorted(set(starts)) and starts[-1] < tnum
nodes = [struct.unpack_from('>10H', collision, noff+i*20) for i in range(nnum)]
visited = set()
leaves = set()
def visit(i, parent):
    assert i < nnum and i not in visited, 'Invalid or cyclic collision tree'
    visited.add(i)
    flag, stored_parent, *children = nodes[i]
    # TP traverses child indices; this exporter leaves optional back-links unset.
    assert stored_parent in (parent, 0xffff)
    if flag & 1:
        assert children[0] < bnum
        leaves.add(children[0])
    else:
        for child in children:
            if child != 0xffff: visit(child,i)
for i in range(gnum):
    group = goff+i*52
    name_offset = u32(collision, group)
    assert name_offset < len(collision)
    root = struct.unpack_from('>H', collision, group+0x2e)[0]
    if root != 0xffff: visit(root,0xffff)
assert len(visited) == nnum and leaves == set(range(bnum))
print(f"PASS {metadata['version']}: DZB resource dispatch, {tnum} triangles, {nnum} tree nodes, all indices in bounds")
