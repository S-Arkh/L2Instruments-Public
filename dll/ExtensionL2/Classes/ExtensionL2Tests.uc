// Usage tests. Native declarations are generated in ExtensionL2API.uc.
class ExtensionL2Tests extends ExtensionL2API;

static function int64 ExampleCall()
{
    return SaturatingAdd64(2147483647, 1);
}

static function int64 ExampleLarge()
{
    return SaturatingAdd64(5000000000, 10);
}

static function bool FileRoundTrip(string FileName, string Directory, string Text)
{
    if (!WriteTextFile(FileName, Directory, Text))
        return false;
    return ReadTextFile(FileName, Directory) == Text && GetFileError() == 0;
}

static function bool SelfTest()
{
    return ExampleCall() == 2147483648
        && ExampleLarge() == 5000000010
        && SaturatingAdd64(9223372036854775807, 1) == 9223372036854775807
        && SaturatingAdd64(-9223372036854775808, -1) == -9223372036854775808;
}

static function string Int64Result(string Label, int64 Actual, int64 Expected)
{
    local string Status;
    if (Actual == Expected)
        Status = "PASS";
    else
        Status = "FAIL";
    return Status $ " | " $ Label $ " | actual=" $ string(Actual)
        $ " | expected=" $ string(Expected) $ Chr(13) $ Chr(10);
}

// Run real native calls on every click. Expected values are only comparison data.
static function string Int64Report()
{
    local string Report;
    Report = "Credit button clicked." $ Chr(13) $ Chr(10)
        $ "ExtensionL2 native int64 tests" $ Chr(13) $ Chr(10);
    Report = Report $ Int64Result("2147483647 + 1", ExampleCall(), 2147483648);
    Report = Report $ Int64Result("5000000000 + 10", ExampleLarge(), 5000000010);
    Report = Report $ Int64Result("-5000000000 - 10", SaturatingAdd64(-5000000000, -10), -5000000010);
    Report = Report $ Int64Result("MAX + 1 (saturate)", SaturatingAdd64(9223372036854775807, 1), 9223372036854775807);
    Report = Report $ Int64Result("MIN - 1 (saturate)", SaturatingAdd64(-9223372036854775808, -1), -9223372036854775808);
    Report = Report $ Int64Result("MAX + MIN", SaturatingAdd64(9223372036854775807, -9223372036854775808), -1);
    Report = Report $ Int64Result("0 + 0", SaturatingAdd64(0, 0), 0);
    Report = Report $ Int64Result("nested Add(Add(MAX, 1), -1)",
        SaturatingAdd64(SaturatingAdd64(9223372036854775807, 1), -1), 9223372036854775806);
    Report = Report $ "SelfTest=" $ string(SelfTest()) $ Chr(13) $ Chr(10);
    return Report;
}
