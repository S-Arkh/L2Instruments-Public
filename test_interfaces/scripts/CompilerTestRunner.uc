class CompilerTestRunner extends ExtensionL2API;

enum TestChoice { ChoiceFirst, ChoiceSecond };
struct TestPair
{
    var int Value;
    var TestChoice Choice;
};
var string Report;
var int Passed;
var int Failed;
var int Skipped;
var bool FileFailed;

function bool SaveReport()
{
    if (!WriteTextFile("test.txt", "", Report))
    {
        FileFailed = true;
        return false;
    }
    return true;
}

function bool BeginTest(string Name)
{
    Report = Report $ "RUN | " $ Name $ Chr(13) $ Chr(10);
    return SaveReport();
}

function bool Check(string Name, bool Success, string Actual, string Expected)
{
    local string Status;
    if (Success)
    {
        Passed++;
        Status = "PASS";
    }
    else
    {
        Failed++;
        Status = "FAIL";
    }
    Report = Report $ Status $ " | " $ Name $ " | actual=" $ Actual
        $ " | expected=" $ Expected $ Chr(13) $ Chr(10);
    return SaveReport();
}

function bool Skip(string Name, string Reason)
{
    Skipped++;
    Report = Report $ "SKIP | " $ Name $ " | " $ Reason $ Chr(13) $ Chr(10);
    return SaveReport();
}

function int OptionalValues(optional array<int> Values, optional int Marker)
{
    return Values.Length + Marker;
}

function bool AdditionalTests()
{
    return Skip("client array.Sort", "not included in this test variant");
}

function bool PointerTests()
{
    return Skip("pointer runtime operations", "no verified pointer adapter for this profile");
}

function string Run(string Profile, string BuildIdentity)
{
    local INT64 Wide;
    local int Value;
    local byte Raw;
    local TestChoice Choice;
    local string Summary;
    local array<int> Values;
    local CompilerTestRunner.TestPair Pair;
    local Object ChoiceType;

    Passed = 0;
    Failed = 0;
    Skipped = 0;
    FileFailed = false;
    Report = "Test button clicked." $ Chr(13) $ Chr(10)
        $ "Profile=" $ Profile $ Chr(13) $ Chr(10)
        $ "Build=" $ BuildIdentity $ Chr(13) $ Chr(10);
    if (!SaveReport()) return "Cannot write System/test.txt";

    if (!BeginTest("native INT64 arguments/result")) return "Cannot update System/test.txt";
    Wide = SaturatingAdd64(INT64("5000000000"), INT64("10"));
    if (!Check("native INT64 arguments/result", Wide == INT64("5000000010"), string(Wide), "5000000010")) return "Cannot update System/test.txt";

    if (!BeginTest("INT64 arithmetic")) return "Cannot update System/test.txt";
    Wide = (INT64("5000000000") + INT64("12")) - INT64("2");
    if (!Check("INT64 arithmetic", Wide == INT64("5000000010"), string(Wide), "5000000010")) return "Cannot update System/test.txt";

    if (!BeginTest("explicit enum to INT64")) return "Cannot update System/test.txt";
    Choice = ChoiceSecond;
    Wide = INT64(Choice);
    if (!Check("explicit enum to INT64", Wide == INT64("1"), string(Wide), "1")) return "Cannot update System/test.txt";

    if (!BeginTest("byte to enum")) return "Cannot update System/test.txt";
    Raw = 1;
    Choice = TestChoice(Raw);
    if (!Check("byte to enum", Choice == ChoiceSecond, string(int(Choice)), "1")) return "Cannot update System/test.txt";

    if (!BeginTest("optional array omission")) return "Cannot update System/test.txt";
    Value = OptionalValues(, 7);
    if (!Check("optional array omission", Value == 7, string(Value), "7")) return "Cannot update System/test.txt";

    if (!BeginTest("native string return")) return "Cannot update System/test.txt";
    if (!Check("native string return", ReadTextFile("test.txt", "") == Report, "file comparison", "identical report")) return "Cannot update System/test.txt";

    if (!BeginTest("native INT64 negative result")) return "Cannot update System/test.txt";
    Wide = SaturatingAdd64(INT64("-5000000000"), INT64("-10"));
    if (!Check("native INT64 negative result", Wide == INT64("-5000000010"), string(Wide), "-5000000010")) return "Cannot update System/test.txt";

    if (!BeginTest("native INT64 upper saturation")) return "Cannot update System/test.txt";
    Wide = SaturatingAdd64(INT64("9223372036854775807"), INT64("1"));
    if (!Check("native INT64 upper saturation", Wide == INT64("9223372036854775807"), string(Wide), "9223372036854775807")) return "Cannot update System/test.txt";

    if (!BeginTest("native INT64 lower saturation")) return "Cannot update System/test.txt";
    Wide = SaturatingAdd64(INT64("-9223372036854775808"), INT64("-1"));
    if (!Check("native INT64 lower saturation", Wide == INT64("-9223372036854775808"), string(Wide), "-9223372036854775808")) return "Cannot update System/test.txt";

    if (!BeginTest("optional array supplied")) return "Cannot update System/test.txt";
    Values.Length = 2;
    Values[0] = 10;
    Values[1] = 20;
    Value = OptionalValues(Values, 7);
    if (!Check("optional array supplied", Value == 9 && Values[0] == 10 && Values[1] == 20, string(Value), "9")) return "Cannot update System/test.txt";

    if (!BeginTest("qualified struct with enum member")) return "Cannot update System/test.txt";
    Pair.Value = 41;
    Pair.Choice = ChoiceSecond;
    Value = Pair.Value + int(Pair.Choice);
    if (!Check("qualified struct with enum member", Value == 42, string(Value), "42")) return "Cannot update System/test.txt";

    if (!BeginTest("enum object literal")) return "Cannot update System/test.txt";
    ChoiceType = Enum'Interface.CompilerTestRunner.TestChoice';
    if (!Check("enum object literal", ChoiceType != None, string(ChoiceType), "non-None TestChoice enum")) return "Cannot update System/test.txt";

    if (!AdditionalTests()) return "Cannot update System/test.txt";
    if (!PointerTests()) return "Cannot update System/test.txt";

    Summary = "TOTAL | PASS=" $ string(Passed) $ " | FAIL=" $ string(Failed) $ " | SKIP=" $ string(Skipped);
    Report = Report $ Summary $ Chr(13) $ Chr(10);
    if (!SaveReport()) return "Cannot update System/test.txt";
    return Summary;
}
