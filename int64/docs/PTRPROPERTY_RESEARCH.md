# PtrProperty interoperability research

## Pointer-limit follow-up

Three separate contracts are being closed: modern nonzero values, legacy runtime
availability, and replication rejection. The corrected numeric-contract fixture
passed in both modern clients: 25 PASS / 0 FAIL / 0 SKIP. Reports match their
build identities and all installed artifact hashes. Nonzero distinct addresses,
typed copying and clearing copies while retaining native owner payloads are
client-verified. The new screenshot for the second profile also confirms the
total; no new screenshot was found for the first profile. Two clicks were
user-confirmed, but only final reports are available for comparison.

This pointer milestone is complete within the agreed scope. Legacy pointer
support is not required for the two checked profiles because their Core binaries
lack native PtrProperty exports. Pointer replication implementation is deferred;
the compiler rejection remains in place. Neither item blocks this milestone.
The results below distinguish these
boundaries from the successful modern pointer execution. Earlier failed runs
are retained as research history rather than reclassified as successful runs.

### Context expressions

Using a native object's `pValue` exposed an SDK compiler defect that the earlier
self-field/local tests did not cover. FPropertyBase uses a scalar-size lookup
table, while the pointer descriptor has the private tag `0x505452`. A direct
object context initially produced an incorrect size diagnostic; after intercepting
the out-of-line size function, an inlined context path still indexed the table
with that tag and caused an access violation. A debugger run located this second
path at Editor RVA `0x79AA2`.

The fix checks and intercepts all seven reads of that exact table in the supported
SDK (`0x6F8EA`, `0x77334`, `0x774FD`, `0x77D1C`, `0x79934`, `0x79AA2`,
`0x84AAA`). Only the private pointer tag receives scalar size four. Other types
execute the original instruction, flags and non-result registers are preserved,
and surrounding code still applies ArrayDim. Generated code is made executable
read-only after initialization. No descriptor tag is serialized.

The pointer fixture now copies a nonzero marker through an object context and
tests a null receiver's pointer result. Exact source roundtrip and metadata
comparison passed, as did the existing native lifecycle/ProcessEvent checks on
the recovered package. Five compiler regression suites passed, including
ordinary expressions, metadata, Sort and replication controls.

### Replication boundary

Baseline experiments found that direct pointer replication was rejected but a
pointer-bearing struct and pointer-valued RPC parameters still compiled. The
guard now traverses struct fields (including inherited fields), array elements
and RPC parameter descriptors. It rejects pointer-bearing transmitted data.
All 45 negative pointer fixtures passed with the final compiler.
Object references do not transmit the referenced object's raw storage, and RPC
locals are not parameters: a positive control covering these distinctions passes
exact roundtrip and metadata comparison.

This establishes an explicit unsupported network contract, not pointer network
transport. The investigated modern SerializeItem implementation is empty, and
the inherited NetSerializeItem delegates to it. A successful serializer return
does not mean that a pointer value crossed a process boundary.

### Legacy capability evidence

`client_pointer_contract.py` copies DLLs into a new isolated workspace, loads
Core with initialization, and checks exported PtrProperty entry points against
a UIntProperty control. The two modern profiles expose all four checked
PtrProperty entries; the two legacy profiles expose none, while the control
resolves in all four. This is stronger than searching packed on-disk bytes,
which failed to enumerate modern exports correctly. Results include DLL/probe
hashes and full logs. It is evidence for these exact profiles only.

Legacy pointer support is unavailable in the current adapters. The SDK's
registered PtrProperty cannot establish a legacy client's native class contract.
Supporting it would require a separate, verified runtime class implementation;
an int/Object replacement would not preserve genuine PtrProperty. Legacy client
pointer tests therefore remain SKIP, not PASS.

### Modern nonzero client fixture

The new runner creates two native GFxValue owners, writes independent integer
values through their native methods, and reads their genuine `pValue` fields.
It requires nonzero distinct pointers, checks local/value/out/return and
field/struct/fixed-array copies, clears the copies, and verifies both owners
still hold their original values. Owners remain referenced throughout the test;
the runner never writes back to their native handles, invents addresses or
dereferences copied values. Four new checks replace the nonzero SKIP.
Expected modern totals are 25 PASS / 0 FAIL / 0 SKIP; this expectation is not
yet an actual-client result.

The first actual run produced 23 PASS / 2 FAIL / 0 SKIP on both modern profiles.
Build identities and all installed artifact hashes matched, and screenshots
confirmed the totals. Both failures included GetInt returning zero instead of
the two expected payloads. The intermediate copy check passed, but the combined
source check did not log its individual pointer predicates, so the complete
nonzero contract cannot be marked passed from these reports.

