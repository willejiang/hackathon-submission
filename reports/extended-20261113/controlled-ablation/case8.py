"""One-factor comparison with v14: retain Z through-bores instead of blind stops.

All other geometry is identical: narrow mouths, four short ears, X blind stops,
rounded deep foot pockets, and corrected 30.2-mm vertical oil-passage position.
"""
from probe import *
s=import_step('/work/ears-bolt-mouths-v9.stp')
C=(Align.CENTER,Align.CENTER,Align.CENTER)
def pockets(s):
 for x in [3,77]:
  for z in [9,31.2]:
   t=Pos(x,7.5,z)*Box(8,9,13,align=C)
   s=s-fillet([e for e in t.edges() if abs(e.length-8)<1e-5],2)
 return s
s=pockets(s)
for x in [7.24,72.76]:
 s=s+Pos(x,6,2.505)*Cylinder(3.68,5.01,align=C)
 s=s-Pos(x,6.015,20.1)*Cylinder(2,30.2,align=C)
s=pockets(s)
# Same final cleanup of the 20-mm X bore as v14, although it is redundant here.
s=s-Pos(40,72.95,20.1)*Rot(0,90,0)*Cylinder(10,66,align=C)
assess(s,'ears-bolt-through-oil-deeppockets-v15')
