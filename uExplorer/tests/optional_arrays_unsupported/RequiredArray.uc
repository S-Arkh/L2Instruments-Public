class RequiredArray extends Object;

native function Send(int ID, array<byte> Payload);

function MissingRequired()
{
    Send(1);
}