Inspection of client UI call sites showed an explicit AllocGFxValue /
DeallocGFxValue pair around value use. The first fixture had instead used bare
`new GFxValue`, whose sufficiency for native payload initialization was not
established. The revised fixture uses GFxUIScript's native allocation pair,
retains the original payload expectations, and logs each nonzero/distinct
predicate independently. It stops pointer-copy checks if source prerequisites
fail and deallocates owners after clearing copies. Runtime confirmation of this
correction was pending at that point; the earlier failed reports are retained as failures.

The allocation-pair revision produced 22 PASS / 1 FAIL / 0 SKIP in both clients.
Its individual predicates established nonzero, distinct source pointers, but the
payload expectation still failed and dependent copy checks were not executed.
Thus changing allocation alone did not explain the failure.

Initialized NWindow export inspection then identified the actual getter/setter
contract in both binaries. `execSetInt` converts its integer argument to double
and writes GFx value type 5. `execGetInt` writes its result only for type 3;
`execGetFloat` accepts type 5 and converts the stored double to float. On the
first profile these functions have RVAs `0x903360`, `0x9024F0`, `0x902410`;
on the second, `0x912F50`, `0x9120E0`, `0x912000`. The revised test retains
SetInt(73/91) and reads through GetFloat, with exact numeric expectations.
This corrects the fixture's native API assumption, not the client implementation
or the expected payload. The subsequent actual-client run passed on both profiles,
as recorded at the start of this report.

The export probe supports `--exports <DLL> <dependencies> <ASCII filter>` to
record bounded initialized export samples without invoking the methods. Local
evidence binds sampled logs to Core/NWindow/probe hashes; packed file export
enumeration alone is insufficient for these binaries.

Status: typed pointer fields, arrays, defaults, copies and function storage validated
in the SDK; modern client zero-pointer checks passed with artifact-bound reports.
This report records the research sequence, unsuccessful experiments, corrections,
and remaining compatibility limits. Client sets are identified by anonymous labels.

Current implementation preserves genuine PtrProperty metadata in ucc64 and
uExplorer. The expanded SDK fixture covers native/transient fields, fixed arrays,
direct/nested zero defaults, typed copies, locals, value/out parameters, returns,
contextual integer-constant zero and PointerEqual. The earlier declaration-only
external audit recovered 7,716 classes without partials or regressions; that audit
is historical evidence, not a full external audit of the latest compiler snapshot.
Earlier entries below describe intermediate states and superseded restrictions.

## Objective and boundaries

The investigation began with the UnrealScript declaration of
`NWindow.GFxValue.pValue` and expanded to the other observed pointer fields.
The implementation preserves genuine Core.PtrProperty identity and native
declarations/calls. Native C++ implementation recovery is outside its scope;
integer/Object substitution, field removal and native-layout changes were excluded.

The tested compiler is the existing x86 UE2 Runtime 2226 profile supported by
ucc64 (the launcher name does not imply a 64-bit compiler). Compiler binaries
are identified in `ABI.md` and `../README.md`. Client sets are labeled A/B/C and
use package profile 133/40. Original compiler/client directories are read-only;
all experiments use new isolated workspaces.

## Confirmed observations

### Package metadata

The three supplied modern client sets agree on:

| Property | Serialized type | Flags | ArrayDim | Extra serialized metadata |
|---|---|---:|---:|---:|
| NWindow.GFxValue.pValue | PtrProperty | 0x1000 (native) | 1 | none |
| Engine.Pawn.AnimData | PtrProperty | 0x2000 (transient) | 1 | none |
| Engine.MeshComponent.MeshComponentData.LinkedAnimData | PtrProperty | 0x2000 | 1 | none |

The serialized payload of pValue is `000000010000000010000000` (12 bytes).
These bytes are property metadata, **not a pointer value from process memory**.
uExplorer reads the common metadata through its end and preserves the raw bytes
in `unrecovered_properties` when source generation remains unsupported.

### Existing compiler experiment

The synthetic declaration below is a hypothesis probe, not established client syntax:

```unrealscript
class MetadataPointer extends Object native;
var native const transient pointer Handle;
```

With the SDK and the pre-extension ucc64 bridge, compilation failed with
`Unrecognized type 'pointer'`. The corrected launcher reports a nonzero exit
status and no output package is produced. Reproduction uses
`uExplorer/tests/compile_generation.py`, `tests/metadata_unsupported`, and
`--expect-error "Unrecognized type 'pointer'"`.

The SDK Core.dll export table contains UIntProperty/UProperty, but no
UPtrProperty or UPointerProperty symbols. The client Core.dll export tables
contain native UPtrProperty constructors, StaticClass, Link, SerializeItem,
ImportText, ExportTextItem, ExportCppItem, copy operations, and Identical.
This is evidence of a runtime type mismatch, not merely a missing parser keyword.

