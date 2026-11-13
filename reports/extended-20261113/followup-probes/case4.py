import sys,json,time
from pathlib import Path
sys.path.insert(0,'/app/src')
from agentic_cad import cad
from build123d import fillet,export_step
p=Path('/work');t=time.time();s=cad.reopen_step(p/'original.stp')
# Keep the two free-end journal faces sharp, as in both isometric references.
es=[e for e in s.edges() if not ((abs(e.bounding_box().min.Z)<1e-4 and abs(e.bounding_box().max.Z)<1e-4) or (abs(e.bounding_box().min.Z-564.88)<1e-4 and abs(e.bounding_box().max.Z-564.88)<1e-4))]
print('filleting',len(es),'of',len(s.edges()),flush=True)
s=fillet(es,2.54)
export_step(s,str(p/'original_r254.stp'));print(json.dumps({'valid':s.is_valid,'solids':len(s.solids()),'volume':s.volume,'area':s.area,'faces':len(s.faces()),'seconds':time.time()-t}))
