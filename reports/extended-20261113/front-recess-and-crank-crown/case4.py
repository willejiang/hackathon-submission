"""Probe the specified R169 convex web crowns between the journal axes.
The chord is the stated 63.5-mm throw; its midpoint establishes the arc centre.
No bore, shaft, pin, or overall dimension is rescaled to fit total volume.
"""
import math,sys
from pathlib import Path
sys.path.insert(0,'/app/src')
from build123d import *
from agentic_cad import factsgen,raster,imagecmp
import json
p=Path('/work');s=import_step(str(p/'original_r254.stp'))
axis=(105.79,114.3);pins=[(105.79,50.8,136.48),(50.8,146.05,282.44),(160.79,146.05,428.4)]
faces=[]
for f in s.faces():
 b=f.bounding_box()
 if f.geom_type==GeomType.PLANE and b.size.Z<1e-5 and 80<b.min.Z<485 and f.area>1500:
  z=b.min.Z;sign=1 if f.normal_at().Z>0 else -1
  print('FACE',round(z,4),round(f.area,2),sign,flush=True)
  faces.append((f,z,sign))
R=169.0
for f,z,sign in faces:
 x,y,zc=min(pins,key=lambda c:abs(c[2]-z))
 dx,dy=x-axis[0],y-axis[1];length=math.hypot(dx,dy);ux,uy=dx/length,dy/length
 half=length/2; cz=z-sign*math.sqrt(R*R-half*half)
 pad=extrude(f,amount=3.1,dir=(0,0,sign))
 cyl=Plane(origin=((x+axis[0])/2,(y+axis[1])/2,cz),z_dir=(-uy,ux,0))*Cylinder(R,500)
 cap=pad&cyl
 if cap.volume>1e-5:s=s+cap
export_step(s,str(p/'original_r254_crown169.stp'));s=import_step(str(p/'original_r254_crown169.stp'))
f=factsgen.measure(s);im=imagecmp.compare_all(Path('/case/images'),raster.render_all(s))
r=dict(valid=s.is_valid,solids=len(s.solids()),volume=s.volume,area=s.area,bbox=f['bounding_box_mm'],genus=f['through_holes_genus'],face_types=f['face_types'],iou=im.mean_iou,views=im.render())
(p/'original_r254_crown169.json').write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True)