### Client binary limitations

All inspected client Core.dll files are x86 PE32. Export names are readable, but
bytes at the exported UPtrProperty method RVAs do not form plausible ordinary
entry-point code in the on-disk samples. Those code sections were treated as
uninterpreted/protected data. Calling conventions, field sizes and serialization
semantics could not be inferred from those bytes. A PE32 process does not prove that a property's
serialized value is a 32-bit integer.

### Related results already verified

- Within resolution and native/noexport class/property declarations are fixed in
  uExplorer; compiler roundtrip checks preserve the corresponding metadata.
- Primitive cast discriminator 57 is rotator-to-vector, independently compiled
  and compared with preserved ScriptText.
- 23 external packages in two modes show zero regressions and zero structural
  audit failures at this stage. PtrProperty was still explicitly partial.

## Initial research questions

1. Is the target UnrealScript spelling `ptr`, `pointer`, or a native-only form?
2. What property ID, alignment, ElementSize and flags does the client use?
3. Does SerializeItem serialize, skip, or reset pointer values? What are the
   constraints on defaults and script-level expressions?
4. How can the old SDK register and reload Core.PtrProperty without changing
   unrelated primitive types or native class layouts?
5. Which compiler declaration/type-construction paths need a narrowly scoped hook?

## Research method

The work proceeded through export inventory and input hashing, exact-SDK ABI
analysis, read-only live observation, isolated registration and persistence
experiments, compiler fixtures, and full generation audits. Each stage tested a
separate claim: registration alone did not demonstrate persistence, and a saved
declaration did not demonstrate value behavior. Positive and negative fixtures
and INT64 regressions preceded source-generation integration.

An integer-backed internal prototype is not sufficient evidence of client
compatibility. Renaming IntProperty in a final package without establishing
registration, reload and native storage semantics is not an acceptable solution.

## Experiment: isolated DLL initialization

Built `tests/ptrproperty_probe.cpp` with Visual Studio 2022, Win32 Release.
The probe reports 16 entry-point bytes without invoking property methods.
`--mapped` uses DONT_RESOLVE_DLL_REFERENCES; `--load` explicitly permits DLL
initialization. Each invocation runs in a separate process with a 20-second
timeout, using copied inputs in a local workspace. SDK dependencies were copied
alongside its Core.dll; client experiments used standalone Core.dll copies.

| Input | Mapped inspection | Initialized inspection |
|---|---|---|
| SDK | succeeds; UPtrProperty exports absent | succeeds; exports still absent |
| A | succeeds; protected-looking method bytes | process exits with code 1 |
| B | succeeds; protected-looking method bytes | process exits with code 1 |
| C | succeeds; protected-looking method bytes | process exits with code 1 |

All invocations completed within the timeout. The client initialized runs emitted
no post-load output or loader-error diagnostic. This does not establish the reason
for termination: missing runtime dependencies, required host initialization and
protection behavior remain possible explanations. It also does not establish that
the exports are callable after initialization in a supported client host.
Repeating with a flushed pre-load marker confirmed that all three client runs
reach LoadLibraryExW but never reach its return-path diagnostics. The SDK control
continues to succeed. The complete Win32 Release build and the existing
`int64_semantics` CTest passed after adding the probe.

Consequently, ordinary standalone LoadLibrary inspection has not supplied the
missing ElementSize, alignment, property ID or value-serialization semantics.
Compiler keyword support and uExplorer generation remained disabled at this
stage. The subsequent initialized-client observation supplied additional runtime
evidence that old-SDK registration analysis alone could not establish.

Build and invocation (placeholder paths):

```powershell
cmake -S int64 -B int64/build-ptrproperty -G "Visual Studio 17 2022" -A Win32
cmake --build int64/build-ptrproperty --config Release --target ptrproperty_probe
int64/build-ptrproperty/Release/ptrproperty_probe.exe --mapped D:/probe/Core.dll D:/probe
```

The `--load` experiment used a separate timeout-controlled process. Raw outputs
and copied binaries were retained in ignored local storage.

## Live client observation

Client A was started through its normal executable. A 32-bit module enumeration
found Core.dll, Engine.dll and NWindow.dll. ReadProcessMemory with read/query
access retrieved selected UPtrProperty entry points; no methods were called
and no client memory was modified. The bytes now contain ordinary x86 code.

- StaticClass returns the relocated PrivateStaticClass address (RVA 0x1f0308).
- SerializeItem at RVA 0xf1a20 starts with `ret 0x0c`: it immediately returns
  without serializing a value. Initialization/reset behavior remains unconfirmed.
