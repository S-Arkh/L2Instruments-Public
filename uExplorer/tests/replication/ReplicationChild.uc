class ReplicationChild extends ReplicationProbe;

simulated function ReceiveValue(int Value)
{
    Counter = Value + 1;
}

state Active
{
    function SendValue(int Value)
    {
        Counter = Value + 2;
    }
}
