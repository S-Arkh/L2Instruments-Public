class CompilerSortTestRunner extends CompilerTestRunner;

struct SortBucket { var array<int> Values; };
var array<SortBucket> Buckets;
var int ReceiverCalls;
var int ComparatorCalls;
var bool ReverseOrder;
var native pointer PointerValue, PointerValues[2];
struct PointerBucket { var transient pointer Value; var int Guard; };
var PointerBucket PointerData;
var int PointerCalls;

function pointer PointerIdentity(pointer Value)
{
    local pointer Saved;
    PointerCalls++;
    Saved = Value;
    return Saved;
}

function SetPointer(out pointer Destination, pointer Value)
{
    Destination = Value;
}

function bool PointerTests()
{
    local pointer Empty;
    if (!BeginTest("pointer declarations and zero storage")) return false;
    if (!Check("pointer zero initialization", PointerEqual(Empty, 0) && PointerEqual(PointerValue, 0)
        && PointerEqual(PointerValues[1], 0) && PointerEqual(PointerData.Value, 0), "zero pointer storage", "zero pointer storage")) return false;
    PointerCalls = 0;
    PointerData.Guard = 73;
    SetPointer(PointerValues[1], PointerIdentity(Empty));
    PointerData.Value = PointerValues[1];
    PointerValue = PointerIdentity(PointerData.Value);
    if (!Check("pointer local parameter return and out", PointerEqual(PointerValue, Empty)
        && PointerCalls == 2 && PointerData.Guard == 73, string(PointerCalls) $ "," $ string(PointerData.Guard), "2,73")) return false;
    PointerValues[1] = 0;
    if (!Check("pointer indexed null assignment", PointerEqual(PointerValues[0], 0)
        && PointerEqual(PointerValues[1], 0), "zero pointer array", "zero pointer array")) return false;
    return NonzeroPointerTests();
}

function bool NonzeroPointerTests()
{
    local GFxUIScript Allocator;
    local GFxValue First, Second;
    local pointer Saved, Other;
    local bool Passed, OwnersReady, FirstNonzero, SecondNonzero, Distinct;
    local float FirstValue, SecondValue;
    if (!BeginTest("native GFxValue pointer sources")) return false;
    // The native objects own these addresses throughout the test. Never import
    // integer markers as pointers and never write back to the native handles.
    // A bare UObject allocation does not establish GFx value initialization.
    // Use the native allocation/deallocation pair used by client UI scripts.
    Allocator = new class'GFxUIScript';
    if (Allocator != None)
    {
        Allocator.AllocGFxValue(First);
        Allocator.AllocGFxValue(Second);
    }
    OwnersReady = Allocator != None && First != None && Second != None && First != Second;
    Passed = Check("pointer native owners", OwnersReady,
        string(Allocator != None) $ "," $ string(First != None) $ "," $ string(Second != None)
        $ "," $ string(First != Second), "True,True,True,True");
    if (!Passed || !OwnersReady)
    {
        if (Allocator != None)
        {
            if (Second == First) Second = None;
            if (First != None) Allocator.DeallocGFxValue(First);
            if (Second != None) Allocator.DeallocGFxValue(Second);
        }
        return Passed;
    }
    if (!BeginTest("native GFxValue payload initialization"))
    {
        Allocator.DeallocGFxValue(First);
        Allocator.DeallocGFxValue(Second);
        return false;
    }
    First.SetInt(73);
    Second.SetInt(91);
    Saved = First.pValue;
    Other = Second.pValue;
    FirstNonzero = !PointerEqual(Saved, 0);
    SecondNonzero = !PointerEqual(Other, 0);
    Distinct = !PointerEqual(Saved, Other);
    // These clients' SetInt stores GFx Number (tag 5 / double); GetInt only
    // reads tag 3. GetFloat is the matching numeric getter for this native API.
    FirstValue = First.GetFloat();
    SecondValue = Second.GetFloat();
    Passed = Check("pointer native nonzero distinct values", FirstNonzero && SecondNonzero
        && Distinct && FirstValue == 73 && SecondValue == 91,
        string(FirstNonzero) $ "," $ string(SecondNonzero) $ "," $ string(Distinct)
        $ "," $ string(FirstValue) $ "," $ string(SecondValue),
        "True,True,True," $ string(73.0) $ "," $ string(91.0));
    if (!Passed || !FirstNonzero || !SecondNonzero || !Distinct || FirstValue != 73 || SecondValue != 91)
    {
        Saved = 0;
        Other = 0;
        Allocator.DeallocGFxValue(First);
        Allocator.DeallocGFxValue(Second);
        return Passed;
    }
    PointerCalls = 0;
    PointerData.Guard = 73;
    SetPointer(PointerValues[1], PointerIdentity(Saved));
    PointerData.Value = PointerValues[1];
    PointerValue = PointerIdentity(PointerData.Value);
    Passed = Check("pointer nonzero local parameter return and out", PointerEqual(PointerValue, Saved)
        && PointerEqual(PointerData.Value, First.pValue) && PointerEqual(PointerValues[1], Saved)
        && !PointerEqual(PointerValue, Other) && PointerCalls == 2 && PointerData.Guard == 73,
        string(PointerCalls) $ "," $ string(PointerData.Guard), "2,73");
    PointerValue = 0;
    PointerValues[1] = 0;
    PointerData.Value = 0;
    Saved = 0;
    Other = 0;
    if (!Passed)
    {
        Allocator.DeallocGFxValue(First);
        Allocator.DeallocGFxValue(Second);
        return false;
    }
    FirstValue = First.GetFloat();
    SecondValue = Second.GetFloat();
    Passed = Check("pointer nonzero clear preserves native owners", PointerEqual(PointerValue, 0)
        && PointerEqual(PointerValues[1], 0) && PointerEqual(PointerData.Value, 0)
        && PointerEqual(Saved, 0) && PointerEqual(Other, 0)
        && !PointerEqual(First.pValue, 0) && !PointerEqual(Second.pValue, 0)
        && FirstValue == 73 && SecondValue == 91,
        string(FirstValue) $ "," $ string(SecondValue), string(73.0) $ "," $ string(91.0));
    Allocator.DeallocGFxValue(First);
    Allocator.DeallocGFxValue(Second);
    return Passed;
}

