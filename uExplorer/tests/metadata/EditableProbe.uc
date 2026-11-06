class EditableProbe extends Object;

var() int DefaultCategory;
var(Settings) string NamedCategory;
var(Settings) const int ReadOnlyValue;

struct EditableData
{
    var() int Value;
};
var(Settings) EditableData Data;
