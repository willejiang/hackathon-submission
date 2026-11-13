import json,time
from pathlib import Path
from agentic_cad import cad, factsgen, imagecmp, raster
from agentic_cad.gt import load_case
root=Path('/evaluation');mapping=json.loads((root/'mapping.json').read_text());rows=[]
for name,part_name in mapping.items():
 p=root/'out'/(name+'.stp');r={'case':name,'part':part_name,'exists':p.is_file()}
 if p.is_file():
  try:
   shape=cad.reopen_step(p);gt=load_case(root/'truth'/name);f=factsgen.measure(shape);im=imagecmp.compare_all(root/'truth'/name/'images',raster.render_all(shape))
   r.update(valid=shape.is_valid,solids=len(shape.solids()),volume_ratio=shape.volume/gt.volume,area_ratio=shape.area/gt.surface_area,genus=f.get('through_holes_genus'),bbox=f['bounding_box_mm'],iou=im.mean_iou)
  except Exception as e:r['error']=type(e).__name__+': '+str(e)[:200]
 rows.append(r);print(json.dumps(r),flush=True)
(root/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
