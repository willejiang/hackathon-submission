"""Rebuild only the actual upper pocket, starting from exact hole-corrected v5.

The entire actual flange outer-wire extrusion is restored, not a historical
source-derived pocket rectangle. The new R65 casting is clipped to that same
actual XY footprint and actual main-flange Y18..78 extent. The R61 inner
pocket Y24.75..64.75 stations are image-derived estimates (not explicit facts).
"""
from assess import *
C=(Align.CENTER,Align.CENTER,Align.CENTER)
s=import_step('/work/accepted745-main-bore-stations-v5.stp')
fs=[]
for f in s.faces():
 b=f.bounding_box()
 if f.geom_type==GeomType.PLANE and abs(b.min.Z-152.74)<1e-4 and abs(b.max.Z-152.74)<1e-4:fs.append(f)
f=max(fs,key=lambda f:f.area);outer_face=Face(f.outer_wire())
full_flange=extrude(outer_face,amount=-16.25)
s=s+full_flange
footprint=extrude(outer_face,amount=-(152.74-110.74))
outer=Pos(84.95,48,175.74)*Rot(90,0,0)*Cylinder(65,60,align=C)
outer=outer&footprint&Pos(81.125,47.575,(110.74+136.49)/2)*Box(170,100,136.49-110.74,align=C)
s=s+outer
inner=Pos(84.95,(24.75+64.75)/2,175.74)*Rot(90,0,0)*Cylinder(61,64.75-24.75,align=C)
s=s-inner
# Reapply exact upper bore inventory, preserving the already corrected lower
# passages and all original lower structures from v5.
for h in gt.facts['cylindrical_holes_and_bores']:
 for i,c in enumerate(h['centres']):
  if c[2]<110:continue
  l=h['lengths'][min(i,len(h['lengths'])-1)]
  if h['axis']=='Y':t=Pos(*c)*Rot(90,0,0)*Cylinder(h['diameter']/2,l,align=C)
  elif h['axis']=='Z':t=Pos(*c)*Cylinder(h['diameter']/2,l+.02,align=C)
  else:t=Plane(origin=c,z_dir=(-.29,-.66,.70))*Cylinder(h['diameter']/2,l,align=C)
  s=s-t
s=assess(s,'accepted745-actual-upper-bowl-v6')
a=import_step('/work/accepted745-main-bore-stations-v5.stp');slab=Pos(81.125,47.575,55)*Box(170,100,110,align=C)
aa=a&slab;bb=s&slab
r={'protected_z_max':110,'old_lower_volume':aa.volume,'new_lower_volume':bb.volume,'old_minus_new':(aa-bb).volume,'new_minus_old':(bb-aa).volume,'actual_old_pocket':{'x':[30,135],'y':[26,66],'floor_z':137.74},'restored_flange_z':[136.49,152.74],'outer_envelope':{'radius':65,'axis_xz':[84.95,175.74],'y':[18,78],'clipped_to':'exact largest actual top-face outer wire'},'inner_estimate':{'radius':61,'axis_xz':[84.95,175.74],'y':[24.75,64.75]}}
(W/'accepted745-actual-upper-bowl-v6-protected.json').write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True)
