"""Conservative hybrid: retain accepted lower structure and flange outline;
replace only its shallow upper pocket with the image-supported deep R61 bowl.
"""
from assess import *
C=(Align.CENTER,Align.CENTER,Align.CENTER)
s=import_step('/work/accepted745.stp')
# Exact accepted planar flange outer wire, without its pocket/hole inner wires.
# The largest upward planar face at the maximum Z is the mounting flange.
fs=[]
for f in s.faces():
 b=f.bounding_box()
 if f.geom_type==GeomType.PLANE and abs(b.min.Z-152.74)<1e-4 and abs(b.max.Z-152.74)<1e-4:
  fs.append(f)
f=max(fs,key=lambda f:f.area)
full_flange=extrude(Face(f.outer_wire()),amount=-16.25)
# Restore only the old shallow rectangular pocket void before recutting it.
old_pocket=Pos((32.05+133.26)/2,(15.75+73.55)/2,(143.24+152.74)/2)*Box(133.26-32.05,73.55-15.75,152.74-143.24,align=C)
s=s+(full_flange&old_pocket)
# Add the curved casting under the existing flange, keeping all existing lug
# and upper flange outside boundaries. Lowest new material is Z=110.74.
outer=Pos(84.95,(18.25+73.55)/2,175.74)*Rot(90,0,0)*Cylinder(65,73.55-18.25,align=C)
outer=outer&Pos(81.125,47.575,(110.74+136.49)/2)*Box(162.25,95.15,136.49-110.74,align=C)
s=s+outer
# The measured concave partial cylinder is R61, matching the open bowl in the
# reference; its front/back wall stations come from the prior image study.
inner=Pos(84.95,(24.75+66.55)/2,175.74)*Rot(90,0,0)*Cylinder(61,66.55-24.75,align=C)
s=s-inner
# Preserve the exact measured cylindrical passages on the new/reconstituted
# upper material; no cuts or modifications reach the lower accepted structure.
for h in gt.facts['cylindrical_holes_and_bores']:
 for i,c in enumerate(h['centres']):
  if c[2]<110:continue
  l=h['lengths'][min(i,len(h['lengths'])-1)]
  if h['axis']=='Y':t=Pos(*c)*Rot(90,0,0)*Cylinder(h['diameter']/2,l,align=C)
  elif h['axis']=='Z':t=Pos(*c)*Cylinder(h['diameter']/2,l+.02,align=C)
  else:t=Plane(origin=c,z_dir=(-.29,-.66,.70))*Cylinder(h['diameter']/2,l,align=C)
  s=s-t
s=assess(s,'accepted745-upper-bowl-v2')
# Boolean equality in the protected lower slab is checked independently.
a=import_step('/work/accepted745.stp')
slab=Pos(81.125,47.575,55)*Box(170,100,110,align=C)
a=a&slab;b=s&slab
r={'protected_z_max':110.0,'old_lower_volume':a.volume,'new_lower_volume':b.volume,'old_minus_new':(a-b).volume,'new_minus_old':(b-a).volume}
(W/'accepted745-upper-bowl-v2-protected.json').write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True)
