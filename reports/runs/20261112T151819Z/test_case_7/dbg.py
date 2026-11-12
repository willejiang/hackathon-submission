import json, sys
from build123d import *
import solution
facts = json.load(open('/Users/apple/Desktop/microsoft/research_space/hackathon-submission/artifacts/inputs/test_case_7/facts.json'))
p = solution.derive(facts)
s = solution.build(p)
bb = s.bounding_box()
print("bbox", bb.min, bb.max)
print("solids", len(s.solids()), "vol", s.volume)
for k in ("z","flange_bot","ylug_y","lug_yl","side_bot","mid_x"):
    print(k, p[k])