- Link at RVA 0xf1a60 writes 4 to instance offset 0x44, computes
  `(outer_virtual_result + 3) & ~3`, and stores it at offset 0x54. This supports
  four-byte element size/alignment; field identities need independent confirmation.
- ExportCppItem was readable; its referenced string was inspected in the
  follow-up below. UnrealScript spelling remains unconfirmed.

The follow-up resolved that string, mapped property fields and the vtable, and
inspected GetID and defaults/copy methods before comparison with the old SDK.
Process IDs and relocated module bases were discovered separately for each run.

### Follow-up: C++ spelling and vtable

Reading the referenced UTF-16 literal confirms that ExportCppItem outputs
`FPtr`. This is C++ output, not evidence of the UnrealScript keyword.
The live vtable entries were matched against the on-disk export RVAs:

- Slot 32: UField::GetPropertiesSize, confirming the outer virtual call used
  by Link before rounding the offset up to a multiple of four.
- Slot 34: UPtrProperty::Link; slot 35: Identical.
- Slot 38: UPtrProperty::SerializeItem; slot 39: inherited NetSerializeItem.
- Slots 43/44: CopySingleValue/CopyCompleteValue; both copy four-byte values,
  with the latter iterating the count at instance offset 0x40 for arrays.
- Slot 45: inherited UProperty::DestroyValue.
- Slot 47: inherited UProperty::GetID, not a UPtrProperty override. Its return
  implementation was examined in the subsequent inherited-contract experiment.
- Identical compares four-byte values, treating an absent comparison value
  as zero. This confirms comparison behavior, not allocation initialization.
- ImportText calls a parsing helper and does not visibly store to the destination
  argument on its normal path. The helper and return contract need investigation
  before claiming support for pointer defaults.

Targeted method bytes remain local in `live-methods.json` beside the earlier
entry-point observations. No methods have been invoked in the client process.

### Reproducible probe and inherited contracts

`tools/probe_live_property.py` enumerates modules with Toolhelp, checks the exact
module path and on-disk SHA-256, opens only query/read access, and reads bounded
samples selected by export-name substring or RVA. It neither injects code nor
calls methods. Output uses exclusive creation so observations are not overwritten.
The probe uses Windows Python of matching or greater bitness than the x86 client.
The PID is supplied for each run; module base discovery is automatic. Samples
are retained as local research artifacts.

```powershell
python -B int64/tools/probe_live_property.py --pid <PID> `
  --core D:/client/System/Core.dll --sha256 <verified-sha256> `
  --symbol GetID@UProperty --size 64 --out local/get-id.json
```

Observed on client A:

- GetID reads `[this+0x24]`, then returns the byte at `[class+0x20]`.
  The PtrProperty UClass has name index 1369 (0x559), yielding 0x59 in this
  process; the UIntProperty control has index 2. This is not evidence of a fixed
  portable PtrProperty type ID. The implementation therefore retains dynamic
  name-based identification rather than hardcoding 0x59.
- DestroyValue is `ret 4`; it performs no destruction of the pointed-to value.
- NetSerializeItem calls virtual slot 38 (SerializeItem) with a zero size
  argument and returns 1. For PtrProperty this delegates to its empty serializer.
  This is an observation, not a recommendation to permit replicated pointers.
- The ImportText helper is the exported ReadToken at RVA 0xf00a0. ImportText
  passes a temporary UTF-16 buffer of 1024 characters, not its destination value;
  its normal return path does not assign the pointer. Text acceptance therefore
  does not establish initialization of a pointer from defaults.
- Default and C++ UPtrProperty constructors call UProperty constructors, zero
  the member at offset 0x80, then install their vtable. The copy constructor
  copies that member. This is property-object state, not the pointed-to instance
  value; instance allocation/reset still needs independent analysis.
- UProperty::Serialize writes ArrayDim at 0x40 and PropertyFlags at 0x48,
  consistent with the Link/copy field mapping and common package metadata.

The initial attempt requested an InternalConstructor export that is absent in
this client and failed explicitly before sampling; rerunning with actual exports
succeeded. Results: `live-contract.json` and `live-class-id.json` in local storage.

### Old SDK registration analysis

The native UClass constructor thunk at RVA 0x2b08 reaches RVA 0x2c6c0 and ends
with `ret 0x3c`. Its last two callback arguments are stored at UClass offsets
0x50c and 0x510; it initializes members through offset 0x51c. These observations
constrained the ABI, but alone did not establish a complete registration sequence,
object size, or the required lifetime of a bridge-owned native class.

