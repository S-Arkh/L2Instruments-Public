class GenerationProbe extends GenerationBase;

var GenerationProbe Other;

function int Handler(int A, int B)
{
    return A - B;
}

function int Exercise(GenerationProbe Target, class<GenerationProbe> Kind)
{
    local GenerationProbe Created;
    Compare = Handler;
    Target.Compare = Handler;
    Compare = Target.Handler;
    Compare(1, 2);
    Target.Compare(3, 4);
    Compare(5, 6);
    Compare = None;
    Created = new class'GenerationProbe';
    Created = new(Self) class'GenerationProbe';
    Created = new(None, "Detached", 0) class'GenerationProbe';
    Created = new(Self, "Created", 0) Kind;
    Created = new(new class'GenerationProbe') Kind;
    Other = Created;
    return Created.Handler(7, 8);
}

function int Nested(GenerationProbe Target)
{
    return Compare(Target.Compare(1, 2), Compare(3, 4));
}

function bool EnumArgument(GenerationProbe Target)
{
    return Target.Choose(Second);
}

function int DefaultCall()
{
    return DefaultValue(9);
}
