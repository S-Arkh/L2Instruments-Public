class BrowserWnd extends UICommonAPI;

var WindowHandle Me;
var TextureHandle Surface;
var Texture ProbeTexture;
var int Phase;

function OnLoad()
{
    Me = GetWindowHandle("BrowserWnd");
    Surface = GetTextureHandle("BrowserWnd.ProbeSurface");
}

function OnShow()
{
    // Hide any HWND browser from the earlier prototype.
    class'AddWebAPI'.static.WebHide();
    if (ProbeTexture == None)
        ProbeTexture = new(self) class'Texture';
    Phase = 0;
    if (UpdateProbe())
    {
        Surface.SetTextureWithObject(ProbeTexture);
        Me.SetTimer(7201, 100);
    }
}

function bool UpdateProbe()
{
    if (!class'TextureProbeAPI'.static.TextureProbeFrame(ProbeTexture, Phase))
    {
        Me.SetWindowTitle("Texture probe FAILED: " $ string(class'TextureProbeAPI'.static.TextureProbeStatus()));
        Me.KillTimer(7201);
        return false;
    }
    Me.SetWindowTitle("HF Texture probe / frame " $ string(Phase));
    Phase = (Phase + 1) % 1000000;
    return true;
}

function OnTimer(int TimerID)
{
    if (TimerID == 7201)
        UpdateProbe();
}

function OnHide()
{
    Me.KillTimer(7201);
    // Keep the UObject reference while the control holds its pointer.
}

function OnExitState(name NextState)
{
    Me.HideWindow();
    OnHide();
}
