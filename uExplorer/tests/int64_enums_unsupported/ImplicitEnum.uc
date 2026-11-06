class ImplicitEnum extends Object;

enum Choice
{
    First,
    Second
};

function INT64 Implicit(Choice Value)
{
    return Value;
}
