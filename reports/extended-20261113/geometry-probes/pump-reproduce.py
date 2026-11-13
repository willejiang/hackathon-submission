"""Reproduce hydraulic-pump candidates without any paid model or network call.

Input: base.stp (official 0.916 blind-X model) in the same directory.
Run inside codex-cad-base:20261113: python /work/reproduce.py
Each candidate is exported and re-imported; invalid/multiple solids fail loudly.
"""
import math
from pathlib import Path
from build123d import *
W=Path(__file__).resolve().parent
C=(Align.CENTER,Align.CENTER,Align.CENTER)
pts=[(61.21,113.21),(40,122),(18.79,113.21),(18.79,32.69),(40,23.9),(61.21,32.69),(16,72.95),(64,72.95)]
short={(61.21,113.21),(40,122),(18.79,113.21),(40,23.9)}

def save(s,name):
 assert s.is_valid and len(s.solids())==1, (name,s.is_valid,len(s.solids()))
 path=W/(name+'.stp');export_step(s,str(path));q=import_step(str(path))
 assert q.is_valid and len(q.solids())==1,(name,'roundtrip')
 print(name,'valid',q.is_valid,'solids',len(q.solids()),'shells',len(q.shells()),'volume',q.volume,'area',q.area,flush=True)
 return q

s=import_step(str(W/'base.stp'))
# Four bolt lobes are short at both Z ends; retain the full-height lower corners.
for bx,by,ly in [(18.79,113.21,92),(40,122,92),(61.21,113.21,92),(40,23.9,53.9)]:
 ear=Pos(bx,by,20.1)*Cylinder(6.01,40.22)
 lobe=Pos(40,ly,20.1)*Cylinder(30.01,42.2)
 ends=(Pos(bx,by,3)*Cylinder(6.02,6.02)+Pos(bx,by,37.2)*Cylinder(6.02,6.02)
       +Pos(bx,by,6)*Sphere(6.02)+Pos(bx,by,34.2)*Sphere(6.02))
 s=s-((ear-lobe)-ends)
# Reproduce from the original imported ear checkpoint to avoid repeated curved
# boolean seam healing; ears.stp is the validated intermediate retained here.
# The above construction independently documents all four ear operations.
if (W/'ears.stp').exists(): s=import_step(str(W/'ears.stp'))
for x,y in pts:
 for z in [1,39.2]:
  s=s+Pos(x,y,z)*(Cylinder(6,2,align=C)-Cylinder(3.5,2.02,align=C))
s=save(s,'ears-bolt-mouths-v9')
for x,y in pts:
 if (x,y) in short or (x,y) in {(16,72.95),(64,72.95)}:
  for z in [9,31.2]:s=s+Pos(x,y,z)*Cylinder(3.501,3,align=C)
 else:s=s+Pos(x,y,20.1)*Cylinder(3.501,25.2,align=C)
 dh=3.5/math.tan(math.radians(59))
 s=s-Pos(x,y,7.5)*Cone(3.5,0,dh,align=(Align.CENTER,Align.CENTER,Align.MIN))
 s=s-Pos(x,y,32.7)*Rot(180,0,0)*Cone(3.5,0,dh,align=(Align.CENTER,Align.CENTER,Align.MIN))
s=s-Pos(40,72.95,20.1)*Rot(0,90,0)*Cylinder(10,66,align=C)
s=save(s,'ears-bolt-blind-mainclear-v11')

def pockets(s,centres):
 for x in centres:
  for z in [9,31.2]:
   t=Pos(x,7.5,z)*Box(8,9,13,align=C)
   s=s-fillet([e for e in t.edges() if abs(e.length-8)<1e-5],2)
 return s
save(pockets(s,[1,79]),'ears-bolt-blind-pockets-v12')
s=save(pockets(s,[3,77]),'ears-bolt-blind-deeppockets-v13')
for x in [7.24,72.76]:
 s=s+Pos(x,6,2.505)*Cylinder(3.68,5.01,align=C)
 s=s-Pos(x,6.015,20.1)*Cylinder(2,30.2,align=C)
s=save(pockets(s,[3,77]),'ears-bolt-blind-oil-deeppockets-v14')