Native registration and isolated construction/save/reload were investigated
before compiler keyword hooks. SDK and modern-client layouts were tracked
separately: ArrayDim is at SDK offset 0x34 versus client offset 0x40.
The eventual declaration syntax is an explicit extension; original-client
UnrealScript spelling remains unconfirmed.

### Native constructor queue experiment

Added the standalone Win32 `ptr_registration_probe` target. In an isolated
process using hash-verified copied SDK DLLs, it calls the exported native UClass
constructor before object-system initialization. Arguments mirror the SDK's
UIntProperty static initializer (RVA 0x7c210): EConstructorNative=0,
instance size 0x6c, flags 0x8000, UProperty superclass, the existing UIntProperty
Within pointer, zero GUID, a distinct PtrPropertyProbe name, Core package, empty
config name, object flags 0x04084004 and callbacks. Its instance callback rejects
unexpected invocation: this deliberately tests the constructor queue only.

Observed result: `queued=1 previous-link=1 property-size=108 guard=1`, exit 0.
The new object becomes GAutoRegister's head, links to the previous head, stores
the requested instance size, and does not overwrite a guard starting at 0x520.
This confirms this constructor call layout for the exact SDK, not complete class
registration or property behavior. The process does not call appInit, process
registrants, construct instances, save packages or enable source syntax.

SDK UObject native construction consults GObjInitialized and GObjNoRegister;
ConditionalRegister also expects membership in the registration bookkeeping.
The subsequent lifecycle experiment established initialization, registration and
instance construction before testing persistence. The queue-only probe remained
a standalone research target.

### Full initialization and genuine metadata persistence experiment

The standalone queue experiment was followed by `ptr_lifecycle_probe`,
an isolated DLL loaded by a copied, hash-checking launcher. It queues a native
class before initialization, hooks appInit, calls the original initializer, and
runs its checks only after the stock UCC initialization returns. It exits before
dispatching a commandlet. This avoids inventing a partial allocator/name/object
initialization sequence.

The integer registration control verifies that the class is discoverable as
`Core.PtrRegistrationControl`, GObjInitialized is set, GAutoRegister is empty,
and StaticConstructObject invokes the callback and preserves class identity.
Creating a property under a package was rejected: the inherited Within is Field.
Using a UField-derived outer passes.

Separate save/load modes register **Core.PtrProperty directly under UProperty**,
using UProperty's constructor and an independent vtable. The only reused integer
methods are four-byte Link, Identical, CopySingleValue and CopyCompleteValue;
the serialized class is never IntProperty. SerializeItem is empty, NetSerializeItem
returns one without changing the value, destruction is inherited/no-op, and GetID
remains inherited/dynamic. ExportCppItem writes FPtr. ImportText rejects input in
this experiment: original-client text/default initialization is still unresolved.
The empty ExportTextItem supplies no pointer-default fidelity; explicit pointer
defaults remain unsupported in the final declaration-only implementation.

Persistence is tested with a synthetic UStruct and one native pointer property:

- A new process saves PtrProbe.Holder.Value with dimension one and flags 0x1000.
- Another process registers the native class again and loads the saved property.
  It verifies exact class identity, metadata and instance-constructor invocation.
- Independent uExplorer inspection reports PtrProperty, no unread metadata and
  raw bytes `000000010000000010000000`, matching the observed client shape.
- Loaded-property checks pass for four-byte element size/alignment, scalar and
  three-element array copies with guard words, comparisons against null, empty
  serialization, network return, no-op destruction, and dynamic GetID.
- A further fresh process without PtrProperty registration cannot resolve the
  property. LoadPackage alone is insufficient evidence because loading is lazy;
  the negative test explicitly requests the property with StaticLoadObject.

The SDK compiler context matters: UCC chooses its commandlet/editor context after
appInit. This hook runs earlier and must explicitly set GIsEditor for the field
load. Without it the package handle exists but the field is not available.
UStruct also requires a non-None FriendlyName (SDK +0x44) before saving.

`tests/ptr_lifecycle.py` reproduces control, save, fresh-process load, independent
metadata inspection and missing-registration rejection, using a new directory
under uExplorer/local and exact Core/Editor/UCC hashes. The final run is recorded
locally in `ptr-lifecycle-9`; all stages pass. Observed GetID was 73 in that run,
distinct from the modern client's 89, confirming that the ID is environment-dependent.

This experiment established isolated registration, construction and metadata
persistence. Compiler integration and compiled-instance initialization were
tested in the following stage; modern-client package loading remains unverified.

Compiler follow-up has identified exact-SDK GetVarType at Editor RVA 0x7d490
(thiscall, five stack arguments, ret 0x14) and GetVarNameAndDim at 0x7e4e0
(nine stack arguments, ret 0x24). The former writes FPropertyBase and the latter
allocates concrete property classes through an explicit type dispatch. Adding
only a keyword or registering the native class therefore cannot be sufficient.
The following stage mapped FPropertyBase conversion and declaration-context
restrictions before implementing the narrow pointer extension.

