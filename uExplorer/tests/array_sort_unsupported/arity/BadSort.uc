class BadSort extends Object;
var array<int> Items;
delegate int Compare(int A) { return 0; }
function Run() { Items.Sort(Compare); }
