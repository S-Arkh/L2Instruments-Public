class ReplicationControl extends Actor;

struct Payload { var int Value; };
var Payload Data;
var PointerOwner OwnerReference;

replication
{
    reliable if (true) Data, OwnerReference, Send;
}

function Send(int Value)
{
    local pointer Scratch;
    Scratch = 0;
    Data.Value = Value;
}
