class BrowserWnd extends UICommonAPI;

#exec TEXTURE IMPORT NAME=BrowserIcon FILE=Textures\BrowserIcon.tga MIPS=OFF

var WindowHandle Me;
var TextureHandle Surface;
var ButtonHandle InputSurface;
var EditBoxHandle Address;
var EditBoxHandle Keyboard;
var Texture BrowserTexture;
var int FrameNumber;
var bool BrowserFocused;
var bool PointerOver;
var int MouseDownCount;
var int KeyDownCount;
var int MouseUpCount;
var bool LeftHeld;
var int LastKey;
var bool WheelDownSeen;
var int WheelStatus;
var bool RestorePage;
var bool OpenRequested;
var string RequestedURL;
var bool ControlsHidden;

// Call through BrowserWnd(GetScript("BrowserWnd")) from another UI script.
// An empty URL uses options.config. Options apply to this opening only.
function OpenBrowser(optional string StartURL, optional bool HideControls)
{
    RequestedURL = StartURL;
    ControlsHidden = HideControls;
    OpenRequested = true;
    RestorePage = false;
    if (Me.IsShowWindow() && !Me.IsMinimizedWindow())
    {
        ReleaseBrowserFocus();
        StartRequestedPage();
    }
    else
        Me.ShowWindow();
}
function SetControlHidden(string ControlName, bool Hidden)
{
    local WindowHandle Control;
    Control = GetWindowHandle("BrowserWnd." $ ControlName);
    if (Hidden) Control.HideWindow();
    else Control.ShowWindow();
}
function ApplyControlVisibility()
{
    SetControlHidden("btnHome", ControlsHidden);
    SetControlHidden("btnReload", ControlsHidden);
    SetControlHidden("Address", ControlsHidden);
    SetControlHidden("btnGo", ControlsHidden);
}
function StartRequestedPage()
{
    if (!OpenRequested)
    {
        RequestedURL = "";
        ControlsHidden = false;
    }
    OpenRequested = false;
    ApplyControlVisibility();
    Address.SetString(RequestedURL);
    class'TextureWebAPI'.static.TextureWebOpen();
    if (Len(RequestedURL) > 0) Navigate();
    RequestedURL = "";
}

