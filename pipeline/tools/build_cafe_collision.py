"""Create a TP DZB collision candidate from the converted static cafe geometry.
Uses the common DZB geometry/tree layout and writes TP-specific surface words.
This is mesh-derived prototype collision, not a translation of SH's gameplay flags.
"""
from pathlib import Path
from io import BytesIO
import sys,struct,json
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'dzb_tools/dzb_tools'))
from dzb import DZB,OctreeNode,OctreeBlock
out=ROOT/'sh_tp_project/assets';a=np.load(out/'cafe_collision_source.npz');v=a['vertices'];f=a['faces']
class BoundedDZB(DZB):
 def generate_octree_node(self,faces):
  node=OctreeNode(self.data);self.octree_nodes.append(node)
  if len(faces)<=10:
   block=OctreeBlock(self.data);block.faces=list(faces);self.octree_blocks.append(block);node.is_leaf=True;node.block=block;return node
  centers=np.array([[sum(getattr(v,a) for v in f.vertices)/3 for a in ['x_pos','y_pos','z_pos']] for f in faces])
  axis=int(np.ptp(centers,axis=0).argmax());order=np.argsort(centers[:,axis],kind='stable');mid=len(order)//2
  node.child_nodes=[self.generate_octree_node([faces[i] for i in ids]) for ids in [order[:mid],order[mid:]]]+[None]*6
  return node
d=BoundedDZB();g=d.add_group('cafe');g.room_index=0;prop=d.add_property()
for face in f:d.add_face([tuple(map(float,p)) for p in v[face]],prop,g)
d.save_changes();raw=bytearray(d.data.getvalue());prop_off=struct.unpack_from('>I',raw,0x2c)[0];group_off=struct.unpack_from('>I',raw,0x24)[0]
# TP: no exit (0x3f), neutral poly color (0xff), no through flags;
# no linked actor/camera/path; passFlag=0 means normal solid surface.
struct.pack_into('>4I',raw,prop_off,0x3fff,0xff,0xffffff00,0)
struct.pack_into('>I',raw,group_off+0x30,0)
check=DZB();check.read(BytesIO(raw));assert len(check.faces)==len(f)
assert len(check.groups)==1 and check.groups[0].room_index==0
(out/'cafe.dzb').write_bytes(raw)
# Check a point selected in the visible cafe aisle has an upward-facing floor.
x,z=200.0,200.0;hits=[]
for tri in v[f]:
 n=np.cross(tri[1]-tri[0],tri[2]-tri[0])
 if n[1]<=1e-6:continue
 p=tri[:,[0,2]];M=np.array([p[1]-p[0],p[2]-p[0]]).T
 if abs(np.linalg.det(M))<1e-6:continue
 u,w=np.linalg.solve(M,np.array([x,z])-p[0])
 if u>=-1e-6 and w>=-1e-6 and u+w<=1+1e-6:
  y=float(tri[0,1]+u*(tri[1,1]-tri[0,1])+w*(tri[2,1]-tri[0,1]))
  if y<150:hits.append(y)
assert hits,'No floor below proposed spawn'
report={'vertices':len(d.vertices),'faces':len(d.faces),'octree_nodes':len(d.octree_nodes),'bytes':len(raw),'spawn_cm':[x,max(hits)+5,z],'collision':'mesh-derived candidate; gameplay testing required'}
(out/'collision_report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
