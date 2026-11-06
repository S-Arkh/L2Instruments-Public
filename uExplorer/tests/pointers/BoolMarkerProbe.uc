class BoolMarkerProbe extends Object;

function bool Identity(bool Value)
{
    return Value;
}

function bool Check(int Value)
{
    local INT64 Wide;
    Wide = INT64(Value);
    return (Identity(true) == true) && (Identity(false) == false);
}

function bool CheckPointer(pointer A, pointer B)
{
    return (PointerEqual(A, B) == true) && (Identity(false) == false);
}
