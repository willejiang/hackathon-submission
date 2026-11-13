import json,sys
from pathlib import Path
sys.path.insert(0,'/app/src')
from build123d import *
from agentic_cad import cad,factsgen,raster,imagecmp
from agentic_cad.gt import load_case
import numpy as np
from PIL import Image
W=Path('/work');CASE=Path('/case');gt=load_case(CASE)
def assess(s,n):
 export_step(s,str(W/(n+'.stp')));s=import_step(str(W/(n+'.stp')))
 f=factsgen.measure(s);rs=raster.render_all(s);ic=imagecmp.compare_all(CASE/'images',rs)
 out=dict(name=n,valid=s.is_valid,solids=len(s.solids()),shells=len(s.shells()),volume=s.volume,V=s.volume/gt.volume,area=s.area,A=s.area/gt.surface_area,genus=f['through_holes_genus'],iou=ic.mean_iou,views=ic.render(),bbox=f['bounding_box_mm'])
 (W/(n+'.json')).write_text(json.dumps(out,indent=2));print(json.dumps(out),flush=True)
 for stem in ['view_0_front','view_2_left','view_4_top','view_6_iso_front_right_top']:
  ref=imagecmp.normalise(imagecmp.reference_mask(CASE/'images'/(stem+'.png')));out=imagecmp.normalise(rs[stem]);rgb=np.ones((*ref.shape,3),dtype=np.uint8)*255;rgb[ref&out]=[120]*3;rgb[ref&~out]=[20,170,20];rgb[out&~ref]=[220,50,50];Image.fromarray(rgb).save(W/(n+'-'+stem+'.png'))
 return s
if __name__=='__main__':
 for n in sys.argv[1:]:assess(import_step(str(W/(n+'.stp'))),n)
