class DefaultProbe extends Object;

var Color Tint;
var Plane Coefficients;
var Range Limits;
var RangeVector Bounds;
var Scale Transform;
var array<vector> Points;
var array<string> Labels;

struct NestedSettings
{
    var int Count;
    var bool Enabled;
    var Color Highlight;
    var Range Interval;
};
var NestedSettings Settings;

defaultproperties
{
    Tint=(R=17,G=33,B=65,A=129)
    Coefficients=(X=1.5,Y=-2.5,Z=3.5,W=4.5)
    Limits=(Min=-7.5,Max=12.5)
    Bounds=(X=(Min=1,Max=2),Y=(Min=3,Max=4),Z=(Min=5,Max=6))
    Transform=(Scale=(X=2,Y=3,Z=4),SheerRate=0.5,SheerAxis=SHEER_XY)
    Points(0)=(X=1,Y=2,Z=3)
    Points(1)=(X=-4,Y=-5,Z=-6)
    Labels(0)="first"
    Labels(1)="second"
    Settings=(Count=37,Enabled=True,Highlight=(R=3,G=5,B=7,A=11),Interval=(Min=0.5,Max=1.5))
}
