# Native compatibility research and standalone compiler handoff

## Scope and disposition

Native SDK/client compatibility repair is **outside the current full-package
decompile/recompile task**. It is deferred to a separate project. Its failures
remain FAIL/BLOCKED evidence, not exporter defects or successful compilations.
The current task can finish its agreed export and regression validation without
implementing a new native adapter or compiler. Essence remains separately deferred.

This document consolidates the established compiler, decompiler and DLL findings
needed to start that future project. Observations below are tied to particular
profiles and experiments. The design proposals are hypotheses, not implemented
solutions. Detailed research and executable controls are linked at the end.
Local inputs, binaries and reports are not distributed with this document.

## 1. Existing architecture

| Component | Actual role and boundary |
| --- | --- |
| `int64/src/launcher.cpp` | Launches the supported SDK compiler and installs the bridge; not a standalone UnrealScript compiler |
| `int64/src/editor_bridge.cpp` | Hooks the exact UE2 Runtime 2226 Editor ABI to extend parsing, type conversion, resolution and emission |
| `int64/src/ptr_property.cpp` | Implements the SDK-side genuine PtrProperty extension and associated compiler contracts |
| SDK Core/Engine/Editor DLLs | Perform native class registration, loading/linking, object initialization, compilation services and saving |
| `uExplorer/core/package.cpp` | Reads package structures, properties, functions and bytecode; audits supported profiles without executing client DLLs |
| `uExplorer/core/decompiler.cpp` | Recovers source, declarations, defaults, state/function control flow and symbolic references |
| `uExplorer/core/api.cpp`, `uExplorer/python/backend.py` | JSON/ctypes transport, source export and evidence capture |
| `dll/` | Client-specific native extension, VM/loader probes and profile tooling; not a replacement for Editor or a complete compiler |

The compiler bridge is **Win32/x86**, despite the name ucc64. The exporter is
built separately as x64. A 64-bit standalone compiler could emit a 32-bit client
format, but host pointer size must never implicitly define the target layout.

## 2. Current full-package evidence

The repaired active matrix completed 141 unique packages across four profiles:

| Profile | Packages | Recovered classes |
| --- | ---: | ---: |
| Korea290 | 45 | 19,312 |
| Japan230 | 43 | 18,869 |
| Gracia | 26 | 6,022 |
| HighFive | 27 | 7,424 |
| Total | 141 | 51,627 |

There are zero partial/failed class exports and three classless packages.
Original and frozen script hashes match for all 141 packages. Compilation totals:

| Dependencies | PASS | FAIL | BLOCKED | SKIP |
| --- | ---: | ---: | ---: | ---: |
| Original client packages | 4 | 9 | 125 | 3 |
| Rebuilt script chain | 4 | 5 | 129 | 3 |

Core compiles independently for all four active profiles. That does not establish
that its complete metadata or native layout matches the client. Failed Engine
prerequisites prevent evaluating many downstream packages' own compiler errors.
No actual clients were launched during this matrix. Historical client tests below
belong to their own artifacts, not these 141 newly recovered packages.

The matrix pinned an exporter preceding the indexed nested-default repair.
A separate full-package export validation of the newer exporter completed all
141 inputs successfully with unchanged input and exporter hashes. This does not
rerun compilation or resolve the native blockers. The newer isolated
regression snapshot passes 25/25 and C++ tests pass 7/7.

## 3. Established failure mechanisms

### Missing native metaclasses

Original Engine loading fails with `Assertion failed: MetaClass` while reading
`ClassProperty Engine.Engine.FlashDevice`, whose metaclass is FlashSubsystem.
Rebuilt Engine source fails with `'FlashSubsystem' is not a class name`.
Static exports expose UFlashSubsystem in Gracia's client Engine DLL, but not in
the pinned SDK Engine DLL. HighFive source compilation also cannot resolve
L2OrcMove. These findings do not constitute complete reconstruction of either
class's native registration, inheritance, size or implementation.

A declaration-only dummy may change the diagnostic, but does not establish the
original native contract. Native implementations cannot in general be recovered
from script bytecode: declarations/native indices refer to code residing in DLLs.

### Host and target object layout differ

