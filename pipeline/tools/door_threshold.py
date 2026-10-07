"""Native scnChg threshold and supported doorway crossing for connected tests."""
from io import BytesIO
from pathlib import Path
import sys,struct
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'dzb_tools/dzb_tools'))
from dzb import DZB,OctreeNode,OctreeBlock

class BoundedDZB(DZB):
 def generate_octree_node(self,faces):
  node=OctreeNode(self.data);self.octree_nodes.append(node)
  if len(faces)<=10:
   block=OctreeBlock(self.data);block.faces=list(faces);self.octree_blocks.append(block);node.is_leaf=True;node.block=block;return node
  centers=np.array([[sum(getattr(v,a) for v in f.vertices)/3 for a in ('x_pos','y_pos','z_pos')] for f in faces])
  axis=int(np.ptp(centers,axis=0).argmax());order=np.argsort(centers[:,axis],kind='stable');mid=len(order)//2
  node.child_nodes=[self.generate_octree_node([faces[i] for i in ids]) for ids in (order[:mid],order[mid:])]+[None]*6
  return node

def world(area,point):
 a=area['facing']*np.pi/32768;s,c=np.sin(a),np.cos(a)
 x,y,z=point
 return np.array(area['door'])+np.array([c*x+s*z,y,-s*x+c*z])

def trigger_record(area):
 # TGSC scale bytes become scale/10; scnChg uses half widths 75*x,75*z,
 # vertical range 0..150*y. Local doorway span z[-605,-5], x +/-112.5.
 pos=world(area,(0,-300,-305))
 return struct.pack('>8sI3f3hH4B',b'scnChg',0xffff0100,*pos,-1,area['facing'],-1,65535,15,80,40,255)

def supported_collision(raw,area):
 old=DZB();old.read(BytesIO(raw));assert len(old.groups)==1 and len(old.properties)==1
 d=BoundedDZB();g=d.add_group('door_supported');g.room_index=0;p=d.add_property()
 for face in old.faces:
  d.add_face([tuple(getattr(v,a) for a in ('x_pos','y_pos','z_pos')) for v in face.vertices],p,g)
 added=[]
 def quad(points,two_sided=False):
  pts=[world(area,q) for q in points]
  faces=[(0,1,2),(0,2,3)]
  if two_sided:faces += [(2,1,0),(3,2,0)]
  for f in faces:
   tri=[tuple(pts[i]) for i in f];d.add_face(tri,p,g);added.append(tri)
 # Upward winding, 10 cm below threshold. End and side stops bound the fallback.
 quad([(-120,-10,50),(120,-10,50),(120,-10,-650),(-120,-10,-650)])
 quad([(-120,-20,-650),(120,-20,-650),(120,350,-650),(-120,350,-650)],True)
 for x in (-120,120):quad([(x,-20,0),(x,-20,-650),(x,350,-650),(x,350,0)],True)
 d.save_changes();out=bytearray(d.data.getvalue());prop=struct.unpack_from('>I',out,0x2c)[0];group=struct.unpack_from('>I',out,0x24)[0]
 # Preserve TP-specific solid surface words, not the exporter WW defaults.
 old_prop=struct.unpack_from('>I',raw,0x2c)[0]
 out[prop:prop+16]=raw[old_prop:old_prop+16];struct.pack_into('>I',out,group+0x30,0)
 return bytes(out),np.array(added)
