class ExpressionProbe extends Object;

const Named = 'Ready';
const Text = "ready";
const Enabled = true;
const Fraction = 1.5;
const Zero = 0;
const One = 1;

enum Mode
{
    Idle,
    Active
};

function name EnumName()
{
    return GetEnum(Enum'Generation.ExpressionProbe.Mode', 1);
}

function string ByteString()
{
    return "éÅ";
}

function string WideString()
{
    return "게임";
}

function name ContextName(ExpressionProbe Target)
{
    return Target.Named;
}

function string ContextString(ExpressionProbe Target)
{
    return Target.Text;
}

function bool ContextBool(ExpressionProbe Target)
{
    return Target.Enabled;
}

function float ContextFloat(ExpressionProbe Target)
{
    return Target.Fraction;
}

function int ContextZero(ExpressionProbe Target)
{
    return Target.Zero;
}

function int ContextOne(ExpressionProbe Target)
{
    return Target.One;
}

function int NegatedLiteral()
{
    return -(-30);
}

function int NegatedExpression(int Value)
{
    return -(-Value);
}
