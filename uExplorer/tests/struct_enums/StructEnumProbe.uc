class StructEnumProbe extends Object;

struct ScaleProbe
{
    var() enum EAxisProbe
    {
        AXIS_None,
        AXIS_X,
        AXIS_Y
    } Axis;
    var EAxisProbe OtherAxis;
};

var ScaleProbe Settings;

defaultproperties
{
    Settings=(Axis=AXIS_X,OtherAxis=AXIS_Y)
}
