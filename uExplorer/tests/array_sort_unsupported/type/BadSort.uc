class BadSort extends Object;
var array<int> Items;
delegate int Compare(string A, string B) { return 0; }
function Run() { Items.Sort(Compare); }