function OnLoad()
{
    Me = GetWindowHandle("BrowserWnd");
    Surface = GetTextureHandle("BrowserWnd.ProbeSurface");
    InputSurface = GetButtonHandle("BrowserWnd.BrowserInput");
    Address = GetEditBoxHandle("BrowserWnd.Address");
    Keyboard = GetEditBoxHandle("BrowserWnd.BrowserKeyboard");
}
function OnShow()
{
    if (RestorePage)
    {
        ApplyControlVisibility();
        class'TextureWebAPI'.static.TextureWebResume();
    }
    else
        StartRequestedPage();
    RestorePage = false;
    PointerOver = false;
    InputSurface.SetAlwaysFullAlpha(false);
    InputSurface.SetAlpha(0);
    Keyboard.SetAlwaysFullAlpha(false);
    Keyboard.SetAlpha(0);
    Keyboard.SetString("");
    Me.EnableTick();
    class'AddWebAPI'.static.WebHide();
    if (BrowserTexture == None)
        BrowserTexture = new(self) class'Texture';
    FrameNumber = 0;
    MouseDownCount = 0;
    KeyDownCount = 0;
    MouseUpCount = 0;
    LastKey = 0;
    UpdateFrame();
    Surface.SetTextureWithObject(BrowserTexture);
    Me.SetTimer(7202, 16);
}
function UpdateFrame()
{
    local int BrowserStatus;
    if (!class'TextureProbeAPI'.static.TextureProbeFrame(BrowserTexture, FrameNumber))
    {
        Me.SetWindowTitle("Browser texture FAILED: " $ string(class'TextureProbeAPI'.static.TextureProbeStatus()));
        return;
    }
    BrowserStatus = class'TextureWebAPI'.static.TextureWebStatus();
    if (BrowserStatus < 0)
        Me.SetWindowTitle("Browser capture FAILED: " $ string(BrowserStatus));
    else if (BrowserStatus != 2)
        Me.SetWindowTitle("Browser texture: loading...");
    else
        Me.SetWindowTitle("Browser D/U " $ string(MouseDownCount) $ "/" $ string(MouseUpCount) $ " K " $ string(KeyDownCount) $ ":" $ string(LastKey) $ " W " $ string(WheelStatus) $ " F " $ string(Keyboard.IsFocused()));
    FrameNumber = (FrameNumber + 1) % 1000000;
}
function OnTimer(int TimerID)
{
    if (TimerID == 7202) UpdateFrame();
}
function OnHide()
{
    PointerOver = false;
    ReleaseBrowserFocus();
    Me.DisableTick();
    Me.KillTimer(7202);
    if (RestorePage || Me.IsMinimizedWindow())
        class'TextureWebAPI'.static.TextureWebHide();
    else
        class'TextureWebAPI'.static.TextureWebClose();
}
function OnExitState(name NextState)
{
    CloseForStateChange();
}
function OnEnterState(name PreviousState)
{
    CloseForStateChange();
}
function CloseForStateChange()
{
    RestorePage = false;
    Me.HideWindow();
    OnHide();
    class'TextureWebAPI'.static.TextureWebClose();
}
function OnMinimize()
{
    RestorePage = true;
    OnHide();
}
function OnClickButton(string strID)
{
    if (strID == "BrowserInput")
    {
        // Some button paths notify Click instead of forwarding ButtonUp.
        FinishLeftClick();
        return;
    }
    ReleaseBrowserFocus();
    switch (strID)
    {
    case "btnBack": class'TextureWebAPI'.static.TextureWebCommand(1); break;
    case "btnForward": class'TextureWebAPI'.static.TextureWebCommand(2); break;
    case "btnReload": class'TextureWebAPI'.static.TextureWebCommand(3); break;
    case "btnHome": class'TextureWebAPI'.static.TextureWebCommand(4); break;
    case "btnGo": Navigate(); break;
    }
}
function Navigate()
{
    local string URL;
    URL = Address.GetString();
    if (Len(URL) == 0) return;
    if (Left(Caps(URL), 7) != "HTTP://" && Left(Caps(URL), 8) != "HTTPS://")
        URL = "https://" $ URL;
    class'TextureWebAPI'.static.TextureWebNavigate(URL);
}
function OnCompleteEditBox(string strID)
{
    if (strID == "Address") Navigate();
}
function OnChangeEditBox(string strID)
{
    local string Text;
    if (strID != "BrowserKeyboard") return;
    Text = Keyboard.GetString();
    if (Len(Text) == 0) return;
    Keyboard.SetString("");
    if (!BrowserFocused || !OwnsFocus()) return;
    // Keep HF's text focus, but translate keys with the Windows layout instead
    // of forwarding the login state's filtered/Latin EditBox text.
}

