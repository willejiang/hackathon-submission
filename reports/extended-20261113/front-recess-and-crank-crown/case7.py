"""Image-evidenced shallow machining recess and kidney perimeter groove.

Uses accepted 0.745 solid directly; it changes no exterior outline, web, ribs,
flange, rear hub or stepped main bore. A retained kidney land preserves the
S-shaped solid and main-bore shoulder; this is not a through-opening cut.
"""
from assess import *

def xz_extrude(prof,y0,y1):
 return Pos(0,y1,0)*Rot(90,0,0)*extrude(prof,amount=y1-y0)

s=import_step('/work/accepted745.stp')
recess_pts=[(85,88),(105,81),(119,66),(124,44),(122,25),(112,14),
            (97,13),(84,23),(73,41),(65,62),(68,78)]
recess=make_face(Spline(*recess_pts,periodic=True))
s=s-xz_extrude(recess,13.70,16.25)
kidney=make_face([
 ThreePointArc((85.65,80.14),(69.90,64.39),(85.65,48.64)),
 ThreePointArc((85.65,48.64),(90.5,47.2),(90.2,42.1)),
 ThreePointArc((90.2,42.1),(92.5,26.0),(105.0,25.0)),
 ThreePointArc((105.0,25.0),(113.5,35.0),(112.4,44.0)),
 ThreePointArc((112.4,44.0),(105.5,66.5),(94.5,77.4)),
 ThreePointArc((94.5,77.4),(90.0,79.7),(85.65,80.14))])
land=offset(kidney,amount=-2.5,kind=Kind.ARC)
s=s-xz_extrude(kidney-land,16.20,21.25)
s=assess(s,'accepted745-front-grooves-v3')
# A protected rear half-space contains the entire old stepped hub and rib/web
# material behind the limited front machining depth.
a=import_step('/work/accepted745.stp')
slab=Pos(81.125,(21.3+95.15)/2,76.37)*Box(170,95.15-21.3,160,align=(Align.CENTER,Align.CENTER,Align.CENTER))
a=a&slab;b=s&slab
r={'protected_y_min':21.3,'old_protected_volume':a.volume,'new_protected_volume':b.volume,'old_minus_new':(a-b).volume,'new_minus_old':(b-a).volume}
(W/'accepted745-front-grooves-v3-protected.json').write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True)
