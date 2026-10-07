"""CPU texture render of the exported geometry for conversion inspection.
This is an asset preview, not a screenshot of the running game.
"""
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
src=ROOT/'sh_tp_project/outdoor/source'; out=ROOT/'sh_tp_project/outdoor'
textures={}; material=None
for line in (src/'THR0001.MTL').read_text().splitlines():
    s=line.split()
    if not s:continue
    if s[0]=='newmtl':material=s[1]
    if s[0]=='map_Kd':textures[material]=np.array(Image.open(src/s[1]).convert('RGBA'))
v=[];uv=[];faces=[]
for line in (src/'THR0001.OBJ').read_text().splitlines():
    s=line.split()
    if not s:continue
    if s[0]=='v':v.append(list(map(float,s[1:])))
    elif s[0]=='vt':uv.append([float(s[1]),1-float(s[2])])
    elif s[0]=='usemtl':material=s[1]
    elif s[0]=='f':
        vs=[tuple(int(x)-1 if x else -1 for x in t.split('/')[:2]) for t in s[1:]]
        for i in range(1,len(vs)-1):faces.append(([vs[0],vs[i],vs[i+1]],material))
v=np.array(v);uv=np.array(uv);W,H=1000,760
eye=np.array([-43.,36.,23.]);target=np.array([-15.,0.,60.]);forward=target-eye;forward/=np.linalg.norm(forward)
right=np.cross(forward,[0,1,0]);right/=np.linalg.norm(right);up=np.cross(right,forward)
cam=(v-eye)@np.array([right,up,forward]).T
proj=np.stack([W/2+cam[:,0]/cam[:,2]*800,H/2-cam[:,1]/cam[:,2]*800],1)
canvas=np.full((H,W,4),[122,130,132,255],dtype=np.uint8);depth=np.full((H,W),np.inf)
for tri,mat in faces:
    ids=[a for a,b in tri];p=proj[ids];z=cam[ids,2]
    if z.min()<=0:continue
    lo=np.maximum(np.floor(p.min(0)).astype(int),[0,0]);hi=np.minimum(np.ceil(p.max(0)).astype(int),[W-1,H-1])
    if np.any(hi<lo):continue
    x,y=np.meshgrid(np.arange(lo[0],hi[0]+1)+.5,np.arange(lo[1],hi[1]+1)+.5)
    den=(p[1,1]-p[2,1])*(p[0,0]-p[2,0])+(p[2,0]-p[1,0])*(p[0,1]-p[2,1])
    if abs(den)<1e-7:continue
    a=((p[1,1]-p[2,1])*(x-p[2,0])+(p[2,0]-p[1,0])*(y-p[2,1]))/den
    b=((p[2,1]-p[0,1])*(x-p[2,0])+(p[0,0]-p[2,0])*(y-p[2,1]))/den
    c=1-a-b;iz=a/z[0]+b/z[1]+c/z[2];dist=1/np.maximum(iz,1e-10)
    region=depth[lo[1]:hi[1]+1,lo[0]:hi[0]+1];mask=(a>=0)&(b>=0)&(c>=0)&(dist<region)
    if not np.any(mask):continue
    color=np.full((*mask.shape,4),[90,88,80,255],dtype=np.uint8)
    if mat in textures and all(t[1]>=0 for t in tri):
        t=uv[[t[1] for t in tri]];tex=textures[mat]
        u=(a*t[0,0]/z[0]+b*t[1,0]/z[1]+c*t[2,0]/z[2])*dist
        w=(a*t[0,1]/z[0]+b*t[1,1]/z[1]+c*t[2,1]/z[2])*dist
        color=tex[np.clip((w*len(tex)).astype(int),0,len(tex)-1),np.clip((u*tex.shape[1]).astype(int),0,tex.shape[1]-1)]
        mask &= color[:,:,3]>=128
    region[mask]=dist[mask];canvas[lo[1]:hi[1]+1,lo[0]:hi[0]+1][mask]=color[mask]
out.mkdir(exist_ok=True,parents=True)
Image.fromarray(canvas).convert('RGB').save(out/'street-asset-preview.png')
print(out/'street-asset-preview.png')