### Compiler integration and declaration-only source extension

#### Function storage, null values and comparison completion

Plain `pointer` is accepted for function locals, parameters and returns; `out
pointer` is accepted for output parameters. Class/struct fields still require
native or transient. Function fixed arrays and optional/coerce forms are excluded
from the validated syntax. The SDK requests return-type lookahead in class scope
with null context and all disallow bits set; actual ReturnValue allocation occurs
under the function. Local flags are zero, value parameters 0x80, out parameters
0x180 and returns 0x580. Independent package inspection asserts these exact values
and genuine PtrProperty identity after export/recompilation.

The constant conversion hook admits only an integer constant with value zero into
a scalar pointer context; ordinary integer variables and nonzero constants remain
incompatible. The constant emitter writes EX_IntZero. Native/default text import
remains stricter about spelling and accepts the literal decimal `0` only.

`PointerEqual(A,B)` is a compiler intrinsic with two pointer-typed arguments
(contextual zero is permitted). It emits the verified four-byte equality native
154 and EndFunctionParms, returning Bool. It does not reinterpret either argument
as an integer descriptor or property. The exporter recognizes native 154 when an
operand has pointer metadata and recovers this intrinsic spelling. Ordinary `==`
overload lookup and pointer arithmetic remain unsupported. The intrinsic name is
reserved in primary-expression position, as INT64 is for the existing extension.

The full compiled fixture executes local-to-out copies, nested calls, pointer
returns, zero-initialized locals, indexed null writes and comparisons before/after
copying and clearing. ProcessEvent results and guard words distinguish equal,
unequal and null values. The compiler package is exported, recompiled and loaded
in a fresh process before these checks. Replication remains explicitly rejected.

Modern client runners add zero-storage, local/parameter/return/out, comparison and
indexed-null checks. Their separate nonzero-marker check remains SKIP: those
markers are established in the standalone SDK, not the client. Legacy runners
retain their profile-specific pointer SKIP. Actual client runs now pass on both
modern profiles (19 PASS, 0 FAIL, 1 SKIP) and both legacy profiles (12 PASS,
0 FAIL, 2 SKIP). The installed four-artifact hashes and report Build identities
match the new candidate manifests. Screenshots confirm the modern buttons and
visible totals and one legacy menu/total; the other legacy run has report evidence.
Two clicks per profile were confirmed by the tester. Only the report after both
clicks was supplied, so byte equality between first and second reports is not
claimed for this milestone. Stage 4 closes for the documented supported subset;
nonzero client pointer values, legacy pointer operations and replication remain
outside its verified runtime scope.

#### Typed pointer-copy expressions

FPropertyBase(UProperty*) now constructs a distinct bridge-only PointerType
descriptor for genuine PtrProperty fields, retaining ArrayDim and PropertyFlags.
No integer property or descriptor is substituted. Editor GetConversion at RVA
0x705a0 indexes a 14-by-14 table without bounds checks (lookup at 0x706cc), so the
conversion hook intercepts either pointer operand before entering that function.
It offers no conversion to or from other types. The overload-cost hook similarly
intercepts before the SDK and permits only matching pointer dimensions and valid
out/const qualifiers. The audited MatchesType routine at RVA 0x6fa10 compares
type and dimension directly; its special object/struct branches are not used by
PointerType.

The positive fixture copies scalar pointers, writes/reads an indexed pointer and
copies through a struct member between native and transient fields. Export and
recompilation preserve the checked metadata, bytecode PCs and symbolic ASTs.
The lifecycle probe loads the recompiled package and invokes CopyPointers through
ProcessEvent, then checks all four destination markers. GIsScriptable must be
enabled temporarily because the probe runs after appInit but before commandlet
setup; the initial call with that flag disabled did not execute script.

Negative tests reject pointer-to-string calls, integer returns, integer/object/None
assignment and scalar/array mismatches. Literal zero in function assignments is
still rejected; the separate defaults importer accepts zero. Locals, parameters,
replication, arithmetic and comparison support are not established by this step.
The earlier VM experiment below remains separate from compiled-source evidence.

#### SDK pointer expression VM experiment

The compiled-class lifecycle probe now exercises exported SDK VM handlers with
loaded Core.PtrProperty operands. A minimal FFrame has Code at +12 and Object at
+8. Operands contain live property addresses, as package relocation would supply;
they are deliberately constructed by the probe, not emitted by the compiler.

