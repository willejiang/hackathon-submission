"""Probe the two specified side Z drillings connecting to the X main bore.
Keep the opposite blind ends and all six perimeter bolt bores unchanged.
The text's through description and a two-handle B-rep deficit motivate this
limited connection hypothesis; genus agreement alone does not prove geometry.
"""
from probe import *
from OCP.BRep import BRep_Tool
s=import_step('/work/ears-bolt-blind-oil-deeppockets-v14.stp')
for x in [16,64]:
 s=s-Pos(x,72.95,30.2)*Cylinder(3.5,20.2,align=(Align.CENTER,Align.CENTER,Align.CENTER))
s=assess(s,'side-Z-main-connections-v16')
v=len(s.vertices());es=[e for e in s.edges() if not BRep_Tool.Degenerated_s(e.wrapped)];fs=list(s.faces());chi=v-len(es)+len(fs)-sum(max(0,len(f.wires())-1) for f in fs)
print('BREP_TOPOLOGY',{'chi':chi,'genus':(2-chi)/2},flush=True)
