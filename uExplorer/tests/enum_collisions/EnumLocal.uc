class EnumLocal extends Object dependson(EnumForeign);
enum Choice { LocalFirst, LocalSecond };
var EnumForeign Other;
var Choice Value;
function Choice Convert()
{
    return Choice(Other.Value);
}
function Assign()
{
    Value = Choice(Other.Value);
}
