class BadSort extends Object;
var array<int> Items;
function int Compare(int A, int B) { return 0; }
function Run() { Items.Sort(Compare); }
