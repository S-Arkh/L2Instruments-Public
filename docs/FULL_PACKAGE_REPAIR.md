# Full-package repair evidence

## Scope update

Native SDK/client compatibility repair is deferred to a separate project and is
not a completion requirement of this task. Findings, the previously successful
adapted Interface pipeline, DLL research and a standalone compiler development
handoff are consolidated in
[Native compatibility and compiler design](NATIVE_COMPATIBILITY_AND_COMPILER_DESIGN.md).
Existing FAIL/BLOCKED outcomes remain unchanged; this is a scope decision, not a
claim that native compatibility has been repaired.

## Dependency isolation and SDK loading

The baseline covers 184 packages across five profiles. Export produced 144
nonempty packages without reported issues, 35 partial packages, four packages
without script classes and one unsupported profile. This is coverage, not a
successful whole-client rebuild.

The matrix accepts repeated `--asset-root Label=directory` arguments. Required
resource dependencies are hash-pinned separately and reused in the rebuilt
chain. Each compilation materializes verified isolated copies, bounding disk
usage rather than retaining another full resource installation. Only script
packages enter `EditPackages`. Original inputs remain intact.

The SDK workspace removes recognized XOR envelopes while preserving the complete
serialized payload. It does not rewrite package versions, native declarations or
metadata. Three dependency contract tests pass, covering envelope fidelity,
transitive resource cycles and separation of resources from rebuilt scripts.

An isolated SDK probe across all five profiles eliminated the previous package
summary assertion after envelope decoding. All five then stopped at the
`MetaClass` assertion for `Engine.Engine.FlashDevice`. SDK compatibility is still
blocked; this is not a source compilation failure or a completed compatibility
repair. A future separate investigation must resolve the referenced metaclass
without substituting a different native contract.

Actual-client execution is reserved for the final validation stage with user
participation. SDK probes do not establish client compatibility.

## Struct-owned enums

The exporter now emits a struct-owned enum inline on its first direct byte
property, retaining the enum owner and reusing the declaration for later fields.
Enums without a suitable direct field remain explicitly incomplete.

All five original Core profiles now export eight classes without issues and
compile successfully in isolated SDK workspaces. Enum paths and values match
the originals in all five profiles; the three `Object.Scale` property metadata
rows also match, excluding raw serialized index bytes. This focused comparison
does not establish equivalence of the entire Core package.

The synthetic struct-enum roundtrip passes compilation, requested metadata and
default-block comparison. All seven C++ regression tests pass. An expanded
fixture exposed a separate existing limitation: indexed nested struct defaults
were not supported at that stage. The subsequent indexed-default repair is
validated separately below.

## Reference and name array defaults

Object, class and name array elements now decode against the package containing
the default payload. Null references and element ordering are retained. Nested
generic declarations separate closing angle brackets for the SDK lexer.

A synthetic roundtrip with object/class references, intervening nulls and names
passes recompilation, metadata and canonical default-block comparison. One
previously affected class from each of the 30 array-default-affected packages
now exports without issues. This sampling is not a complete export audit or a
compilation claim for those external packages; full validation remains pending.

## State control flow across labels

The reported iterator-boundary error in `ScriptedController.Scripting` came from
splitting state code at labels inside conditional regions. The exporter now
structures the full state body and emits labels at their statement boundaries.
Labels on elided control-flow instructions remain explicitly unsupported.

The synthetic nested-label fixture recompiles with matching state ASTs, PCs and
requested metadata. All seven C++ regression tests pass. ScriptedController
exports without issues in all five external profiles. Actual execution of those
external states has not been validated.

## Package profile 131/40

The original IpDrv package passes structural validation of 466 supported exports
with zero failures; all 14 classes export without issues. The reader accepts
the exact profile pair, while rejecting neighboring unverified profiles and
keeping modern INT64/Sort opcode support gated to its existing profiles.

Compilation exposed a separate source-emission defect: class default access was
incorrectly prefixed with `static`. Correcting this allows IpDrv to compile
against the pinned SDK Core/Engine. Linear class-default probes pass AST, PC,
metadata and default-block roundtrip checks. The first branching probe compiled
but did not match AST/property metadata because the existing function recovery
adds a program-counter local; it is not evidence of exact equivalence.

The seven C++ tests pass for the profile-reader change. IpDrv compilation against
SDK dependencies does not establish compatibility with original client Engine
or prove runtime/network behavior.

