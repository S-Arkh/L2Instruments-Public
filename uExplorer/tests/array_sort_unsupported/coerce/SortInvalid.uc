class SortInvalid extends Object;
var array<int> Values;
delegate int Compare(coerce int A, coerce int B) { return A-B; }
function Test() { Values.Sort(Compare); }
