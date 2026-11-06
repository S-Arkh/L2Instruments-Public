class BadSort extends Object;
var const array<int> Items;
delegate int Compare(int A, int B) { return 0; }
function Run() { Items.Sort(Compare); }
