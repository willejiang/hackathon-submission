"""Export raw constructed geometry without loose-BSpline-bbox translation.

The valid trimmed loft faces have OCC parameter-rectangle bounds below the
true solid; raw mesh/vertex bounds remain the intended 0..165.1 mm frame.
"""
import sys,json,time
from pathlib import Path
sys.path.insert(0,'/app/src')
from build123d import *
import numpy as np
from OCP.BRep import BRep_Tool
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from agentic_cad import factsgen,raster,imagecmp
from agentic_cad.gt import load_case
W=Path('/work');CASE=Path('/app/artifacts/inputs/test_case_5');gt=load_case(CASE)
def brep_genus(s):
 if not s.is_valid or len(s.solids())!=1 or len(s.shells())!=1:return None
 es=[e for e in s.edges() if not BRep_Tool.Degenerated_s(e.wrapped)];fs=list(s.faces());iw=sum(max(0,len(f.wires())-1) for f in fs);chi=len(s.vertices())-len(es)+len(fs)-iw
 return (2-chi)//2 if chi<=2 and chi%2==0 else None
for name in sys.argv[1:]:
 t=time.time();ns={};exec(compile((W/(name+'.py')).read_text(),str(W/(name+'.py')),'exec'),ns);p=ns['derive'](gt.facts);s=ns['build'](p)
 path=W/(name+'_raw.stp');export_step(s,str(path));s=import_step(str(path));vs,ts=s.tessellate(.05,.1);xyz=np.array([tuple(v) for v in vs]);vb=np.array([tuple(v) for v in s.vertices()])
 f=factsgen.measure(s);rs=raster.render_all(s);ic=imagecmp.compare_all(CASE/'images',rs);ft={}
 for fa in s.faces():ft[fa.geom_type.name]=ft.get(fa.geom_type.name,0)+1
 bnd=Bnd_Box();BRepBndLib.AddOptimal_s(s.wrapped,bnd,False,False)
 row={'name':name+'_raw','valid':s.is_valid,'solids':len(s.solids()),'shells':len(s.shells()),'volume':s.volume,'V':s.volume/gt.volume,'area':s.area,'A':s.area/gt.surface_area,'genus_mesh':f.get('through_holes_genus'),'genus_brep':brep_genus(s),'face_types':ft,'mesh_min':xyz.min(0).tolist(),'mesh_max':xyz.max(0).tolist(),'mesh_extent':np.ptp(xyz,axis=0).tolist(),'vertex_min':vb.min(0).tolist(),'vertex_max':vb.max(0).tolist(),'bbox_loose':f['bounding_box_mm'],'OCC_AddOptimal_no_triangulation':[[bnd.CornerMin().X(),bnd.CornerMin().Y(),bnd.CornerMin().Z()],[bnd.CornerMax().X(),bnd.CornerMax().Y(),bnd.CornerMax().Z()]],'iou':ic.mean_iou,'views':ic.render(),'seconds':time.time()-t}
 (W/(name+'_raw.json')).write_text(json.dumps(row,indent=2));print(json.dumps(row),flush=True)
