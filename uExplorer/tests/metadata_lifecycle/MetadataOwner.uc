class MetadataOwner extends Object;
var InlineValue Inline;
var InlineValue Fixed[2];
var array<InlineValue> Dynamic;
var PlainValue Plain;
function Accept(out InlineValue Value, out PlainValue Control)
{
    Value = Inline;
    Control = Plain;
}
