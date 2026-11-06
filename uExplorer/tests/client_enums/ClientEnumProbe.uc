class ClientEnumProbe extends Object;

function Actor.EL2ObjectType Airship()
{
    return EL2_AIRSHIPKEY;
}

function Actor.EL2ObjectType Statue()
{
    return EL2_STATUE;
}

function bool Compare(Actor.EL2ObjectType Value)
{
    return Value == EL2_AIRSHIPKEY;
}
