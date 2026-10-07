"""Create a TP DZB collision candidate from the converted static outdoor geometry.
Uses the common DZB geometry/tree layout and writes TP-specific surface words.
This is mesh-derived prototype collision, not a translation of SH's gameplay flags.
"""
from pathlib import Path
from io import BytesIO
import sys,struct,json
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'dzb_tools/dzb_tools'))
from dzb import DZB,OctreeNode,OctreeBlock
out=ROOT/'sh_tp_project/outdoor/assets';a=np.load(out/'outdoor_collision_source.npz');v=a['vertices'];f=a['faces']
# Keep this isolated street test inside the ground-covered road and pavement.
# Boundary quads are collision only, with both windings; no extra rendered walls.
bounds = (-150., 1970., -1970., 1970.)
x0,x1,z0,z1=bounds
corners=[(x0,z0),(x1,z0),(x1,z1),(x0,z1)]
extra_v=[];extra_f=[]
for i in range(4):
 a,b=corners[i],corners[(i+1)%4];start=len(v)+len(extra_v)
 extra_v.extend([(a[0],-50,a[1]),(b[0],-50,b[1]),(b[0],1200,b[1]),(a[0],1200,a[1])])
 extra_f.extend([[start+j for j in face] for face in [(0,1,2),(0,2,3),(2,1,0),(3,2,0)]])
v=np.concatenate([v,np.array(extra_v)]);f=np.concatenate([f,np.array(extra_f)])
class BoundedDZB(DZB):
 def generate_octree_node(self,faces):
  node=OctreeNode(self.data);self.octree_nodes.append(node)
  if len(faces)<=10:
   block=OctreeBlock(self.data);block.faces=list(faces);self.octree_blocks.append(block);node.is_leaf=True;node.block=block;return node
  centers=np.array([[sum(getattr(v,a) for v in f.vertices)/3 for a in ['x_pos','y_pos','z_pos']] for f in faces])
  axis=int(np.ptp(centers,axis=0).argmax());order=np.argsort(centers[:,axis],kind='stable');mid=len(order)//2
  node.child_nodes=[self.generate_octree_node([faces[i] for i in ids]) for ids in [order[:mid],order[mid:]]]+[None]*6
  return node
d=BoundedDZB();g=d.add_group('outdoor');g.room_index=0;prop=d.add_property()
for face in f:d.add_face([tuple(map(float,p)) for p in v[face]],prop,g)
d.save_changes();raw=bytearray(d.data.getvalue());prop_off=struct.unpack_from('>I',raw,0x2c)[0];group_off=struct.unpack_from('>I',raw,0x24)[0]
# TP: no exit (0x3f), neutral poly color (0xff), no through flags;
# no linked actor/camera/path; passFlag=0 means normal solid surface.
struct.pack_into('>4I',raw,prop_off,0x3fff,0xff,0xffffff00,0)
struct.pack_into('>I',raw,group_off+0x30,0)
check=DZB();check.read(BytesIO(raw));assert len(check.faces)==len(f)
assert len(check.groups)==1 and check.groups[0].room_index==0
(out/'outdoor.dzb').write_bytes(raw)
# Check a point selected in the visible outdoor aisle has an upward-facing floor.
x,z=500.0,0.0;hits=[]
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
report={'vertices':len(d.vertices),'faces':len(d.faces),'octree_nodes':len(d.octree_nodes),'bytes':len(raw),'spawn_cm':[x,max(hits)+5,z],'bounds_xz_cm':list(bounds),'boundary_triangles':len(extra_f),'collision':'mesh-derived candidate with perimeter limits; gameplay testing required'}
(out/'collision_report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))

# Raycast a 60 cm footprint and verify no geometry within standing headroom.
def vertical_hits(x,z):
 hits=[]
 for tri in v[f]:
  p=tri[:,[0,2]];M=np.array([p[1]-p[0],p[2]-p[0]]).T
  if abs(np.linalg.det(M))<1e-6:continue
  u,w=np.linalg.solve(M,np.array([x,z])-p[0])
  if u>=-1e-6 and w>=-1e-6 and u+w<=1+1e-6:
   n=np.cross(tri[1]-tri[0],tri[2]-tri[0]);n=n/np.linalg.norm(n)
   hits.append((float(tri[0,1]+u*(tri[1,1]-tri[0,1])+w*(tri[2,1]-tri[0,1])),float(n[1])))
 return hits
floor=report['spawn_cm'][1]-5
for dx in (-30,0,30):
 for dz in (-30,0,30):
  h=vertical_hits(x+dx,z+dz)
  assert any(abs(y-floor)<2 and ny>0.7 for y,ny in h),'Uneven spawn footprint'
  assert not any(floor+10<y<floor+190 for y,ny in h),'Obstructed spawn'
report['spawn_checks']={'footprint_cm':60,'headroom_cm':190,'samples':9,'passed':True}
(out/'collision_report.json').write_text(json.dumps(report,indent=2))
print('PASS: spawn floor, footprint and headroom')
