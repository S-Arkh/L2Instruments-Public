class BrowserWnd extends UICommonAPI;

var WindowHandle Me;
var EditBoxHandle Address;

function OnLoad()
{
    Me = GetWindowHandle("BrowserWnd");
    Address = GetEditBoxHandle("BrowserWnd.Address");
    Me.SetWindowTitle("Web Browser");
}

function OnShow()
{
    Me.SetWindowTitle("Web Browser");
    SyncBounds();
    class'AddWebAPI'.static.WebShow();
    Me.SetTimer(7101, 16);
}

function SyncBounds()
{
    local Rect R;
    if (!Me.IsShowWindow())
        return;
    R = Me.GetRect();
    class'AddWebAPI'.static.WebBounds(R.nX + 10, R.nY + 66, R.nWidth - 20, R.nHeight - 76);
}

function OnTick()
{
    SyncBounds();
}

function OnTimer(int TimerID)
{
    if (TimerID == 7101)
        SyncBounds();
}

function OnHide()
{
    Me.KillTimer(7101);
    class'AddWebAPI'.static.WebHide();
}

function OnExitState(name NextState)
{
    Me.HideWindow();
    OnHide();
}

function OnClickButton(string strID)
{
    switch (strID)
    {
    case "btnBack": class'AddWebAPI'.static.WebCommand(1); break;
    case "btnForward": class'AddWebAPI'.static.WebCommand(2); break;
    case "btnReload": class'AddWebAPI'.static.WebCommand(3); break;
    case "btnHome": class'AddWebAPI'.static.WebCommand(4); break;
    case "btnGo": Navigate(); break;
    }
}

function Navigate()
{
    local string URL;
    URL = Address.GetString();
    if (Len(URL) == 0)
        return;
    if (Left(Caps(URL), 7) != "HTTP://" && Left(Caps(URL), 8) != "HTTPS://")
        URL = "https://" $ URL;
    class'AddWebAPI'.static.WebNavigate(URL);
}

function OnCompleteEditBox(string strID)
{
    if (strID == "Address")
        Navigate();
}
