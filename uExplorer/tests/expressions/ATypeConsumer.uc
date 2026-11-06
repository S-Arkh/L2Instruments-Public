class ATypeConsumer extends Actor dependson(ZTypeBase) dependson(ZTypeOwner);

var ZTypeOwner.Payload Data;
var ZTypeOwner.Choice Selected;

function int Read(ZTypeOwner.Payload Input)
{
    local ZTypeOwner.Payload Copy;
    Copy = Input;
    return Copy.Value;
}

function int Select()
{
    local ZTypeOwner Target;
    local int Result;
    foreach AllActors(class'ZTypeOwner', Target)
    {
        switch (Target.GetChoice())
        {
            case Second:
                Result = 1;
                break;
            default:
                Result = 0;
                break;
        }
    }
    return Result;
}
