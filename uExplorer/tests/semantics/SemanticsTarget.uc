class SemanticsTarget extends Object dependson(SemanticsBase);
var int TargetStorage;
enum Choice { ForeignZero, ForeignOne, ForeignTwo };
struct ForeignData { var SemanticsBase.BaseData Data; };
function int Accept(SemanticsBase.Choice Value) { return int(Value)+10; }
