class GenerationBase extends Object;

enum EChoice
{
    First,
    Second
};

delegate int Compare(int A, int B);

delegate bool Choose(EChoice Choice, optional int Count);

delegate int DefaultValue(optional int Offset)
{
    return Offset;
}