Gracia Core.Object contains native integer fields IndexBuffer, HashNextBuffer
and CacheIndex absent from SDK Object. Their combined 12 bytes account for the
observed `Actor.Owner: Script=76 C++=64` discrepancy. This is an inherited-layout
barrier, not just a missing class name. Older Interface research separately
encountered `Script=60 C++=64`; those numbers describe a different input/profile.

Our own two-class ExtensionL2 package, included among HighFive inputs, fails
during matrix SDK initialization. A separate control with consistent SDK
Core/Engine compiles successfully. It does not prove original-dependency loading.
Historical Texture.Destroy/Material.ShaderCode faults likewise exposed client
Material layout incompatibility with the old native Engine.

Disabling checks or removing client fields would conceal the mismatch. A future
compiler must distinguish target metadata/storage from any objects used by its
host runtime, especially when importing defaults and constructing class defaults.

### Stripped dependency source is reparsed

Read-only TextBuffer inspection finds empty Object.ScriptText in Korea290 and
Japan230 Core. Gracia and HighFive retain nonempty text. Both modern-profile
original-dependency Engine logs enter `Parsing Object` and report
`Missing 'Class' definition`. This is consistent with reparsing the stripped
dependency text. The exact SDK decision that triggers reparsing is not yet mapped.
Recovered Object source itself compiles; rebuilt-chain Engine reaches the distinct
FlashSubsystem error. Replacing the original Core with rebuilt Core changes the
dependency experiment and must be reported as such.

### Resources and envelopes were separate barriers

Decoding recognized XOR111/121 envelopes in workspace copies removed the initial
package-summary assertion. Payload versions and metadata were not rewritten.
Resource-only name/import table validation passed for 5,433 files. This enables
dependency discovery, not texture/sound/mesh payload reconstruction. Gracia and
HighFive reassessment removed earlier unsupported-resource-table diagnoses;
remaining original-mode blockers refer to the independently observed SDK loader
failure (22 and 23 packages respectively). Input assets remain read-only.

## 4. Why Interface compiled successfully before

The earlier successful pipeline is real and is not invalidated by this matrix.
For one historical profile it compiled 253 classes and 3,792 functions with
0 errors and 35 warnings. All functions matched under the documented symbolic
instruction comparison, including its limited constant-conversion folding.
Historical validation records client loading and implemented-feature execution.
It does not establish equality of every default property or support for all clients.

`int64/tools/prepare_interface.py` used a deliberately adapted compiler workspace:

* A verified SDK Engine.u and Editor.u, rather than rebuilding client Engine.
* SDK Engine enums augmented with Actor.EL2ObjectType and Interactions.EInputKey.
* SDK Object native storage combined with client types/constants/functions via
  `object_with_runtime_storage`; this was not an unchanged client Core rebuild.
* NWindow/Interface sources from complete embedded ScriptText for that profile.
* Declaration normalization; `constructive` removed from the compiler copy only.
* Symbolic proxies for Vehicle.MaxFuel, CurFuel and DriverID. They do not join
  Children or change PropertiesSize; generated references resolve to client fields.

The game keeps its actual base packages and native libraries. This is a useful
script-targeting technique, not evidence that arbitrary client DLLs can replace
SDK DLLs or that client Engine can be rebuilt by the same host.

Later full-Interface MSVC/MinGW comparison found a bridge bug: reused bool tokens
retained an emission marker, omitting operands in 26 function payloads. Clearing
that marker fixed the observed case; rebuilt outputs differed only in their GUID,
and 1,215 bool comparisons had valid arity. That separate modern comparison must
not be conflated with the historical 253-class result or a new client run.

## 5. Compiler ABI and bytecode lessons

The supported Editor preferred base is `0x10200000`; documented addresses are
RVAs for that exact binary, not portable APIs. Verified examples include
GetConversion `0x705a0` (cdecl), ConversionCost `0x713c0` (thiscall), FindField
`0x74870`, GetToken `0x7b590` and CompileExpr `0x78430`. A recovered decompiler
signature omitted a GetConversion argument; stack/call-site inspection corrected
it. Using the wrong calling convention corrupts even ordinary expressions.

