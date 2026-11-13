"""Reposition the accepted main stepped bore without changing its outer shell.

The R1 front shoulder and R1 rear mouth account for the one-mm difference
between cylindrical-face stations and the retained Y77.55 rear outer face.
"""
from assess import *
C=(Align.CENTER,Align.CENTER,Align.CENTER)
s=import_step('/work/accepted745-upper-bore-stations-v4.stp')
def cy(r,y0,y1,x=85.65,z=64.39):return Pos(x,(y0+y1)/2,z)*Rot(90,0,0)*Cylinder(r,y1-y0,align=C)
old_void=cy(30.001,32.55,66.55)+cy(32.501,66.55,75.55)+cy(34.251,75.55,77.55)
s=s+old_void
# Large bore front shoulder has a rounded cutter edge. Its front disk is R29
# at Y32.55 and its R30 cylindrical wall starts at Y33.55, exactly as facts.
t60=cy(30,32.55,67.55)
front=[e for e in t60.edges() if e.geom_type==GeomType.CIRCLE and abs(e.center().Y-32.55)<1e-5]
assert len(front)==1
s=s-fillet(front,1)
# Keep the rear passage open through the existing outer plane, then round
# the material mouth so the true R32.5 cylinder ends one mm before that plane.
s=s-cy(32.5,67.55,77.65)
s=s-cy(34.25,72.55,74.55)
# Preserve the left small drilling that intersects the main hole restoration.
s=s-cy(4.25,13.75,37.75,x=52.75,z=62.89)
# The old R14.5 entry remains unchanged and connects to the R29 shoulder disk.
s=s-cy(14.5,21.25,32.55)
# Identify the exact rear circular edge from its plane and radius.
rear=[]
for e in s.edges():
 if e.geom_type!=GeomType.CIRCLE:continue
 b=e.bounding_box()
 if abs(b.min.Y-77.55)<1e-4 and abs(b.max.Y-77.55)<1e-4:
  try:
   if abs(e.radius-32.5)<1e-4:rear.append(e)
  except:pass
assert len(rear)==1,[(e.geom_type.name,str(e.bounding_box())) for e in rear]
s=fillet(rear,1)
s=assess(s,'accepted745-main-bore-stations-v5')
a=import_step('/work/accepted745-upper-bore-stations-v4.stp')
added=s-a;removed=a-s
r={'added_volume':added.volume,'removed_volume':removed.volume,'added_outside_old_void':(added-old_void).volume,'outer_rear_y':77.55,'front_transition':'R1 round, Y32.55 R29 disk to Y33.55 R30 cylinder','rear_transition':'R1 material mouth, R32.5 cylinder to Y76.55; opening at Y77.55'}
# Exact point checks on the shared axis verify that no new solid cap blocks
# the passage from front entry Y13.75 to the retained rear opening Y77.55.
axis_points=[(85.65,y,64.39) for y in [13.76,17.5,21.24,21.26,32.54,32.56,33.54,33.56,67.54,67.56,72.54,72.56,74.54,74.56,76.54,76.56,77.54]]
q=s.solids()[0];r['axis_inside_material']=[bool(q.is_inside(p)) for p in axis_points];assert not any(r['axis_inside_material'])
(W/'accepted745-main-bore-stations-v5-protected.json').write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True)
