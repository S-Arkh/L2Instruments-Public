class EventProbe extends EventBase;

function Register()
{
    RegisterEvent(2010);
    RegisterEvent(2030);
    RegisterEvent(9999);
    ExecuteEvent(2010, "payload");
}

function Shadowed(int EV_Ready)
{
    RegisterEvent(2010);
}
