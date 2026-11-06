class BadSort extends Object;
delegate int Compare(int A, int B) { return 0; }
static function Run()
{
    local array<int> Items;
    Items.Sort(Compare);
}
