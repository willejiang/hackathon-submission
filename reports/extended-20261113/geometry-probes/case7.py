"""Practice bracket: curved upper bowl, lug flange, tilted four-hole plate,
stepped main chamber and exact fact-sheet bores. Unspecified casting walls
are explicit estimates checked against the views, not volume-fitted cavities.
"""
from build123d import *
import math

def derive(facts):
    return {'facts':facts}

def cy(r,y0,y1,x,z):
    return Pos(x,(y0+y1)/2,z)*Rot(90,0,0)*Cylinder(r,y1-y0)
def cz(r,z0,z1,x,y):
    return Pos(x,y,(z0+z1)/2)*Cylinder(r,z1-z0)
def xz_extrude(prof,y0,y1):
    return Pos(0,y1,0)*Rot(90,0,0)*extrude(prof,amount=y1-y0)
def build(p):
    f=p['facts'];holes=f['cylindrical_holes_and_bores']; ztop=f['bounding_box_mm']['z']
    # Front mounting flange and its four peripheral lugs.
    flange=Pos(84.95,45.9,(ztop+136.49)/2)*Box(130.1,55.3,ztop-136.49)
    for x in (9.45,152.25):
        flange += cz(9.45 if x<80 else 10.0,113.79,ztop,x,32.05)
        nx=22.3 if x<80 else 147.5
        flange += Pos((x+nx)/2,32.05,(136.49+ztop)/2)*Box(abs(x-nx)+2,18.9,ztop-136.49)
    for x in (43.65,113.95):
        flange += cz(9.35,136.49,ztop,x,85.8)
        flange += Pos(x,78.9,(136.49+ztop)/2)*Box(18.7,13.8,ztop-136.49)
    # The visible concave upper bowl is a constant thickness circular section.
    outer=cy(65,18.25,73.55,84.95,175.74)
    outer &= Pos(84.95,45.9,76.37)*Box(130.1,55.3,152.74)
    body=flange+outer
    # Front boss and rear domed end are retained where they are outside the bowl.
    body += cy(17.05,0,78.1,84.95,135.69)
    body += Pos(84.95,78.1,135.69)*Sphere(17.05)
    # Lower mounting plate: rounded hull of its actual four fastener stations.
    pts=[(80.15,11.24),(133.25,37.69),(104.55,92.09),(52.75,62.89)]
    prof=offset(Polygon(*pts,align=None),amount=11.0,kind=Kind.ARC)
    plate=xz_extrude(prof,13.75,28.75)
    for x,z,r,back in [(52.75,62.89,12,37.75),(133.25,37.69,11,33.75),(80.15,11.24,11.24,28.75)]:
        plate += cy(r,13.75,back,x,z)
    body += plate
    # Central structural web and the back cylindrical chamber.
    neck=Polygon((68,86),(101,86),(101,121),(97,135.69),(72,135.69),(68,121),align=None)
    body += xz_extrude(neck,13.75,30.0)
    bridge=make_face([Line((48,84),(123,84)),
                      ThreePointArc((123,84),(125,112),(150,136.49)),
                      Line((150,136.49),(20,136.49)),
                      ThreePointArc((20,136.49),(45,112),(48,84))])
    # Two specified side ribs, leaving the visible central opening.
    inner_bridge=offset(bridge,amount=-8,kind=Kind.INTERSECTION)
    body += xz_extrude(bridge-inner_bridge,28.75,73.55)
    body += cy(36.75,27.0,76.55,85.65,64.39)
    # Open the bowl after all structural unions so it stays genuinely open.
    body -= cy(61,24.75,66.55,84.95,175.74)
    # Two visible front recesses: the shallow oval machining land and the
    # deeper kidney-shaped chamber leading into the upper stepped bore.
    recess_pts=[(85,88),(105,81),(119,66),(124,44),(122,25),(112,14),
                (97,13),(84,23),(73,41),(65,62),(68,78)]
    recess=make_face(Spline(*recess_pts,periodic=True))
    body -= xz_extrude(recess,13.70,16.25)
    kidney=make_face([
        ThreePointArc((85.65,80.14),(69.90,64.39),(85.65,48.64)),
        ThreePointArc((85.65,48.64),(90.5,47.2),(90.2,42.1)),
        ThreePointArc((90.2,42.1),(92.5,26.0),(105.0,25.0)),
        ThreePointArc((105.0,25.0),(113.5,35.0),(112.4,44.0)),
        ThreePointArc((112.4,44.0),(105.5,66.5),(94.5,77.4)),
        ThreePointArc((94.5,77.4),(90.0,79.7),(85.65,80.14))])
    body -= xz_extrude(kidney,16.20,21.25)
    # The measured adjacent cylindrical faces leave a 1 mm unreported
    # blend at the shoulder. Join those two known radii with a short taper.
    transition=loft([Pos(85.65,32.53,64.39)*Rot(90,0,0)*Circle(14.5),
                     Pos(85.65,33.57,64.39)*Rot(90,0,0)*Circle(30.0)])
    body -= transition
    # All exact cylindrical feature cutters come directly from facts.json.
    for h in holes:
        d=h['diameter']; axis=h['axis']; lens=h['lengths']
        for i,c in enumerate(h['centres']):
            length=lens[min(i,len(lens)-1)]
            if axis=='Y':
                cut=cy(d/2,c[1]-length/2-.02,c[1]+length/2+.02,c[0],c[2])
            elif axis=='Z':
                cut=cz(d/2,c[2]-length/2-.1,c[2]+length/2+.1,c[0],c[1])
            else:
                cut=Plane(origin=c,z_dir=(-.29,-.66,.70))*Cylinder(d/2,length+.1)
            body -= cut
    return body
