class BadSort extends Object;
var array<int> Items;
delegate int Compare(out int A, int B) { return 0; }
function Run() { Items.Sort(Compare); }