The bridge's Property descriptor is 20 bytes; Token is `0x8a4`, with a 64-code-unit
UTF-16 identifier and 2,048-byte value union. These are host ABI details, not a
required standalone compiler representation. Hook behavior is gated by verified
call sites; lookahead must not emit bytecode. Private token markers need explicit
lifecycle management, as the bool bug demonstrates.

Verified INT64 observations for the researched profiles:

* Primitive cast opcode is `0x39`; cast indices `0x5a..0x63` cover conversions
  between INT64 and byte/int/bool/float/string.
* Native operator indices 400..413 are confirmed by client initializer code.
* The bridge uses casts for constants rather than emitting direct token `0x46`.
* INT64 default storage uses high32/low32 ordering. Expression semantics and
  conversion priorities are covered by `int64_semantics.h` and compiler tests.
* Client array.Sort uses `0x47`; support is explicit and profile-gated. The plain
  SDK VM is not thereby made a general executor of client `0x46`/`0x47` bytecode.
* Script size and jump PCs refer to the **in-memory instruction representation**,
  not byte offsets in the compact-reference serialized stream. Decoders require
  instruction-boundary targets and full consumption of supported export bodies.

Optional-array arguments, qualified structures, scoped enum casts, enum name
collisions and client-specific enum values have dedicated controls. A future
frontend needs these actual language rules, not just the SDK's baseline grammar.
Source staging uses UTF-16 for the SDK; preserve text code points independently
of transport encoding. Unknown package/opcode profiles must fail explicitly.

## 6. Metadata is not just source syntax

SDK native saving changes metadata even without recompilation. The lifecycle
research separates file flags, post-Link flags, save/reload, construction and GC:

| Observation | Established result |
| --- | --- |
| Instanced reference compiled flags | `0x04000008` becomes `0x04400008` after SDK Link |
| Original GFxValue out reference | `0x00400180` becomes `0x04400188` after SDK save/reload |
| Class export flags | SDK save alone changes `0xE0004` to `0xF0004` |
| Class object bit `0x10000` | RF_LoadForClient, not an instancing bit or RF_Standalone |
| Modern client Link bodies | Include referenced-class instancing test absent in SDK Link |
| CopySingleValue | Copies a reference; template construction is a separate cloning operation |

Initialized modern client Serialize samples lack the SDK saving-time inline/export
OR. Native methods were inspected, not executed as a general client lifetime test.
Scalar template/GC probes do not establish array-element, out-parameter or full
Scaleform lifetime behavior. Full comparisons retained 782 class export-flag
changes, 80 property-flag changes, eight spelling changes and 12,369 added helper
identities in the researched Interface; these are not comparison exemptions.

A future writer must encode the target contract directly instead of assuming
SDK SavePackage is a fidelity-preserving backend. Preserving serialized masks
alone is insufficient without target load/link/construction validation.

## 7. PtrProperty and native DLL research

Genuine Core.PtrProperty identity is preserved. NWindow.GFxValue.pValue is native
(`0x1000`); other observed pointer fields are transient (`0x2000`). Serialized
property metadata is not a pointer address. Typed fields/arrays/structs, zero
defaults, locals, value/out/return parameters and PointerEqual have SDK controls.

The bridge's private pointer type tag `0x505452` exposed both out-of-line and
inlined scalar-size table accesses. Seven verified Editor sites needed handling;
only that private descriptor receives size four, and the tag is never serialized.
This demonstrates why adding a token or type name alone is insufficient.

Historical modern-client pointer fixtures passed 25/25 in two profiles with
nonzero distinct native handles and preserved owner payloads. Failed earlier
fixtures are retained: bare allocation was not an established GFx initialization
contract, and SetInt writes type 5 while GetInt accepts type 3; GetFloat reads the
tested type 5 values. Native API assumptions must be measured, not inferred from
method names. Pointer replication remains rejected, including nested structs,
inherited fields and RPC parameters (45 negative controls). An empty SerializeItem
and a successful NetSerializeItem return do not establish network transport.
Legacy pointer support is outside scope; two examined legacy Core profiles lack
the required exports and cannot inherit capability from the SDK extension.

DLL-level findings relevant to a future compiler/runtime toolchain:

* Disk bytes and initialized code differ in researched modern binaries. Store
  file hashes/export RVAs and loaded instruction fingerprints separately. Static
  inspection alone missed some capabilities in packed inputs.
