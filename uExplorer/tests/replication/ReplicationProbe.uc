class ReplicationProbe extends Actor;

var int Counter;
var byte SmallValue;
var bool Enabled;

replication
{
    reliable if (Role == ROLE_Authority)
        Counter, SmallValue, ReceiveValue;
    unreliable if (Role < ROLE_Authority)
        SendValue;
    reliable if (bNetInitial)
        Enabled;
}

simulated function ReceiveValue(int Value)
{
    Counter = Value;
}

function SendValue(int Value)
{
    Counter = Value;
}
