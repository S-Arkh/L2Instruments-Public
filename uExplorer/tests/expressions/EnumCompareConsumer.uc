class EnumCompareConsumer extends Object dependson(EnumCompareOwner);

function bool Leading(EnumCompareOwner.CompareChoice Value)
{
    return CompareChoice(0) <= Value;
}

function bool Trailing(EnumCompareOwner.CompareChoice Value)
{
    return Value <= CompareSecond;
}

function bool ExplicitByte(EnumCompareOwner.CompareChoice Value)
{
    return byte(0) <= Value;
}
