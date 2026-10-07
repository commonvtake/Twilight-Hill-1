"""Convert the outdoor TOWN OBJ into a single-joint J3D BMD for a TP room.
Uses the game's material container as a template; writes new geometry/display lists.
"""
from pathlib import Path
from io import BytesIO
import sys,struct,copy,json,math
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'gclib'))
from gclib.bunfoe import BUNFOE, fields
from gclib.rarc import RARC
from gclib.j3d import BMD
from gclib import fs_helpers as fs
from gclib.j3d_chunks.mat3 import TexCoord,TevStage,TevOrder,TevSwapMode,TevSwapModeTable
from gclib.bunfoe_types import Vec3float
from gclib.texture_utils import ImageFormat
from gclib.gx_enums import FilterMode,WrapMode
import gclib.gx_enums as GX
OUT=ROOT/'sh_tp_project/town/assets';OUT.mkdir(parents=True,exist_ok=True)
CAFE=ROOT/'sh_tp_project/town/source'
def pack(fmt,*a):return struct.pack('>'+fmt,*a)
def pad(b,n=32):b.extend(b'\0'*((-len(b))%n));return b
def chunk(tag,b):
 b=pad(bytearray(b));b[:4]=tag.encode();struct.pack_into('>I',b,4,len(b));return bytes(b)
def s32(b,o,v):struct.pack_into('>I',b,o,v)
def bind(value, stream, seen=None):
 if seen is None:seen=set()
 if id(value) in seen:return
 seen.add(id(value))
 if isinstance(value,BUNFOE):
  value.data=stream
  for f in fields(value):
   if f.name not in ('data','mat3'):bind(getattr(value,f.name,None),stream,seen)
 elif isinstance(value,(list,tuple)):
  for v in value:bind(v,stream,seen)
def obj():
 vs=[];uv=[];faces=[];mat=None;paths={}
 for line in (CAFE/'TOWN.MTL').read_text().splitlines():
  s=line.split()
  if not s:continue
  if s[0]=='newmtl':mat=s[1]
  elif s[0]=='map_Kd':paths[mat]=CAFE/s[1]
 for line in (CAFE/'TOWN.OBJ').read_text().splitlines():
  s=line.split()
  if not s:continue
  if s[0]=='v':vs.append([float(x) for x in s[1:]])
  elif s[0]=='vt':uv.append([float(s[1]),1-float(s[2])])
  elif s[0]=='usemtl':mat=s[1]
  elif s[0]=='f':
   idx=[tuple(int(x)-1 if x else -1 for x in a.split('/')[:2]) for a in s[1:]]
   for i in range(1,len(idx)-1):
    tri=[idx[0],idx[i],idx[i+1]]; faces.append((tri,mat if all(v[1]>=0 for v in tri) else '_untextured'))
 vs=(np.asarray(vs)-[-20,0,60])*100
 uv.append([0,0]);groups={};normals=[]
 for tri,mat in faces:
  p=vs[[a[0] for a in tri]];n=np.cross(p[1]-p[0],p[2]-p[0]);norm=np.linalg.norm(n)
  if norm<1e-6:continue
  ni=len(normals);normals.append(n/norm)
  groups.setdefault(mat,[]).append([(a,ni,0,b if b>=0 else len(uv)-1) for a,b in tri])
 return vs,np.asarray(normals),np.asarray(uv),groups,paths
