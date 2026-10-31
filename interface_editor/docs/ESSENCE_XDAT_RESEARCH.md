# Essence XDAT recovery — research status

## Status

**All six supplied normal/Classic XDATs now parse to EOF with zero opaque tail.**
Byte-identical roundtrips, a variable-length window-name edit/reload, and undo
passed for each sample. Two native-reader-verified profiles are now included in
the editor catalog: `essence_native.XDAT` and `korea_native.XDAT`.
Their labels deliberately describe reader verification, not full client UI
validation or universal compatibility with a chronicle name.

Independent native-reader checks now also pass for all six edited files using
each profile's own NWindow DLL: window names and dimensions were changed and
the native archive cursor reached exact EOF. Reports are in
`evidence/native-{essence,korea,japan}.json`. This is isolated native serializer
execution, not full game startup or visual validation.

Three supplied client profiles are compared: Essence, Korea and Japan. Directory
labels and user-supplied protocol numbers are not format evidence. Essence's
unprotected executable statically maps `-L2ProtocolVersion` to revision 591;
the Korean/Japanese network protocol numbers remain unverified.
Catalog labels include Essence protocol 591, Japan protocol 230 and Korea
protocol 290. The latter two are explicitly marked `user-reported`; native-reader
verification applies to the supplied XDAT layouts, not those protocol numbers.

## Established package evidence

All 15 examined `.u` files use wrapper 111 and Unreal package profile 133/40.
uExplorer now parses the added INT64 literal, array-sort token and delegate
property metadata. Independent decoding matches all 15 packages, and structural
audits have zero failures. See `../../uExplorer/docs/PACKAGE_133_40.md` for commands,
scope and machine-readable evidence. Each NWindow package exposes 140 classes.
Script/UI API metadata is useful evidence, but does not specify native XDAT readers.

## XDAT observations and uncertainty

The native-derived draft replaces the legacy Window order and corrects base
properties and numerous control layouts. ListCtrl contains three unsigned byte
fields; ChatWindow contains four. RichListCtrl, EffectViewportWnd and StatusRound
have dedicated layouts. Root default positions are a list of groups, each holding
a list of positions; FontDefinition is conditional on a raw32 presence flag.

HeadDisplay has text, image and complex branches. ScalableData contains 101
width/height-rate pairs and 101 font-mapping groups. These are structured data,
not opaque tails. Essence and Japan samples use the same current draft. Korea's
CharacterViewportWindow omits `isCostume` but retains `useBackbuffer`, confirmed
by its own native serializer and XML setter.

| Profile | Normal bytes | Classic bytes | Unparsed tail |
| --- | ---: | ---: | ---: |
| Essence | 7501625 | 8257313 | 0 |
| Korea | 7286706 | 8102780 | 0 |
| Japan | 7501731 | 8257419 | 0 |

Follow-up native inspection resolved the initially unnamed fields:

| Field | Evidence RVA / object offset |
| --- | --- |
| nWindowStyleLow/High | XMLUIData::GetNWindowStyle 0x986b30; +0x88/+0x8c returned in EAX/EDX |
| unselectedOverTex / selectedOverTex | XMLListData::Process 0x965244; two-name table at 0xd156a8; +0x14c/+0x158 |
| GaugeTexture.ratio | XMLStatusBarCtrlData::ProcessGaugeTextureSplit 0x978bc9; +0x1c |
| deadTextColor / deadTextureScale | setters 0x95914a / 0x959184; +0xe0/+0xe4 |
| trailerU/V/USize/VSize, maskU/V/USize/VSize | StatusRound setters +0x17c/+0x18c; XMLNode::GetAttributeCoords 0x9361e0 |

The style bitmask is preserved as two raw32 halves; individual bit meanings
are not exhaustively documented. Native-reader acceptance is not a proof of
every enum domain or runtime visual behavior. Use
`tools/audit_native_xdat.py --package schemas/schemas.json --schema essence_native.XDAT
--sample <external.xdat> --output <report.json>` for a path-free edit/roundtrip
report; this does not claim actual client validation.

At offset 212573 in the Essence normal sample, `showAnimSeconds` is extremely
large. The relevant window has show/hide animation types zero. Native
`ProcessShowHideAnimNode` (RVA 0x9899e0) writes float seconds at object +0x1f8
and direction at +0x1fc. The archive helper at 0xac2520 serializes direction
before seconds. `XMLWindowData::Init` (0x989d30) initializes animation types
but not those parameter members. This supports inactive uninitialized data as
the explanation; it is not a reason to normalize or discard the original bits.

Neither plausible values nor an unchanged byte roundtrip proves schema correctness.
Opaque tails, unvisited branches and unknown semantics require explicit tracking.
Complete support requires native-reader or equivalent independent layout evidence,
full parsing of normal/Classic samples, controlled edit validation and regressions.

