from build123d import *
from OCP.BRep import BRep_Tool
import json
from pathlib import Path

def genus(s):
 v=len(s.vertices());all_e=list(s.edges());deg=sum(BRep_Tool.Degenerated_s(e.wrapped) for e in all_e);e=len(all_e)-deg
 faces=list(s.faces());holes=sum(max(0,len(f.wires())-1) for f in faces)
 chi=v-e+len(faces)-holes
 return {'V':v,'E':e,'degenerate_edges':deg,'F':len(faces),'inner_wires':holes,'chi':chi,'genus':(2-chi)/2,'shells':len(s.shells())}
for name,s in [('box',Box(10,10,10)),('sphere',Sphere(10)),('cylinder',Cylinder(10,10)),('ring',Cylinder(10,10)-Cylinder(5,12)),('blind',Box(30,30,30)-Pos(0,0,10)*Cylinder(5,15)),('torus',Torus(20,5))]:print(name,json.dumps(genus(s)))
for name in ['base','ears-bolt-blind-oil-deeppockets-v14','ears-bolt-through-oil-deeppockets-v15']:
 print(name,json.dumps(genus(import_step('/work/'+name+'.stp'))))
