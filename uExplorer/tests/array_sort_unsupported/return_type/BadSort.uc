class BadSort extends Object;
var array<int> Items;
delegate bool Compare(int A, int B) { return true; }
function Run() { Items.Sort(Compare); }