vs,normals,uv,groups,paths=obj();names=list(groups);N=len(names)
arc=RARC(str(ROOT/'sh_tp_project/overlay/res/Stage/R_SP108/R00_00.arc'))
bmd=BMD(arc.get_file_entry('model.bmd').data)
# Material settings: one opaque/cutout, unlit texture stage, white vertex color.
base=bmd.mat3.materials[0];materials=[];indirects=[]
for i,name in enumerate(names):
 m=copy.deepcopy(base);m.mat3=bmd.mat3;m.data=bmd.mat3.data;m.num_tex_gens=1;m.num_tev_stages=1;m.num_color_chans=1;m.cull_mode=GX.CullMode.Cull_None
 m.textures=[i]+[None]*7;m.tex_coord_gens=[TexCoord()]+[None]*7;m.post_tex_coord_gens=[None]*8;m.tex_matrixes=[None]*10;m.post_tex_matrixes=[None]*20
 for c in m.color_channels:
  if c:c.lighting_enabled=False;c.mat_color_src=GX.ColorSrc.Vertex;c.used_lights=[False]*8
 stage=copy.deepcopy(base.tev_stages[0]);stage.color_in_a=GX.CombineColor.ZERO;stage.color_in_b=GX.CombineColor.TEXC;stage.color_in_c=GX.CombineColor.RASC;stage.color_in_d=GX.CombineColor.ZERO
 stage.alpha_in_a=GX.CombineAlpha.ZERO;stage.alpha_in_b=GX.CombineAlpha.TEXA;stage.alpha_in_c=GX.CombineAlpha.RASA;stage.alpha_in_d=GX.CombineAlpha.ZERO
 m.tev_stages=[stage]+[None]*15;m.tev_orders=[TevOrder(channel_id=GX.ColorChannelID.COLOR0A0)]+[None]*15
 m.tev_swap_modes=[TevSwapMode()]+[None]*15;m.tev_swap_mode_tables=[copy.deepcopy(base.tev_swap_mode_tables[0])]+[None]*15
 m.pixel_engine_mode=GX.PixelEngineMode.Opaque
 m.alpha_compare.comp0=GX.CompareType.Greater_Equal;m.alpha_compare.ref0=128;m.alpha_compare.comp1=GX.CompareType.Always;m.alpha_compare.ref1=0
 if m.tex_indirect:indirects.append(m.tex_indirect)
 bind(m,bmd.mat3.data);materials.append(m)
bmd.mat3.materials=materials;bmd.mat3.mat_names=[f'sh_street_{i:02}' for i in range(N)];bmd.mat3.indirects=[];bmd.mat3.save()
# Replace the texture table. RGB5A3 preserves PS1-style opaque/cutout pixels.
template=bmd.tex1.textures[0];texs=[];texdata=BytesIO(b'TEX1'+b'\0'*(0x20+N*0x20-4));fs.write_u16(texdata,8,N);fs.write_u16(texdata,10,0xffff);fs.write_u32(texdata,12,0x20)
for i,name in enumerate(names):
 t=copy.deepcopy(template);t.data=texdata;t.header_offset=0x20+i*0x20;t.image_format=ImageFormat.RGB5A3;t.mipmap_count=1;t.min_filter=FilterMode.Nearest;t.mag_filter=FilterMode.Nearest;t.wrap_s=WrapMode.ClampToEdge;t.wrap_t=WrapMode.ClampToEdge
 t.replace_image(Image.open(paths[name]).convert('RGBA') if name in paths else Image.new('RGBA',(8,8),(100,97,90,255)));texs.append(t)
bmd.tex1.data=texdata;bmd.tex1.num_textures=N;bmd.tex1.textures=texs;bmd.tex1.texture_names=[f'cafe_{i:02}' for i in range(N)];bmd.tex1.save()
# Vertex arrays and their formats.
b=bytearray(0x40);s32(b,8,0x40)
for attr,count,typ in [(9,1,4),(10,0,4),(11,1,5),(13,1,4),(255,0,0)]:b.extend(pack('IIIB3x',attr,count,typ,0))
pad(b)
for index,data in [(0,vs.astype('>f4').tobytes()),(1,normals.astype('>f4').tobytes()),(3,bytes([255]*4)),(5,uv.astype('>f4').tobytes())]:
 s32(b,0xc+index*4,len(b));b.extend(data);pad(b)
