class EventBase extends Object;

const EV_Ready = 2010;
const EV_AliasA = 2030;
const EV_AliasB = 2030;

native function RegisterEvent(int EventID);
native function ExecuteEvent(int EventID, optional string Param);
