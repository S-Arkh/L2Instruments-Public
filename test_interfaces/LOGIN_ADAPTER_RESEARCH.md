# Login adapter research

## Verified Korean path

The ordinary XDAT window exposes `LogIn.Btn_Login`. A cloned Test control anchored
to its left reached the client and invoked the compiled wrapper. The initial
expanded runtime subset passed sixteen checks with one explicit pointer skip. Installed artifact
hashes matched the candidate manifest. The final summary is visible through
`LogIn.Txt_Msg`, which the original Login class uses for login error messages.
The generic native `ShowMessageInLogin` call did not produce a visible summary in
the exercised modern client.

The client Sort convention differs from the initial C-style comparator assumption:
positive for A < B produced ascending order. Reversing the sign produced descending
order, including duplicate values. Receiver evaluation and delegate invocation
were checked independently. The same checks passed in the exercised Japanese build.

## Legacy discovery

The inspected Gracia Interface has only `LoginMenuWnd` among login-named classes;
High Five also exposes character-password classes. The menu click handler manages
account links, options, credits and replay rather than credential submission.
The inspected XDAT menu does not expose the actual login button.

Read-only string inspection of the matching NWindow libraries found native
`autoclassLoginWnd` registration strings in both profiles. Gracia additionally
exposes LoginWnd RTTI, a login-window source-file diagnostic and login-state
diagnostics. This supports investigating a native-created login control rather
than treating LoginMenuWnd as the actual login form. String evidence alone does
not establish a valid control path, coordinates, or a verified button adapter.

The accepted legacy placement uses the ordinary bottom-right menu instead of
anchoring to the native login form. Test is appended below Replay, preserving the
existing menu actions. Both clients passed twelve checks with two explicit skips
(Sort and pointer runtime operations), and displayed the summary through the
existing native login-message API. Layout rollback restores the original bytes.

## Japanese GFx path

The recovered Login class extends GFxUIScript. `OnCallUCFunction` handles `setLogin`,
`out` and `openURL`. Its error-message method invokes
`CallGFxFunction("LogIn", "ErrorMsg", ErrorMsg)`; initialization uses `flashInit`.
These identify existing bridge entry points, but do not demonstrate an existing
Test control or a supported Flash mutation API. The accepted implementation adds
an ordinary CompilerTestWnd in LoginState, using UIEasyLoginWnd control templates.
The bottom-right button and summary were verified in the client alongside the
original GFx form. No movie modification or Flash button anchoring is required.

## Artifact and repeat-run evidence

All four clients ran the expanded subset twice. Repeated reports were byte-identical
with reset counters. The verification tool matched the report profile and Build,
checked totals, and compared the installed Interface, XDAT, Core and ExtensionL2
hashes with their candidate manifests. This binds on-disk artifacts and reports;
it is not an attestation of modules in process memory.

The complete preparation workflow was also exercised from original inputs for all
four profiles. Rebuilt XDAT and DLL files were byte-identical. Rebuilt Interface
packages differed only in their sixteen-byte package GUIDs, so reproducibility
does not imply identical whole-file hashes. Each output retains its own manifest.

These results cover the exercised test subset, not all gameplay or metadata
equivalence. Compiler-only checks and remaining coverage are tracked separately
in COVERAGE.md. Client write-failure injection is excluded from the agreed scope;
the standalone native file-error tests remain applicable.
