class CallScopeCaller extends Object;

enum Category { FirstCategory, SecondCategory };
var CallScopeReceiver Target;
var int Index;
var byte RawCategory;
struct RawData { var byte Value; };
var RawData Data;
var array<byte> Values;
var EnumCastSource EnumSource;
var Category CurrentCategory;

function byte RawValue() { return RawCategory; }

function Category Converted()
{
    return Category(Data.Value);
}

function string Describe(Category Value)
{
    return "caller";
}

function Run()
{
    Target.Consume(Describe(Category(Index)));
    Target.Consume(Describe(Category(RawCategory)));
    Target.Consume(Describe(Category(Data.Value)));
    Target.Consume(Describe(Category(Values[Index])));
    Target.Consume(Describe(Category(RawValue())));
    CurrentCategory = Category(EnumSource.Value);
    Target.Consume(Describe(Category(EnumSource.Value)));
}