vtx=chunk('VTX1',b)
# One draw packet per material, sharing joint zero and one vertex descriptor.
b=bytearray(0x30);struct.pack_into('>HH',b,8,N,0xffff);shape_off=len(b);b.extend(b'\0'*(N*0x28));s32(b,0xc,shape_off)
s32(b,0x10,len(b));b.extend(b''.join(pack('H',i) for i in range(N)));pad(b,4);s32(b,0x14,0)
s32(b,0x18,len(b));b.extend(b''.join(pack('II',a,3 if a!=255 else 0) for a in [9,10,11,13,255]));s32(b,0x1c,len(b));b.extend(pack('H',0));pad(b,4)
s32(b,0x24,len(b));b.extend(b''.join(pack('HHI',0,1,0) for _ in range(N)));s32(b,0x28,len(b));draw_off=len(b);b.extend(b'\0'*(N*8));pad(b);prim_off=len(b);s32(b,0x20,prim_off)
for i,name in enumerate(names):
 faces=groups[name];start=len(b);verts=[v for face in faces for v in face]
 assert len(verts)<65536
 b.extend(pack('BH',0x90,len(verts)))
 for indices in verts:b.extend(pack('4H',*indices))
 pad(b);struct.pack_into('>II',b,draw_off+i*8,len(b)-start,start-prim_off)
 points=vs[[v[0] for v in verts]];lo=points.min(0);hi=points.max(0);radius=float(np.linalg.norm(points,axis=1).max())
 struct.pack_into('>BBHHHHHf6f',b,shape_off+i*0x28,0,255,1,0,i,i,65535,radius,*lo,*hi)
shp=chunk('SHP1',b)
# Hierarchy: root joint, material children, shape children.
b=bytearray(0x18);struct.pack_into('>HHIII',b,8,0,0xffff,N,len(vs),0x18);b.extend(pack('4H',0x10,0,1,0))
for i in range(N):b.extend(pack('8H',0x11,i,1,0,0x12,i,2,0))
b.extend(pack('4H',2,0,0,0));inf=chunk('INF1',b)
evp=chunk('EVP1',bytearray(0x20));b=bytearray(0x20);struct.pack_into('>HHII',b,8,1,0xffff,0x14,0x16);drw=chunk('DRW1',b)
assert len(bmd.jnt1.joints)==1
j=bmd.jnt1.joints[0];j.scale=Vec3float(x=1,y=1,z=1);j.rotation.x=j.rotation.y=j.rotation.z=0;j.translation=Vec3float(x=0,y=0,z=0);j.bounding_box_min=Vec3float(**dict(zip('xyz',vs.min(0))));j.bounding_box_max=Vec3float(**dict(zip('xyz',vs.max(0))));j.bounding_sphere_radius=float(np.linalg.norm(vs,axis=1).max());bind(j,bmd.jnt1.data);bmd.jnt1.save()
chunks=[inf,vtx,evp,drw,bmd.jnt1.data.getvalue(),shp,bmd.mat3.data.getvalue(),bmd.tex1.data.getvalue()]
header=bytearray(b'J3D2bmd3'+b'\0'*24);s32(header,8,32+sum(map(len,chunks)));s32(header,12,len(chunks));header[16:20]=b'SVR3'
result=bytes(header)+b''.join(chunks);(OUT/'town.bmd').write_bytes(result)
verified=BMD(BytesIO(result));assert len(verified.shp1.shapes)==N;assert len(verified.tex1.textures)==N
manifest={'vertices':len(vs),'triangles':sum(map(len,groups.values())),'materials':N,'bounds_cm':[vs.min(0).tolist(),vs.max(0).tolist()],'model_bytes':len(result),'source':'BG/THR0000.IPD + THR0001.IPD + THR0002.IPD','status':'structurally parsed; gameplay validation pending'}
(OUT/'model_report.json').write_text(json.dumps(manifest,indent=2));np.savez(OUT/'town_collision_source.npz',vertices=vs,faces=np.array([[x[0] for x in f] for fs_ in groups.values() for f in fs_]))
print(json.dumps(manifest))
