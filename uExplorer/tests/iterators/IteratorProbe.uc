class IteratorProbe extends Actor;

function int CountActors()
{
    local Actor Item;
    local int Count;
    foreach AllActors(class'Actor', Item)
        Count++;
    return Count;
}

function int FilterActors()
{
    local Actor Item;
    local int Count;
    foreach AllActors(class'Actor', Item)
    {
        if (Item == Self)
            continue;
        Count++;
        if (Count > 3)
            break;
    }
    return Count;
}

function Actor FirstOther()
{
    local Actor Item;
    foreach AllActors(class'Actor', Item)
        if (Item != Self)
            return Item;
    return None;
}

function int CountPairs()
{
    local Actor Left, Right;
    local int Count;
    foreach AllActors(class'Actor', Left)
        foreach AllActors(class'Actor', Right)
            if (Left != Right)
                Count++;
    return Count;
}

function Actor FirstPair()
{
    local Actor Left, Right;
    foreach AllActors(class'Actor', Left)
        foreach AllActors(class'Actor', Right)
            if (Left != Right)
                return Right;
    return None;
}

function int MixedControl(bool Enabled)
{
    local Actor Item;
    local int Count, Index;
    if (Enabled)
    {
        foreach AllActors(class'Actor', Item)
        {
            Index = 0;
            while (Index < 3)
            {
                Index++;
                if (Index == 2)
                    continue;
                if (Count > 7)
                    break;
                if (Item == Self)
                    Count++;
                else
                    Count += 2;
            }
        }
    }
    return Count;
}

function int SwitchActors(byte Mode)
{
    local Actor Item;
    local int Count;
    foreach AllActors(class'Actor', Item)
    {
        switch (Mode)
        {
            case 0:
                Count++;
                break;
            case 1:
            case 2:
                Count += 2;
                break;
            default:
                Count += 3;
        }
    }
    return Count;
}
