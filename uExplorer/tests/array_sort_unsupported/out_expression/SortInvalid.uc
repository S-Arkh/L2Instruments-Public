class SortInvalid extends Object;
var array<int> Values;
delegate int Compare(int A, int B) { return A-B; }
function Accept(out int Value) {}
function Test() { Accept(Values.Sort(Compare)); }
