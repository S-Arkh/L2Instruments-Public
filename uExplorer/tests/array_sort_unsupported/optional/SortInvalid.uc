class SortInvalid extends Object;
var array<int> Values;
delegate int Compare(optional int A, optional int B) { return A-B; }
function Test() { Values.Sort(Compare); }