## Expanded regression gate and full-matrix preparation

The expanded hash-bound regression snapshot passes 24 of 24 checks, including
the four new suites, SDK VM semantics, pointer lifecycle and metadata lifecycle.
All tracked inputs and copied tools remained unchanged during that run.

Resource staging recognizes verified filename-keyed XOR envelopes as well as
the fixed-key envelope. Resource basenames need not be script identifiers.
Conflicting package roots are recorded as affected-package dependency blockers;
the runner does not silently select a conflicting asset. Preparation failures
can be resumed without repeating completed profiles. Export caches require an
exact exporter-binary hash match in addition to input/source integrity checks.

The repaired active matrix is complete, as summarized below. Essence is deferred at the user's
request until its resources are available. Its completed evidence is retained;
the active scope is 141 packages across the other four profiles.
An independently observed SDK Engine loading failure can block downstream
attempts with a reference to its evidence log. This avoids repeatedly staging
large resource sets for a known failed prerequisite; it is not a successful
compilation result.

## Resource dependency table validation

The resource-only import reader now accepts the additional observed header
profiles without enabling script or resource payload decoding for them. Name
and import table validation completed without errors for 5,433 resource files:
Korea290 1,691; Japan230 1,701; Gracia 960; HighFive 1,081. Four dependency unit
tests pass, including profile separation and malformed-table rejection.

The earlier Gracia/HighFive matrix entries blocked on unsupported resource
table profiles predate this repair. They require dependency reassessment; they
must not be relabeled as successful compilations based on this table audit.

## Native SDK compatibility controls

Static export inspection finds `UFlashSubsystem` exports in the Gracia client
Engine library but not in the pinned SDK Engine library. HighFive Engine source
compilation also fails to resolve the native class `L2OrcMove`. These findings
support a native-surface compatibility problem, not merely missing assets.

ExtensionL2 is the project's own two-class test package found among the supplied
HighFive files. Its matrix failure occurs during SDK initialization with an
Actor.Owner script/native offset mismatch. A separate control using consistent
SDK Core/Engine dependencies exports both classes and compiles successfully.
That control does not replace the matrix result using client dependencies.

Metadata inspection also finds three additional native integer fields in the
Gracia Object declaration: `IndexBuffer`, `HashNextBuffer` and `CacheIndex`.
They are absent from SDK Object. Their combined size accounts for the observed
12-byte Actor.Owner offset difference. Native class registration alone therefore
cannot be considered a complete compatibility repair; inherited layout and
compiler-host object initialization must also be reconciled without discarding
the client fields or suppressing layout checks.

## Indexed nested defaults and dependency reassessment

Nested fixed-array default indices are now decoded with dimension bounds checks
and emitted using the SDK's struct field indexing syntax. A synthetic roundtrip
preserves integer values, an index of 129 and enum-array values, with matching
requested metadata and canonical default blocks. All seven C++ tests pass.
The expanded hash-bound snapshot passes all 25 checks, including SDK VM
semantics and lifecycle contracts. Tracked sources, SDK inputs and copied
tools remained unchanged during the run.

The Gracia and HighFive dependency reassessment reuses hash-verified generated
sources with the same exporter binary. No unsupported-resource-table blockers
remain. Original-dependency compilation is still blocked for 22 Gracia packages
and 23 HighFive packages by the independently reproduced SDK Engine loader
failure. Successful resource discovery must not be presented as a compilation
or native compatibility fix.

## Completed active matrix

All 141 active package records are complete and unique. The four profiles
recover 51,627 classes with zero partial or failed class exports; three packages
contain no script classes. Original and frozen script hashes match for all 141
packages. Aggregate and per-profile result files report completion despite
intermediate report replacement failures; recovery evidence is retained.

| Profile | Packages | Recovered classes |
| --- | ---: | ---: |
| Korea290 | 45 | 19,312 |
| Japan230 | 43 | 18,869 |
| Gracia | 26 | 6,022 |
| HighFive | 27 | 7,424 |

Original-dependency compilation totals are PASS 4, FAIL 9, BLOCKED 125, SKIP 3.
Rebuilt-chain totals are PASS 4, FAIL 5, BLOCKED 129, SKIP 3. The reconciled
evidence uses the completed Gracia/HighFive resource reassessment for dependency
diagnoses while preserving the main run. Export success does not close the
native compatibility repair or establish client execution equivalence.
This matrix uses the exporter pinned before the indexed nested-default repair.
The independent full-package export validation of the newer binary subsequently
completed all 141 inputs without partial or failed exports. All input and exporter
hashes remained unchanged. This is export validation, not a rerun of compilation.