delegate int CompareValues(int A, int B)
{
    ComparatorCalls++;
    // Korean client Sort: positive puts A before B (opposite to C qsort).
    if (A < B)
    {
        if (ReverseOrder) return -1;
        return 1;
    }
    if (A > B)
    {
        if (ReverseOrder) return 1;
        return -1;
    }
    return 0;
}

function int SelectBucket()
{
    ReceiverCalls++;
    return 0;
}

function bool AdditionalTests()
{
    if (!BeginTest("client array.Sort")) return false;
    ReceiverCalls = 0;
    ComparatorCalls = 0;
    ReverseOrder = false;
    Buckets.Length = 1;
    Buckets[0].Values.Length = 3;
    Buckets[0].Values[0] = 3;
    Buckets[0].Values[1] = 1;
    Buckets[0].Values[2] = 2;
    Buckets[SelectBucket()].Values.Sort(CompareValues);
    if (!Check("Sort order", Buckets[0].Values[0] == 1 && Buckets[0].Values[1] == 2 && Buckets[0].Values[2] == 3,
               string(Buckets[0].Values[0]) $ "," $ string(Buckets[0].Values[1]) $ "," $ string(Buckets[0].Values[2]), "1,2,3")) return false;
    if (!Check("Sort receiver evaluation", ReceiverCalls == 1, string(ReceiverCalls), "1")) return false;
    if (!Check("Sort delegate execution", ComparatorCalls > 0, string(ComparatorCalls), "positive count")) return false;
    if (!BeginTest("client array.Sort reverse and duplicates")) return false;
    ReverseOrder = true;
    Buckets[0].Values.Length = 4;
    Buckets[0].Values[3] = 2;
    Buckets[0].Values.Sort(CompareValues);
    if (!Check("Sort reverse and duplicates", Buckets[0].Values[0] == 3 && Buckets[0].Values[1] == 2 && Buckets[0].Values[2] == 2 && Buckets[0].Values[3] == 1,
                  string(Buckets[0].Values[0]) $ "," $ string(Buckets[0].Values[1]) $ "," $ string(Buckets[0].Values[2]) $ "," $ string(Buckets[0].Values[3]), "3,2,2,1")) return false;
    if (!BeginTest("client array.Sort empty and singleton")) return false;
    Buckets[0].Values.Length = 0;
    ReceiverCalls = 0;
    ComparatorCalls = 0;
    Buckets[SelectBucket()].Values.Sort(CompareValues);
    if (!Check("Sort empty array", Buckets[0].Values.Length == 0 && ReceiverCalls == 1 && ComparatorCalls == 0,
        string(Buckets[0].Values.Length) $ "," $ string(ReceiverCalls) $ "," $ string(ComparatorCalls), "0,1,0")) return false;
    Buckets[0].Values.Length = 1;
    Buckets[0].Values[0] = 73;
    ReceiverCalls = 0;
    ComparatorCalls = 0;
    Buckets[SelectBucket()].Values.Sort(CompareValues);
    return Check("Sort singleton array", Buckets[0].Values.Length == 1 && Buckets[0].Values[0] == 73
        && ReceiverCalls == 1 && ComparatorCalls == 0,
        string(Buckets[0].Values[0]) $ "," $ string(ReceiverCalls) $ "," $ string(ComparatorCalls), "73,1,0");
}
