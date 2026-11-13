from assess import *
s=import_step('/work/accepted745.stp')
# Both exact Y-facing references show a gold disk in the upper horizontal bore;
# the accepted model leaves a large background-white crescent through its rear
# sphere. A 3-mm stop at the rear end stays within the existing cylindrical
# boss envelope, preserving the front counterbores and long axial passage.
stop=Pos(84.95,82.5,135.69)*Rot(90,0,0)*Cylinder(8.76,3,align=(Align.CENTER,Align.CENTER,Align.CENTER))
assess(s+stop,'accepted745-dome-stop-v1')
