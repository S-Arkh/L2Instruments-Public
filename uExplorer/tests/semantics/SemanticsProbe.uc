class SemanticsProbe extends SemanticsBase dependson(SemanticsTarget);
var int Calls;
var SemanticsTarget Target;
var SemanticsTarget.ForeignData Stored;

function SemanticsProbe Receiver()
{
    Calls++;
    return Self;
}

function int Contexts(int Input)
{
    local int Result;
    Calls=0;
    Result=Receiver().Zero + Receiver().One;
    if (Receiver().Enabled && Receiver().Fraction == 1.5 && Receiver().Label == 'Ready') Result+=10;
    return Result+Calls*100;
}

function int Lexical(int Input)
{
    Target=new class'SemanticsTarget';
    Stored.Data.Value=Target.Accept(Choice(Input));
    return Stored.Data.Value;
}

function int Flow(int Input)
{
    local int I, Result;
    Result=7;
    for (I=0; I<Input; I++)
    {
        if (I==2) continue;
        switch (I)
        {
            case 0: Result+=3; break;
            case 1: Result*=2; break;
            case 4: Result-=5; break;
            default: Result+=I;
        }
        if (Result>40) break;
    }
    while (Result>30) Result-=4;
    return Result;
}
