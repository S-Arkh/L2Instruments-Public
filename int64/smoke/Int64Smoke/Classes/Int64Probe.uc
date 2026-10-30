class Int64Probe extends Object;

const BigConstant = 5000000000;
var int64 Amount;
var int64 FixedValues[2];
var array<int64> Values;

function int64 Widen(int Value)
{
    return Value;
}

function int64 ParseValue(string Text)
{
    return int64(Text);
}

function string FormatValue(int64 Value)
{
    return string(Value);
}

function int64 LargeLiteral()
{
    return 5000000000;
}

function int64 Minimum()
{
    return -9223372036854775808;
}

function int64 Maximum()
{
    return 9223372036854775807;
}

function int64 NamedConstant()
{
    return BigConstant;
}

function int64 Nested(int Value)
{
    return int64(int64(Value + 1) + 5000000000);
}

function float MixedFloat(int64 Value, float Scale)
{
    return Value + Scale;
}

function int LegacyMask()
{
    return 0xffffffff;
}

function byte ByteArithmetic(int Value)
{
    return 255 - Value;
}

function int IntArithmetic(byte Value, int Other)
{
    return Value + Other;
}

function int64 MixedByte(byte Value, int64 Other)
{
    return Value + Other;
}

function int64 Arithmetic(int64 A, int B)
{
    local int64 Result;

    Result = A + B;
    Result += 5;
    Result -= 1;
    if (Result > 0)
        return Result * 2;
    return 0;
}

function int Narrow(int64 Value)
{
    return int(Value);
}

function TestArrays(int Value)
{
    Values.Length = 2;
    Values[0] = Value;
    FixedValues[1] = 5000000000;
    Amount = Values[0] + FixedValues[1];
}

// Call in the CLIENT, not in the old compiler runtime, after loading the .u.
function bool VerifyRuntime()
{
    return LargeLiteral() == ParseValue("5000000000")
        && FormatValue(Minimum()) == "-9223372036854775808"
        && FormatValue(Maximum()) == "9223372036854775807"
        && Widen(-1) == ParseValue("-1")
        && Arithmetic(ParseValue("5000000000"), 1) == ParseValue("10000000010")
        && NamedConstant() == LargeLiteral();
}

defaultproperties
{
    Amount=5000000000
    FixedValues(0)=-1
    FixedValues(1)=9223372036854775807
}
