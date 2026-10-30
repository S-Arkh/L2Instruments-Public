# Gracia UI loader: investigation

Input NWindow.dll SHA256:
`14b838bbc6b6517ddc8294f0ab2fafdbe73daa5e4a39da224fdfd252c4545e06`.
Addresses below are preferred virtual addresses (image base `0x10000000`).

At `0x101CF181` the script name is converted from FString. At `0x101CF18A`
the loader pushes UTF-16 `Interface` (VA `0x102FC520`), then `%s.%s`
(VA `0x10312B3C`) and formats a class name. At `0x101CF1B8` it calls
Core StaticLoadClass through IAT `0x102E132C` using the formatted name.
Before this fallback it searches a name produced by `0x101CE160`, which also
uses the Interface prefix in the observed branches.

Consequently, accepting `GameBrowser.BrowserWnd` directly as the XDAT script
has not been established; the observed fallback would prefix it with Interface.
No NWindow patch has been applied. This evidence does not rule out every other
loader path, but does rule out assuming the examined fallback accepts a fully
qualified external-package name unchanged.

The earlier StaticLoadClass call at `0x101C540A` uses `Editor.MakeCommandlet`,
followed by `-UIScriptCompile`. It is a compiler path, not evidence of external
UI package loading.