Verified operations are scalar InstanceVariable reads, Let assignment from another
pointer field, ArrayElement reads at index one, and Let of IntZero to that indexed
element. The checks require exact code consumption, a guarded four-byte result,
the copied marker value and unchanged adjacent array elements. This establishes
that these SDK VM paths can handle genuine PtrProperty storage without an integer
property surrogate. It does not establish client VM compatibility or source-level
pointer conversion rules. IntZero here is a VM operand, not permission to assign
arbitrary integers to pointers in source.

Compiler work must retain a distinct pointer descriptor. Existing rejection points
are field lookup, FPropertyBase(UProperty*) and GetIdentifier token handling.
Simply removing them is insufficient: the private PointerType is not a stock SDK
type index. Conversion selection, overload cost, expression matching and emission
must be audited before permitting it into those paths. Source pointer expressions,
locals, parameters and replication remain rejected during this experiment.

#### Explicit zero-default implementation evidence

The native ImportText override accepts the exact decimal literal `0` for direct
native/transient fields and fixed-array elements. It permits surrounding whitespace
and the comma/closing-parenthesis delimiters used by property importers, writes
exactly four zero bytes and returns the delimiter position after trailing whitespace.
Other spellings, addresses and expressions report an error and return null without
modifying the destination. This is extension syntax, not recovered client syntax.

The pointer fixture now includes direct native/transient defaults and indexed
array defaults. Compilation, export/recompilation and fresh-process instance
initialization pass. Explicit source zeros need not reappear in exported source:
the pointer serializer has no payload and zero is already the implicit default.
This establishes value equivalence, not source-spelling preservation.

Nested struct defaults are now supported. SDK UStructProperty::ImportText at Core
RVA 0x67ec0 checks slot 44 (UProperty::Port) before invoking slot 39 (ImportText).
Port at RVA 0x63dd0 rejects native/transient flags when the category is None.
The extension overrides Port for four-byte pointer properties with dimensions
1..2048 and supplies a matching ExportTextItem: zero exports as `0`; nonzero
values report an error and produce no address text. Archive serialization remains
the existing no-payload operation, and property flags retain their original values.
Nested negative fixtures now reach ImportText and reject nonzero/malformed values.

The compiled fixture initializes native/transient nested pointers and an indexed
array element alongside Count=7. A fresh-process native check invokes the stock
struct text exporter and importer, then explicitly imports all nested zero fields
over nonzero markers. Both paths reproduce the original twenty-byte struct.
The stock exporter omits zero fields against an implicit zero baseline, yielding
`(Count=7)`. An initial assertion requiring an explicit InnerHandle=0 in that text
was corrected after observing this behavior; value equality is checked directly.
All fourteen pointer cells remain zero and independent across instances, and
Count=7 survives package reload. Direct nonzero pointer export rejection is also
checked with guard words.

The updated negative compiler suite passes 22 cases. Native value-contract checks
also exercise accepted delimiters, guarded four-byte writes and failure without
mutation. Client pointer execution and expression support remain unverified.

#### Fixed-array implementation evidence

Fixed native/transient pointer fields now accept dimensions from 2 through 2048,
matching the SDK GetVarNameAndDim bounds (Editor RVA 0x7e6cd). Dimension parsing
uses the SDK integer/lexical-constant reader at RVA 0x76740, with the declaring
scope supplied as its third argument. Scalar fields retain dimension one; an
explicit `[1]` is rejected like an ordinary SDK fixed array.

The compiler writes the actual dimension into Core.PtrProperty, and the exporter
preserves the array declaration. The expanded fixture covers a named constant,
native and transient arrays, a scalar after an array in a shared declaration,
and an array inside a nested struct. Compile/export/recompile metadata and script
comparison passes. Sixteen negative cases pass, including invalid dimensions and
a missing closing bracket. All seven exporter CTests pass.

Fresh-process compiled-object checks validate four-byte element sizes, declared
dimensions, zero initialization of fourteen pointer cells, distinct per-cell
markers, and isolation from another instance and class defaults. Existing native
save/load, missing-registration and guarded copy contracts also pass. This is SDK
evidence; client pointer execution remains unverified. Explicit defaults,
expressions, locals, parameters and replication remain rejected at this step.

The probe uses fixed storage for its cell-offset list. A trial using std::vector
produced a fail-fast exit after the control success marker; its cause was not
established. Removing that dependency restored successful process exits across
all lifecycle modes. A success marker alone is therefore never sufficient.

The shared `src/ptr_property.cpp` module now supplies the native class to both
the actual compiler bridge and the isolated lifecycle probe. Registering it
before stock initialization preserves Core.PtrProperty identity across compiler
and fresh-process loads. The production source has changed; previously published
executables/portable artifacts have not been replaced.