* `dll/core_profiles.json` and generated adapters bind exact Core ABIs, exports,
  FFrame::Step fingerprints, string conventions and GNatives capacity. Adding a
  hash to a catalog is not proof of support for an unknown ABI.
* Isolated VM hosts verified instruction cursor behavior, INT64 ordering, result
  canaries, argument/result dispatch and extension registration across four profiles.
  Occupied native slots are not overwritten; temporary slots are restored.
* Gracia's 16-bit string exports use unsigned-short mangling, while HF uses
  wchar_t mangling. Equal code-unit width does not imply identical exported ABI.
* A historical wrong-Core deployment failed on GetCPUCacheLineSize/SetVGAInfo
  signatures. Using the client's matching Core resolved the mismatch; a one-name
  alias would not repair differing calling/return contracts.
* Loader adaptation preserves original sections/exports in copied binaries and
  adds extension loading. Successful Core+Engine loading and VM probes do not
  establish Editor compatibility or arbitrary game startup.
* All four supplied active client directories lack Editor.dll, UnrealEd.dll and
  ucc.exe. Client Core/Engine DLLs alone are not a complete compiler distribution.

## 8. Decompiler capabilities and remaining fidelity limits

The reusable reader includes symbolic name/import/export resolution, profile
validation, class/struct/state/function/property metadata and bytecode decoding.
The exporter can validate embedded ScriptText or force bytecode recovery. Repair
work established struct-owned enum emission, reference/name array defaults,
state labels across conditional regions, exact 131/40 support, corrected class
default access and indexed nested struct defaults (including index 129).

Zero reported export issues mean the implemented recovery completed; they do not
prove semantic or metadata equivalence. Branching recovery can introduce a PC
local/dispatch and helper metadata. A compiled branching probe therefore failed
exact AST/property-metadata comparison despite compiling successfully. Defaults,
replication, iterators, state labels, native indices and flags need independent
checks. Resource table support is not a resource writer. Decompiled source cannot
reconstruct arbitrary native DLL implementation bodies.

Delivery follow-up found a leading-argument omission bug in source joining:
`GotoState(, 'Open')` became `GotoState('Open')`. The correction preserves empty
argument slots; an all-package instruction audit located 18 affected calls.
Separately, two independent decoders confirmed that supplied High Five bytecode
already lacks required bool operands retained in its saved ScriptText. The user
build uses that saved source rather than guessing missing bytecode operands.
Future validation should distinguish syntactic decoding from call-signature
validation and explicitly record disagreements between source and bytecode.

## 9. Candidate solutions for a future project — not implemented

| Approach | Benefit | Unresolved requirement |
| --- | --- | --- |
| Matching client SDK/toolchain | Potentially matches native registration/layout | Obtain and verify the exact Editor/Core/Engine toolchain |
| Profile-specific SDK bridge | Reuses established frontend/backend | Complete mapping of affected host ABI, layout and saver behavior |
| Adapted SDK dependencies for script-only builds | Already demonstrated for particular Interface inputs | Per-profile symbol/type coverage and client validation; not full Engine rebuild |
| Separate host/target metadata models | Avoids executing target layout in host objects | Independent linking/defaults/serialization and target contract database |
| Standalone compiler and package writer | Removes dependency on SDK native loading/saving | New frontend, semantic analysis, emitter, linker and validated writer |
| Bytecode transplantation into originals | Preserves much original native metadata | Relocations, names/imports, function metadata, defaults and object graph integrity; narrower than full rebuild |

For standalone development, a useful design hypothesis is a pure target metadata
model with no required DLL loading during compilation. Explicit profile data
would describe native identities, type rules, opcodes and serialization. Original
package metadata can supply dependencies; required native-only declarations may
need additional verified descriptions. Keeping native implementations in client
DLLs is compatible with compiling scripts that reference them; reproducing the
DLL implementations is a separate undertaking.

## 10. Proposed development sequence and acceptance gates

1. **Freeze reference profiles.** Record package/licensee versions, envelopes,
   opcode capabilities, native tables, serialized masks and exact DLL evidence.
   Do not equate a package version with one universal native ABI.
