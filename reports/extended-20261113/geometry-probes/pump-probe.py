import sys,json
sys.path.insert(0,'/app/src')
from pathlib import Path
from build123d import *
from agentic_cad import cad,factsgen,imagecmp,raster
from agentic_cad.gt import load_case
import numpy as np
from PIL import Image
W=Path('/work'); gt=load_case(Path('/case'))
def assess(s,n):
 s=cad._normalise(s);export_step(s,str(W/(n+'.stp')));s=import_step(str(W/(n+'.stp')))
 f=factsgen.measure(s); rs=raster.render_all(s);ic=imagecmp.compare_all(Path('/case/images'),rs)
 out=dict(name=n,valid=s.is_valid,solids=len(s.solids()),shells=len(s.shells()),volume=s.volume,V=s.volume/121458.5,area=s.area,A=s.area/38901.1,genus=f['through_holes_genus'],iou=ic.mean_iou,views=ic.render(),bbox=f['bounding_box_mm'])
 (W/(n+'.json')).write_text(json.dumps(out,indent=2));print(json.dumps(out),flush=True)
 for stem in ['view_4_top','view_2_left','view_6_iso_front_right_top']:
  ref=imagecmp.normalise(imagecmp.reference_mask(Path('/case/images')/(stem+'.png')));out=imagecmp.normalise(rs[stem]);rgb=np.ones((*ref.shape,3),dtype=np.uint8)*255;rgb[ref&out]=[120]*3;rgb[ref&~out]=[20,170,20];rgb[out&~ref]=[220,50,50];Image.fromarray(rgb).save(W/(n+'-'+stem+'.png'))
 return s
if __name__=='__main__':
 s=import_step('/work/ears.stp')
 for i,e in enumerate(s.edges()):
  c=e.center();b=e.bounding_box()
  if c.Y<12 and (c.X<12 or c.X>68):print(i,e.geom_type.name,round(e.length,2),str(c),str(b.min),str(b.max))
 f=s
 for x in [-3.5,83.5]: f=f-Pos(x,25.5,20.1)*Cylinder(18,42.2)
 assess(f,'ears-feet-R18-v5')
