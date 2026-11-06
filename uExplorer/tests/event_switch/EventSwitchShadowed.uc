class EventSwitchShadowed extends EventSwitchBase;

event OnEvent(int EV_Ready, string Param)
{
    if (EV_Ready == 2010) Result = 2;
    switch (EV_Ready)
    {
        case 2010: Result = 1; break;
    }
}