Supported extension syntax (not claimed to be the original client's spelling):

```unrealscript
var native pointer Handle;
var transient pointer AnimationData;
```

Only scalar class/struct fields with exactly CPF_Native (0x1000) or CPF_Transient
(0x2000) are admitted. The expanded inventory found that GFxValue.pValue uses
0x1000, whereas Pawn.AnimData and MeshComponentData.LinkedAnimData use 0x2000.
Those flags are preserved; transient fields are not rewritten as native fields.

GetVarType recognizes the two explicit modifier/type sequences and emits a
bridge-only descriptor. Unmatched lookahead restores the SDK parser cursor and
delegates to the original method. GetVarNameAndDim creates a real PtrProperty,
preserves category, and appends it to the scope's child chain. No int/Object
surrogate is created, and the private descriptor is never serialized.

Early compiler trials corrected two assumptions. A non-null temporary argument
to GetVarNameAndDim did not mean the declaration was an array: the ordinary SDK
path discards that temporary and appends to the scope's own child chain. Rejecting
it had incorrectly rejected scalar fields. The first working native-only fixture
then recovered GFxValue but left the Engine fields partial. Inspecting their
metadata established the distinct transient flag and motivated the second
declaration form without changing the serialized flags.

FPropertyBase(UProperty*) at Editor RVA 0x722c0 is a closed class dispatch. The
bridge rejects pointer expression conversion before that dispatch. Field lookup
and GetIdentifier's GetToken call at return RVA 0x7c419 also reject pointer
references, including replication (which bypasses FPropertyBase conversion).
The SDK's normal handling of all other types remains in place.

An initial replication-negative fixture unexpectedly compiled successfully.
Tracing token consumption identified the GetIdentifier path above; adding the
targeted restriction converted that case into the expected compilation failure.

Positive compiler fixtures cover native/transient class and nested struct fields,
multiple names in a declaration, surrounding ordinary fields, a child class,
and ordinary script accessing the non-pointer struct members. All seven fixture
suites pass exact roundtrip checks with the final bridge. The pointer fixture
contains six pointer fields including inherited and nested fields.

Eleven negative cases reject arrays, locals, parameters, reads, writes,
replication, duplicate names and direct/nested pointer defaults. Direct default
rejection reports through GWarn and returns ImportText failure; appThrowf from
the defaults-import phase was experimentally unsafe outside the compiler catch
boundary. Nested defaults are rejected by the SDK's member importer. Each
negative test requires a matching diagnostic, nonzero exit and no output package.

The shared lifecycle probe also loads the compiled child class in a fresh SDK
process, creates two instances, checks all six pointer fields are initially zero,
and verifies writing one instance does not affect the second or class defaults.
This uses `-NoBind`, as the matching compilation SDK's Core.u contains declarations
whose native bodies are not in the old Core.dll. It establishes SDK storage and
initialization behavior, not execution of the modern client's native functions.

The first compiled-class load failed on a native export absent from the old SDK
Core.dll. Repeating the isolated storage test with `-NoBind` resolved that binding
mismatch without supplying or simulating the missing native implementation.

uExplorer emits `native pointer` or `transient pointer` only for the verified
metadata/context subset. Pointer expressions, unsupported flags/dimensions and
other declaration contexts remain explicitly partial with evidence preserved.
All nine previously pointer-blocked class/profile instances now recover without
issues in the targeted read-only check.

Validation completed:
- Seven uExplorer CTests and the INT64 semantics CTest pass.
- Seven compiler suites pass with `pointer-candidate-2`.
- Eleven negative pointer cases pass.
- Shared-runtime save/reload, missing-registration rejection and compiled-class
  zero-initialization/instance-independence checks pass.
- INT64 smoke bytecode, overloads, defaults and class-flag checks pass.
- Python unit discovery passes 15 tests; 21 external integration tests are skipped
  by their existing environment gates, not counted as passed integration checks.

Local evidence: `pointer-final-regression-*`, `pointer-negative-final-2`,
`pointer-runtime-shared-final-3`, `pointer-final-int64-smoke`,
`pointer-targeted-final.json`. Full `full-pointer-after.json` completed with
7,716 recovered, zero partial, zero diagnostics, zero regressions and zero
structural failures across 23 packages in two modes. Its recorded SHA matches
pointer-candidate-1's core, byte-identical to pointer-candidate-2's core:
`964dafdbfdab56d3d7abc69ccc075a21252461b59e17dba44e0a9f009221c7ce`.
The final bridge SHA-256 is
`5afe1e8a121e383104439ff2203db5ecfa288cc76e1ed731823766a767bc9b1f`.
This closes the discovered recovery backlog within the audited package set;
it does not establish in-game semantic equivalence or coverage of other packages.