## Original Core source availability

Read-only inspection of serialized TextBuffer exports finds an empty
`Object.ScriptText` in both Korea290 and Japan230 Core packages. Gracia and
HighFive retain nonempty Object source text. The Korea290 original-dependency
Engine log explicitly enters `Parsing Object` and fails with `Missing 'Class'
definition`. This is consistent with reparsing stripped dependency source,
rather than a missing declaration in the newly exported Object source.
The rebuilt-dependency attempt reaches the separate unresolved FlashSubsystem
error. Neither replacing original Core with rebuilt Core nor supplying invented
native declarations would establish original-dependency compatibility.

## Interface delivery follow-up: omitted arguments and input provenance

Adapted-SDK Interface compilation exposed a source-emission defect not exercised
by the original/rebuilt-chain matrix: the string join helper omitted a leading
separator when its first argument was empty. Gracia's saved call
`OptionalValues(, 7)` therefore became `OptionalValues(7)` in bytecode recovery.
Joining by element index preserves argument positions. Fixtures cover one and
two leading omissions plus the existing interior omission; strict roundtrip,
seven C++ tests and the complete hash-bound 25-check regression pass.
An instruction audit across all 141 frozen packages checks 121,910 functions and
states without decode errors and identifies 18 affected calls in ten classes
across six packages. All ten affected classes were re-exported with before/after
evidence. This includes GotoState calls where dropping the leading omission
changed the meaning from a label argument to a state argument; successful source
compilation alone would not catch that semantic change.

High Five has a different input problem. Two independent decoders find only two
operands followed immediately by EndFunctionParms in two InventoryWnd calls to
RequestGetItemFromPet. Its NWindow declaration requires a third bool argument.
Saved ScriptText supplies false and true respectively; other calls retain their
bool operands in bytecode. This establishes a source/bytecode discrepancy in the
supplied package, not a justification to invent an operand during recovery.
The symptom is consistent with the earlier bool-marker issue, but the exact
historical build provenance of this input has not been independently established.

Japan's original Engine EL2ObjectType has the same ordered seven names and numeric
values as the existing historically named korea290 compiler enum profile.
Portable profile selection therefore enables that verified enum extension for
both supplied modern profiles. This changes compiler-side enum preparation,
not client native storage. Compilation using saved source and compilation using
forced-bytecode recovery are recorded as distinct evidence.

## Completed adapted-SDK Interface delivery checks

The four full Interface builds now pass through the portable build script using
profile-specific compiler dependencies. This is a third mode, separate from the
original-dependency and rebuilt-chain matrix; their earlier results are retained.

| Profile/protocol | Source basis | Classes | Errors | Warnings |
| --- | --- | ---: | ---: | ---: |
| Gracia / 152 | Saved ScriptText | 241 | 0 | 3 |
| High Five / 268 | Saved ScriptText | 255 | 0 | 34 |
| Japan / 591 | Repaired bytecode recovery | 794 | 0 | 65 |
| Korea / 606 | Repaired bytecode recovery | 782 | 0 | 60 |

All four produced packages pass the supported structural audit and retain the
original class inventories and inheritance. Sources, compiler dependencies and
SDK/tool inputs remained unchanged during the builds. The actual delivered High
Five output contains all four required bool arguments in the checked PetAPI calls.

Symbolic class/state/property inventories (excluding raw serialized reference
bytes) match for Gracia and High Five. Japan has 876 changed rows, eight
original-only identities and 12,261 compiled-only identities; Korea has 862,
eight and 12,377 respectively. These differences remain visible and include SDK
metadata policies and generated helpers. This comparison is not a full-package
or semantic equivalence certificate, even where the inspected inventories match.

The minimal user workspace retains sources, necessary compiler dependencies,
compiler binaries, launch scripts, licenses, concise instructions and build
status. Research, reference originals and validation artifacts are stored outside
the user bundle. The final CMD wrapper passes a relocated short path containing
spaces and non-ASCII text with restricted PATH, and propagates a failure without
replacing an earlier successful artifact. A deeper-path probe failed under the
old SDK's path limitations and is retained as failed evidence; short paths are
documented as a requirement. Manual client checks are deferred to the final
user-assisted stage. No new actual-client execution is claimed.
