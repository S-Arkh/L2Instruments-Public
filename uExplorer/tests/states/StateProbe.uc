class StateProbe extends Actor;

function CustomIgnored(int Value)
{
}

state Idle
{
    ignores Timer, Tick, Touch, CustomIgnored;
}

state Child extends Idle
{
}

auto state Waiting
{
    ignores PostNetReceive;
}
