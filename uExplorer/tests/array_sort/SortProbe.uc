class SortProbe extends SortBase;

struct Item
{
    var int Key;
};

struct Group
{
    var array<Item> Items;
};

var array<int> Numbers;
var array<string> Names;
var array<Group> Groups;
var int Counter;

delegate int CompareItems(Item A, Item B)
{
    return A.Key - B.Key;
}

delegate int CompareNames(string A, string B)
{
    return Len(A) - Len(B);
}

function int NextIndex()
{
    Counter++;
    return 0;
}

function SortAll()
{
    local array<int> LocalNumbers;
    local Group LocalGroup;
    Numbers.Sort(CompareInts);
    Names.Sort(CompareNames);
    LocalNumbers.Sort(CompareInts);
    LocalGroup.Items.Sort(CompareItems);
    Groups[NextIndex()].Items.Sort(CompareItems);
    Numbers.Insert(0, 1);
    Numbers.Remove(0, 1);
}
