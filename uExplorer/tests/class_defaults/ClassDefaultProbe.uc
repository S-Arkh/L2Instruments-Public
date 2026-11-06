class ClassDefaultProbe extends Object;

var int Number;
var bool Enabled;

function int ReadDefault(class<ClassDefaultProbe> Kind)
{
    return Kind.default.Number;
}

function bool ReadBool(class<ClassDefaultProbe> Kind)
{
    return Kind.default.Enabled;
}

function int ReadConstantDefault()
{
    return Class'ClassDefaultProbe'.default.Number;
}

defaultproperties
{
    Number=37
    Enabled=True
}
