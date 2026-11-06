class PointerProbe extends Object;

var int Before;
var native pointer Handle, OtherHandle;
var byte After;
var transient pointer AnimationData;
const HandleCount = 3;
var native pointer Handles[HandleCount], TrailingHandle;
var transient pointer Animations[2];

struct NativeData
{
    var native pointer InnerHandle;
    var int Count;
    var transient pointer LinkedAnimationData;
    var native pointer InnerHandles[2];
};

var NativeData Data;

function int ReadCount()
{
    return Data.Count + Before;
}

function CopyPointers()
{
    local PointerProbe Source;
    Source = Self;
    OtherHandle = Source.Handle;
    Handles[1] = Handle;
    Data.InnerHandle = Handles[1];
    CopyParameter(ReturnPointer(Data.InnerHandle), AnimationData);
}

function CopyParameter(pointer Value, out pointer Destination)
{
    local pointer Saved;
    Saved = Value;
    Destination = Saved;
}

function pointer ReturnPointer(pointer Value)
{
    return Value;
}

function ClearPointers()
{
    local pointer Empty;
    OtherHandle = Empty;
    Handles[1] = 0;
    CopyParameter(0, Data.InnerHandle);
    AnimationData = ReturnPointer(0);
}

function bool EqualPointers()
{
    return PointerEqual(Handle, OtherHandle) && PointerEqual(Handles[1], Data.InnerHandle);
}

function bool NullPointers()
{
    local PointerProbe Missing;
    return PointerEqual(OtherHandle, 0) && PointerEqual(Handles[1], 0)
        && PointerEqual(Data.InnerHandle, 0) && PointerEqual(AnimationData, 0)
        && PointerEqual(Missing.Handle, 0);
}

defaultproperties
{
    Handle=0
    AnimationData=0
    Handles(0)=0
    Handles(2)=0
    Animations(1)=0
    Data=(InnerHandle=0,Count=7,LinkedAnimationData=0,InnerHandles[1]=0)
}
