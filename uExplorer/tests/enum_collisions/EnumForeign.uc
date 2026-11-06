class EnumForeign extends Object;
enum Choice { ForeignFirst, ForeignSecond };
var Choice Value;
function Choice ConvertByte(byte Raw)
{
    return Choice(Raw);
}