2. **Build a read-only target model.** Reuse the reader and symbolic inspectors;
   represent owners, inheritance, property kinds/dimensions, function signatures,
   replication and state metadata without constructing SDK UObject instances.
3. **Implement a lossless supported-subset writer.** Test read/write/read and
   symbolic identity/metadata/default fidelity before introducing a frontend.
   Unknown payloads require explicit preservation or rejection, not zero filling.
4. **Implement parser and semantic IR.** Start with the existing synthetic suites;
   handle overloads, coercions, scope, optional/out parameters, native declarations,
   enum ownership, INT64 and pointer restrictions as distinct rules.
5. **Implement bytecode and relocation.** Track memory PCs separately from file
   offsets, resolve symbolic references and validate native-call arity, state
   labels, iterators, return boundaries and replication offsets.
6. **Implement target defaults and metadata linking.** Preserve field order and
   masks; model inheritance/default values without borrowing host object storage.
   Test target save/load behavior separately from SDK behavior.
7. **Validate a small script-only package against real dependencies.** Then a
   profile-specific Interface, then larger dependency chains. Investigate each
   newly exposed compiler failure before generalizing success across profiles.
8. **Run explicit runtime gates.** Structural reader, strict metadata/AST checks,
   supported SDK VM controls, target native probes and actual-client checks are
   separate results. Display client results and write System/test.txt; unavailable
   server/network behavior remains SKIP. Full native Engine rebuild is a later
   milestone, not inferred from a successful Interface build.

Required negative controls include unsupported profiles/opcodes, invalid compact
indices and jump targets, malformed metadata, missing imports, pointer-bearing
replication/RPCs and invalid implicit conversions. Compare MSVC/MinGW or other
host builds on identical inputs; report GUID/PE reproducibility separately from
symbolic or semantic agreement. No dummy native types, silent flag normalization,
field deletion or disabled layout assertions should serve as acceptance criteria.

## 11. Evidence and source map

These documents retain experiment-specific details and historical failures:

* [Full-package repairs](FULL_PACKAGE_REPAIR.md): repairs, matrix counts and boundaries.
* [Compiler ABI](../int64/docs/ABI.md): calling conventions, structures, verified RVAs and casts.
* [Interface blockers](../int64/docs/INTERFACE_BLOCKERS.md) and
  [validation](../int64/docs/VALIDATION.md): historical successful adapted pipeline.
* [Bool token reuse](../int64/docs/BOOL_TOKEN_REUSE_RESEARCH.md): cross-toolchain counterexample and correction.
* [Metadata lifecycle](../int64/docs/METADATA_LIFECYCLE_RESEARCH.md): exact masks, native differences and lifetime controls.
* [PtrProperty research](../int64/docs/PTRPROPERTY_RESEARCH.md): pointer ABI, initialized exports, failed and successful client fixtures.
* [Native profiles](../dll/NATIVE_PROFILE_RESEARCH.md),
  [Core profiles](../dll/CORE_PROFILES.md) and [HF ABI mismatch](../dll/CLEAR_HF_FIX.md): DLL evidence and adapter limits.
* [Regression/release workflow](ROUNDTRIP_RELEASE.md): verification layers and reproducibility constraints.

Implementation starting points: `uExplorer/core/{package,decompiler}.cpp`,
`int64/src/{editor_bridge,ptr_property}.cpp`, `int64/src/int64_semantics.h`,
`int64/tools/{verify_profile,prepare_interface,ue2package,compare_interface}.py`,
`uExplorer/tests/{compile_generation,compile_external,regression_snapshot,package_matrix}.py`,
`dll/core_profiles.json`, and the native/metadata/pointer probes linked above.

Local evidence, when retained in a development checkout: `uExplorer/local/pm-repair/`
(raw results, inputs, logs, manifests and reconciled results),
`uExplorer/local/pm-resource-recheck/`, `uExplorer/local/extension-sdk-control/`,
`uExplorer/local/repair-regression-indexed/`,
`uExplorer/local/indexed-package-validation/`, and
`uExplorer/local/final-validation/core-textbuffers.json`.
These ignored paths are evidence locators, not bundled prerequisites. Recreate
experiments from hash-pinned inputs when artifacts are unavailable. Check the
completion flag and tool hashes before using an in-progress report as evidence.
