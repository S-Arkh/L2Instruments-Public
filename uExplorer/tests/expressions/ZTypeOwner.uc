class ZTypeOwner extends ZTypeBase;

struct Payload
{
    var int Value;
};

struct Container
{
    var Payload Data;
    var array<Payload> Items;
};

enum Choice
{
    First,
    Second
};

function Choice GetChoice()
{
    return Second;
}