function int InputModifiers()
{
    local int Flags;
    if (IsKeyDown(IK_Alt)) Flags = Flags + 1;
    if (IsKeyDown(IK_Ctrl)) Flags = Flags + 2;
    if (IsKeyDown(IK_Shift)) Flags = Flags + 8;
    return Flags;
}
function bool OwnsFocus()
{
    return Me.IsShowWindow() && !Me.IsMinimizedWindow() && !RestorePage && Keyboard.IsFocused();
}
function ReleaseBrowserFocus()
{
    BrowserFocused = false;
    LeftHeld = false;
    WheelDownSeen = false;
    if (Keyboard.IsFocused()) Keyboard.ReleaseFocus();
    class'TextureWebAPI'.static.TextureWebFocus(false);
    class'TextureWebAPI'.static.TextureWebPoll(false, false, 0, 0, 0, 0);
}
function OnTick()
{
    local Rect R;
    if (BrowserFocused && !OwnsFocus()) ReleaseBrowserFocus();
    R = Surface.GetRect();
    WheelStatus = class'TextureWebAPI'.static.TextureWebPoll(Me.IsShowWindow() && !Me.IsMinimizedWindow() && !RestorePage && (PointerOver || (BrowserFocused && OwnsFocus())), PointerOver,
        R.nX, R.nY, R.nWidth, R.nHeight);
    if (LeftHeld)
    {
        if (!class'TextureWebAPI'.static.TextureWebLeftPressed()) FinishLeftClick();
        else SendMouse(0);
    }
}
function bool IsSurfaceTarget(WindowHandle Target)
{
    local string TargetName;
    if (Target == None) return false;
    TargetName = Target.GetWindowName();
    return TargetName == "BrowserInput";
}
function bool SendMouse(int Kind)
{
    local Rect R;
    if (!Me.IsShowWindow() || Me.IsMinimizedWindow() || RestorePage) return false;
    R = Surface.GetRect();
    return class'TextureWebAPI'.static.TextureWebMouse(Kind, R.nX, R.nY, R.nWidth, R.nHeight, InputModifiers());
}
function MouseDown(WindowHandle Target, int Kind)
{
    if (IsSurfaceTarget(Target) && SendMouse(Kind))
    {
        MouseDownCount++;
        Keyboard.SetFocus();
        if (Kind == 1 || Kind == 7) LeftHeld = true;
        BrowserFocused = true;
        PointerOver = true;
        class'TextureWebAPI'.static.TextureWebFocus(true);
    }
    else ReleaseBrowserFocus();
}
function OnLButtonDown(WindowHandle Target, int X, int Y) { MouseDown(Target, 1); }
function OnLButtonDblClick(WindowHandle Target, int X, int Y) { MouseDown(Target, 7); }
function OnRButtonDown(WindowHandle Target, int X, int Y) { MouseDown(Target, 3); }
function OnLButtonUp(WindowHandle Target, int X, int Y)
{
    FinishLeftClick();
}
function FinishLeftClick()
{
    if (!LeftHeld) return;
    // Moving focus from the button to EditBox can synthesize a release in HF.
    if (class'TextureWebAPI'.static.TextureWebLeftPressed()) return;
    LeftHeld = false;
    MouseUpCount++;
    if (!SendMouse(2)) ReleaseBrowserFocus();
}
function OnRButtonUp(WindowHandle Target, int X, int Y)
{
    if (BrowserFocused && !SendMouse(4)) ReleaseBrowserFocus();
}
function OnMouseMove(WindowHandle Target, int X, int Y)
{
    PointerOver = false;
    if (IsSurfaceTarget(Target)) PointerOver = SendMouse(0);
}
function OnMouseOut(WindowHandle Target) { PointerOver = false; }
function OnMouseOver(WindowHandle Target)
{
    PointerOver = IsSurfaceTarget(Target);
    if (PointerOver) SendMouse(0);
}
function OnKeyDown(WindowHandle Target, EInputKey Key)
{
    KeyDownCount++;
    LastKey = int(Key);
    if (!BrowserFocused || !OwnsFocus()) return;
    if (Key == IK_MouseWheelUp || Key == IK_MouseWheelDown)
    {
        WheelDownSeen = true;
        SendWheel(Key);
    }
    else
        class'TextureWebAPI'.static.TextureWebKey(int(Key), true, InputModifiers());
}
function SendWheel(EInputKey Key)
{
    if (!PointerOver) return;
    // Native wheel routing owns delivery when its thread hook is installed.
    if ((WheelStatus & 1) != 0) return;
    if (Key == IK_MouseWheelUp) SendMouse(5);
    else SendMouse(6);
}
function OnKeyUp(WindowHandle Target, EInputKey Key)
{
    if (!BrowserFocused || !OwnsFocus()) return;
    if (Key == IK_MouseWheelUp || Key == IK_MouseWheelDown)
    {
        if (!WheelDownSeen) SendWheel(Key);
        WheelDownSeen = false;
    }
    else
        class'TextureWebAPI'.static.TextureWebKey(int(Key), false, InputModifiers());
}
