class IndexedDefaults extends Object;

struct SettingsData
{
    var int Values[3];
    var int WideValues[130];
    var enum EMode
    {
        MODE_First,
        MODE_Second
    } Mode;
    var EMode Modes[2];
};

var SettingsData Settings;

defaultproperties
{
    Settings=(Values[0]=17,Values[1]=29,Values[2]=41,WideValues[129]=73,Mode=MODE_Second,Modes[0]=MODE_Second,Modes[1]=MODE_First)
}