## Protected native modules

Core, Engine and NWindow DLLs in all supplied profiles have `.ncg0`–`.ncg6`
sections. Protected-module research on working copies was explicitly authorized.
The 32-bit Windows loader probe now successfully loads working-copy DLLs,
including TLS initialization, and captures memory-layout images (offset = RVA).
Essence, Korea and HF captures reported zero unreadable pages. These images are
private research artifacts, not rebuilt PE files or distributable dependencies.

Static inspection of Essence NWindow shows a large high-entropy `.ncg0`, an
obfuscated entry stub, and a visible import table containing only
`USER32.MessageBoxW`. Its 8276 exports retain useful names, including
`UWindowHandle::execLoadXMLWindow`, `execSaveXMLWindow` and
`execSetXMLDocumentInfo`. These identify investigation targets, not recovered
serialization routines by themselves. Linear disassembly of the entry stub is unreliable
because jumps cross junk/overlapping instruction bytes.

Native anchors (RVAs in the captured Essence module): root serializer 0x92c280,
LoadXdat 0x92c980, base properties 0x983e20, Window 0x98a200,
HeadDisplay 0x958e30, ScalableData 0x939140. Korea's CharacterViewportWindow
serializer is 0x93a740; its UseBackbuffer setter at 0x93aedd writes object +0x100.

Native probe constructor/serializer RVAs (thiscall ABI): Essence
0x931050/0x92c280, Korea 0x921520/0x91c770, Japan 0x931460/0x92c690.
See `XDAT_LEGACY_TAILS.md` for probe build/run instructions; omit `--stack-ctor`
for these three profiles. RVAs must be verified against the exact module hash.

## Reproducible profiles and verification

`tools/build_native_profiles.py --update-builtin` regenerates both profiles from
the unchanged bundled Salvation baseline. It requires no private binaries or
draft files. Original catalog records remain unchanged; 144 new records were
added under distinct namespaces. Standard schema selection/detection and
import/export apply to these profiles.

`tools/create_native_fixture.py --schema essence_native.XDAT --output <fixture.xdat>`
creates original synthetic data with all 41 controls, byte boundaries 0/128/255,
populated ListCtrl/RichListCtrl columns, two default-position groups, optional
FontDefinition, and HeadDisplay draw types 0/1/2/3. Both profiles' fixtures were
accepted to EOF by their own native readers; the Essence fixture also passed
Japan's reader. See `evidence/native-branches-*.json`. Individual default-control
fixtures for all 41 Essence controls also passed independently.

Windows x64 Release rebuild passed. Full Windows tests: 171 passed, 29 skipped,
20 subtests; subsequent focused schema/GUI checks: 34 passed (including both new
profiles opening, editing and Save As). Linux focused native/tail/byte/research
checks: 30 passed. All 27 independently supplied old XDAT fixtures passed binary
and JSON roundtrips after integration. The six new real samples passed editor
roundtrip/edit/undo using the integrated catalog (`evidence/editor-*.json`).

Remaining work: full game startup/rendering with edited files, exhaustive enum
and runtime semantic documentation, and identification of the legacy trailer
writer. The supplied Essence and Japan datasets contain only `system`; Korea
contains `system` and `SysTextures`, so full matching client assets are not
available for those visual checks. Native archive validation is completed but
must not be reported as a full in-game UI test.

JSON export now uses compact formatting to avoid indentation-driven growth in
deep UI trees. JSON import/export share a 512 MiB text limit; the binary limit
remains 256 MiB. Existing formatted JSON remains readable. Both Linux and Windows
cores were rebuilt after this correction; the focused Windows JSON/native/tail
suite passed 39 tests before the additional file-limit checks. The Linux suite
including those checks passed 41 tests. All six real normal/Classic files then
passed JSON-to-XDAT byte-identical roundtrip as well as binary roundtrip,
edit/reload and undo; updated results are in `evidence/editor-*.json`.
Those reports retain the catalog hash used for the audit, before protocol numbers
were added to the display labels. Reconstructing the earlier labels reproduces
that hash in the published new-client-support revision. The subsequent legacy
trailer investigation additionally annotates the `ct24`/`ct26` tail operations;
it does not change the Essence/Korea/Japan layouts. See `XDAT_LEGACY_TAILS.md`.

Final pre-publication Windows run after the protocol-label update: **175 passed,
29 skipped, 20 subtests passed**. The external 27-file integration set is opt-in
and was verified separately as described above. uExplorer package-token CTests
also passed on Linux and Windows x64 Release.
HF/Gracia trailer investigation is tracked in `XDAT_LEGACY_TAILS.md`.
Client binaries, decoded packages and memory dumps must stay
outside tracked/public content. Publish only anonymous commands, hashes and derived
format evidence.
