"""Correct the measured upper horizontal bore stations, preserving exterior.

All fill material is confined to voids measured directly in the accepted STEP:
D28 Y0..2, D26 Y9..11, and D21 Y84..86. These lie within the existing front
R21 or middle R17.05 outer cylinders. Re-cut stations come directly from facts.
"""
from assess import *
C=(Align.CENTER,Align.CENTER,Align.CENTER)
s=import_step('/work/accepted745.stp')
def cy(r,y0,y1):return Pos(84.95,(y0+y1)/2,135.69)*Rot(90,0,0)*Cylinder(r,y1-y0,align=C)
# Restore only the portions of the old, incorrectly stationed bore voids that
# must be solid. 0.01 radial overlap bonds the restoration to existing walls.
s=s+(cy(14.01,0,2)-cy(13,0,2))
s=s+(cy(13.01,9,11)-cy(8.75,9,11))
s=s+cy(10.51,84,86)
# Correct mouth, retaining groove, long bore and forward internal groove.
for r,y0,y1 in [(13,0,9),(14,2,4),(8.75,9,84),(10.5,22.8,24.8)]:s=s-cy(r,y0,y1)
# The inclined D4.5 drilling is completely absent from the accepted artifact.
c=(80.96,84.6,146.58)
s=s-Plane(origin=c,z_dir=(-.29,-.66,.70))*Cylinder(2.25,22.32,align=C)
s=assess(s,'accepted745-upper-bore-stations-v4')
# Verify the exterior-preserving requirement by checking that every added point
# is within measured old-hole void tools rather than arbitrary envelope solids.
a=import_step('/work/accepted745.stp')
added=s-a;removed=a-s
allowed=cy(14.01,0,2)+cy(13.01,9,11)+cy(10.51,84,86)
r={'added_volume':added.volume,'removed_volume':removed.volume,'added_outside_old_hole_tools':(added-allowed).volume,'protected_below_z_110':None}
slab=Pos(81.125,47.575,55)*Box(170,100,110,align=C);aa=a&slab;bb=s&slab
r['protected_below_z_110']={'old_minus_new':(aa-bb).volume,'new_minus_old':(bb-aa).volume}
(W/'accepted745-upper-bore-stations-v4-protected.json').write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True)
