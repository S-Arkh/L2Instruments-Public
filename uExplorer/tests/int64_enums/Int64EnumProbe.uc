class Int64EnumProbe extends Object;

enum Choice
{
    First,
    Second
};

function INT64 Explicit(Choice Value)
{
    return INT64(Value);
}

function INT64 ThroughInt(Choice Value)
{
    return INT64(int(Value));
}
