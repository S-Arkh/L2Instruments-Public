class SortInvalid extends Object;
var array<int> Values;
delegate int Compare(int A, int B) { return A-B; }
function int Test() { return Values.Sort(Compare); }
