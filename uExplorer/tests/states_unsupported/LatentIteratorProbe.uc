class LatentIteratorProbe extends Actor;
var Actor Item;
state Invalid
{
Begin:
    foreach AllActors(class'Actor', Item)
        Sleep(0.125);
}
