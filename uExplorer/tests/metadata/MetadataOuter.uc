class MetadataOuter extends Object;

function vector Direction(rotator Rotation)
{
    return vector(Rotation);
}

function vector NestedDirection(rotator Rotation)
{
    return vector(rotator(vector(Rotation)));
}

function int InvokeNative(MetadataNative Target)
{
    return Target.NativeCall(3);
}
