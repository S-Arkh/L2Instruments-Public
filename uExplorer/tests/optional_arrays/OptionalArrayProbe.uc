class OptionalArrayProbe extends Object;

native function Send(int ID, optional array<byte> Payload);
native function SendMore(int ID, optional array<byte> Payload, optional int Extra);
native function LeadingOmission(optional array<byte> Payload, optional int Extra);
native function LeadingTwoOmissions(optional int First, optional array<byte> Payload, optional int Extra);

function Omitted()
{
    Send(1);
    SendMore(2, , 3);
    LeadingOmission(, 7);
    LeadingTwoOmissions(, , 9);
}

function Explicit()
{
    local array<byte> Payload;
    Send(1, Payload);
}
