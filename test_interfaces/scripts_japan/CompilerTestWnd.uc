class CompilerTestWnd extends UICommonAPI;

var bool bCompilerTestRunning;

function OnClickButton(string strID)
{
    local CompilerTestRunner TestRunner;
    local string Summary;
    if (strID != "Btn_CompilerTest" || bCompilerTestRunning) return;
    bCompilerTestRunning = true;
    GetTextBoxHandle("CompilerTestWnd.Txt_Result").SetText("Running tests...");
    TestRunner = new class'CompilerSortTestRunner';
    if (TestRunner == None)
        Summary = "Cannot create compiler test runner";
    else
        Summary = TestRunner.Run("japan", "__COMPILER_BUILD_ID__");
    GetTextBoxHandle("CompilerTestWnd.Txt_Result").SetText(Summary);
    bCompilerTestRunning = false;
}
