class LatentProbe extends Actor;

var int Count;
var Actor Item;

auto state Waiting
{
Begin:
Start:
    Sleep(0.25);
    Count++;
    goto 'Again';
Again:
    while (Count < 3)
    {
        Sleep(0.5);
        Count++;
    }
    Stop;
}

state Iterating
{
Begin:
    foreach AllActors(class'Actor', Item)
    {
        Count++;
        if (Item == Self)
            break;
    }
    Sleep(0.125);
    goto 'Begin';
}
