class EventSwitchProbe extends EventSwitchBase;

function OnEvent(int EventID, string Param)
{
    if (EventID == 2010) Result = 6;
    if (2010 != EventID) Result = 7;
    if (EventID == 2030) Result = 8;
    if (EventID == 9999) Result = 9;
    if (EventID + 1 == 2010) Result = 10;
    switch (EventID)
    {
        case 2010: Result = 1; break;
        case 2030: Result = 2; break;
        case 9999: Result = 3; break;
    }
    switch (EventID + 1)
    {
        case 2010: Result = 4; break;
    }
}

function Unrelated(int Value)
{
    if (Value == 2010) Result = 6;
    switch (Value)
    {
        case 2010: Result = 5; break;
    }
}
