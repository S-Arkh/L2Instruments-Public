# UnrealScript recovery research and validation

The completed audit recovered 7,716 class/profile instances with zero partial
results, diagnostics, regressions or structural failures. The chronology below
records the baseline, experiments, corrections and stage-specific validation.
Recovery status describes generation coverage, not in-game semantic equivalence.

## Scope and baseline

This ledger covers every diagnostic family observed in the completed five-profile
audit: 23 present packages in automatic and forced-bytecode modes. There are 25
profile/package slots, including two absent optional packages. This is not a
claim that every package in each client installation was scanned.

Baseline core SHA-256:
`9e77aca2481a549761c7b1a0a2055505321abbcf8d8e87b7b90a3f6e1b994b7d`.
Baseline audit file SHA-256:
`0833c2ffc4629fb23ba1d2dd30be7f5ee131c7c35aba83263812d0f85da111d9`.
Forced-bytecode totals: 7,353 recovered and 363 partial class/profile instances.

`tests/inventory_generation.py` creates an occurrence-level JSON backlog from the
audit, checks issue totals against individual class diagnostics, and replaces
profile labels with P1..P5. Example invocation with a new output filename:

```powershell
python tests/inventory_generation.py --audit local/metadata/after.json `
  --out local/metadata/unsupported-inventory.json
```

| Family | Diagnostic | Occurrences | Affected class/profile instances |
|---|---|---:|---:|
| Property types | PtrProperty | 9 | 9 |
| Defaults | Tagged struct (10) | 403 | 144 |
| Defaults | Tagged array (9) | 8 | 8 |
| Iterators | Unsupported iterator expression | 338 | 155 |
| Replication | Function replication declaration | 665 | 45 |
| Replication | Property replication declaration | 620 | 90 |
| Replication | Class-level script/replication | 110 | 110 |
| States | Ignore mask | 105 | 30 |
| States | Label/latent script | 75 | 35 |

Affected-class counts overlap and cannot be summed into a partial total. No unknown
cast/native/opcode diagnostic is present in this baseline. Function generation
stops at its first error, so an iterator can mask later unsupported statements.
The inventory was rebuilt after each family to detect newly exposed failures.
Structural decoding success also does not prove execution equivalence.

## Property types: PtrProperty

The sole explicitly unsupported property class in the baseline was PtrProperty:
GFxValue.pValue, Pawn.AnimData and MeshComponentData.LinkedAnimData in three
profiles. Live runtime and SDK registration findings are maintained separately in
`../../int64/docs/PTRPROPERTY_RESEARCH.md`.

The investigation covered actual native class registration, instance construction, package
save/reload in a fresh SDK process, compiler declaration support with explicit
operation restrictions, then uExplorer source generation. The initial queue-only
UClass experiment established only the constructor queue contract.

The subsequent isolated lifecycle experiment has now passed actual registration,
instance construction and genuine Core.PtrProperty metadata save/fresh-process
reload. Independent inspection confirms the original pointer property class and
observed metadata shape; a missing-registration negative case is rejected.
The subsequent compiler integration now supports explicit ucc64 extension syntax
`var native pointer` and `var transient pointer` for scalar class/struct fields.
Original flags are preserved: GFxValue uses native; the two Engine fields use
transient. Unsupported dimensions, flags, contexts and expressions remain partial.
The shared runtime, compiler roundtrip, eleven negative cases and fresh-process
initialization checks pass; see the latest pointer research section for details.
All nine previously blocked instances recover in the targeted recheck and full
pointer-stage matrix; client-game execution is not established.

## Defaults — full generation regression passed

An additional read-only pass over all 152 affected class/profile instances found:

| Struct name | Tags |
|---|---:|
| Color | 291 |
| RangeVector | 45 |
| Range | 35 |
| Scale | 15 |
| Plane | 10 |
| FresnelParam | 3 |
| RandomizerSoundDuration | 3 |
| DecalParam | 1 |

The eight dynamic array tags belong to KVehicle.ExitPositions (vectors) and
GameEngine.ServerPackages (strings). Color uses four raw bytes in B,G,R,A order;
Vector/Rotator use their existing binary representation. Other observed structs
use nested tagged members, including inherited Plane members and enum-valued
Scale.SheerAxis. No new compiler type registration is required for these defaults.

The candidate generator now supports these encodings, recursive struct tags,
enum-name lookup, and nonempty dynamic arrays with supported element types.
Unrecognized top-level tags retain structured `unrecovered_defaults` records
(type, struct name, index, raw bytes). Malformed nested data retains partial
status and the class tail. Empty dynamic arrays and indexed members inside tagged
struct defaults remain explicitly unsupported; neither occurred in this audit.

Compiler experiments found and corrected two issues:
1. The supported SDK does not trim whitespace after commas in struct ImportText.
   Generated struct defaults must use commas without added spaces. This also
   corrects the former Vector/Rotator default formatting.
2. Enum fields need symbolic enum members; emitting the numeric byte caused an
   ImportText failure. The generator resolves the property's enumeration.

Validation at the defaults stage:
- Four CTests pass, including hand-authored color/nested-tag fixtures, truncated
  payloads, missing nested terminators and unknown-tag raw preservation.
- `tests/defaults/DefaultProbe.uc` compiles, decompiles and recompiles without
  errors; metadata and canonical generated defaults remain equal. Values cover
  distinct color channels, nested structs, enums, booleans, vector/string arrays.
- Read-only recheck of all 152 previously default-affected class/profile instances:
  zero remaining default diagnostics; 127 are now recovered, the rest retain
  unrelated issues. This does not establish client runtime equivalence.
- Full 23-package/two-mode regression completed: zero regressions, zero structural
  audit failures. Forced-bytecode totals changed from 7,353 recovered / 363 partial
  to 7,480 recovered / 236 partial. No unsupported-default diagnostics remain.
  Engine partial counts changed from 74 to 47 in modern profiles and from 69 to
  46 in older profiles. NWindow PtrProperty status is unchanged.

Local reports: `defaults-inventory.json`, `defaults-after.json`,
`defaults-roundtrip-3/roundtrip.json`, and completed `full-defaults-after.json`
under `local/metadata`. Client inputs and detailed logs remain unpublished.

## Iterators — structured region reconstruction

Iterator functions use structured regions instead of inserting foreach into the
existing PC-dispatch loop. Entry/exit boundaries, trailing IteratorNext/IteratorPop,
continue sequences and return cleanup are checked explicitly. Supported regions
include nested foreach, if/else, while and verified switch case chains. Cross-region
branches and unverified cleanup fail explicitly and retain the AST.

Seven synthetic functions roundtrip with identical symbolic ASTs, PCs and flags:
simple iteration, break/continue, early return, nested iteration, nested-return
cleanup, mixed while/conditionals and switch with fallthrough/default. The first
external recheck eliminated 333 of 338 iterator diagnostics; the five remaining
Actor.DisplayDebug instances needed switch support. After that extension, those
five also generated without errors. First-error masking did not expose additional
failures in the combined recheck of previously partial classes.

CTest fixtures additionally reject incorrect iterator exit targets and return
without the required cleanup. Local reports: `iterators-roundtrip-2/roundtrip.json`,
`iterator-after-1.json`, `iterator-switch-after.json`.

## Replication — full generation regression passed

Function/property replication offsets are now retained instead of discarded.
The generator resolves each offset to a class-script expression boundary, groups
members by that offset, and preserves function reliability. Recovery is committed
only after all referenced conditions render successfully. Unreferenced class
script remains explicitly incomplete; the class AST is retained in the report.

The SDK compiler assigns 0xffff to inherited network-function overrides. These
are recognized only with a resolved super-function, matching name and matching
network/reliable flags. Such overrides inherit the declaration instead of
creating a new condition in a child class or state.

The synthetic replication fixture covers three distinct conditions, multiple
properties sharing a condition, reliable/unreliable functions, a child override,
and an override inside a state. Four functions roundtrip with matching function
ASTs, flags, offsets, property metadata, defaults and class condition ASTs.

Experiments corrected two additional issues:
- Dropping enum context from `Role == ROLE_Authority` changed conversion bytecode
  and subsequent condition offsets. Comparisons now preserve enum operands and
  symbolic constants so the compiler emits the original implicit conversions.
- A declaration-only state already receives an implicit Stop from the compiler.
  Emitting that Stop again duplicated it. A single Stop with no label table is
   now omitted from source; label/latent reconstruction is described below.

Read-only recheck of all 115 replication-affected class/profile instances found
zero remaining replication diagnostics. This is generation coverage, not an
in-game networking test. Five CTests passed at this stage, including invalid replication-offset
and truncated metadata checks. Defaults, five metadata/native functions and eight
delegate/new functions also pass compiler regressions with the replication build.

The full replication-stage audit completed on 23 packages in two modes: zero
regressions and zero structural failures. Bytecode totals are 7,535 recovered /
181 partial, compared with 7,480 / 236 after defaults. This snapshot predates
iterator and state reconstruction; the combined audit remains separate.

Local results: `full-replication-after.json`, `replication-after.json`, `replication-inheritance-3/roundtrip.json`,
and `replication-regression-{defaults,metadata,generation}/roundtrip.json`.
Separate immutable snapshots distinguished this stage from the defaults-only audit.

## States — ignore masks and label/latent bodies

Read-only inspection of client A confirmed that execEnable uses name indices
300..363. The FName table supplied the corresponding probe names; reserved slots
and the aggregate All slot are not treated as source events. Name resolution also
requires a matching function in the state/class inheritance hierarchy.

Comparison with preserved old-profile ScriptText exposed why a mask alone is
insufficient: non-probe ignored functions are stored as separate no-body function
declarations. These declarations remain in generated source, while probe bits
produce the `ignores` clause. Source inheritance and conditional source variants
also mean a textual ignores list is not always identical to a serialized mask.

The synthetic StateProbe covers low/high mask bits, a non-probe ignored function,
an inherited state and an auto state. Compile/decompile/recompile passes with
matching function ASTs and state flags, probe/ignore masks, label offsets and
script sizes. All 30 affected class/profile instances were rechecked: zero
remaining ignore diagnostics. Five CTests passed at this stage. The combined build/test wrapper
timed out after build output; a separate CTest invocation completed successfully.

Local results: `state-ignore-source-comparison.json`, `state-ignore-after.json`
and `states-roundtrip-final/roundtrip.json`. The replication audit used an earlier
immutable snapshot; the later combined audit validated the ignore changes.

Label tables now delimit state-code regions, preserving labels, goto expressions,
latent calls, structured branches/loops and explicit Stops. Only the compiler's
implicit final Stop and label-table alignment padding are omitted. Label targets
must be executable statement boundaries, and the serialized label offset must
match the table. Aliases at the same PC are emitted in reverse table order because
the compiler prepends label entries; a compiler experiment caught and verified
this ordering requirement. State code is not moved into an ordinary function.

The expanded state fixture roundtrips complete state ASTs, including Sleep, goto,
while, label aliases, foreach followed by Sleep, auto/inherited states and ignores.
The SDK rejects Sleep inside foreach; a separate negative fixture confirms the
diagnostic and absence of an output package, and generation rejects that layout.
All 35 label/latent-affected class/profile instances generated without state-code
errors. CTest covers malformed label targets/table offsets and preservation of
the original state AST. Results: `latent-roundtrip-final/roundtrip.json`,
`latent-iterator-negative/compile.log`, `latent-after-1.json`.

## Combined pre-pointer audit

Rechecking all 363 baseline partial class/profile instances yielded 354 recovered
and nine partial, all exclusively due to PtrProperty. Seven CTests passed.
All six compiler fixture suites pass against an immutable
`local/metadata/combined-candidate-1` core snapshot. The complete 23-package,
two-mode matrix has completed with zero regressions and zero structural failures.
Forced-bytecode totals are 7,707 recovered / nine partial (baseline: 7,353 / 363).
The only remaining diagnostic at this stage was unsupported PtrProperty, with nine occurrences.
The report's core SHA-256 matches the immutable snapshot:
`d66b86b4611a99774c400aa0584766cd60056acd4a942d2cb47882ae9f128362`.
This validates recovery coverage, not client runtime semantic equivalence.
Reports: `combined-partial-recheck.json`, completed `full-combined-after.json`,
and completed `combined-regression-*/roundtrip.json`.

## Pointer-stage validation update

Seven compiler suites now pass with the pointer-capable ucc64 bridge, including
native/transient pointer fields inside classes/structs and inherited storage.
Seven CTests and the INT64 semantics/smoke regressions pass. The full matrix passed
on the immutable pointer-candidate-1 core (identical to pointer-candidate-2's core):
**7,716 recovered / zero partial, zero diagnostics, zero regressions and zero
structural failures**, across 23 packages in two modes. The report SHA was verified.
Final report: `full-pointer-after.json`. The
earlier 7,707 recovered / nine partial totals above belong to the pre-pointer
snapshot, not the latest targeted result. Distribution binaries remain unchanged.

## Research progression and limitations

| Completed stage | Recovered | Partial |
|---|---:|---:|
| Baseline | 7,353 | 363 |
| Defaults | 7,480 | 236 |
| Replication | 7,535 | 181 |
| Combined iterators/states, before pointers | 7,707 | 9 |
| Pointer declarations | 7,716 | 0 |

Each stage retained unknown data and used occurrence inventories and regression
comparisons to distinguish new coverage from suppressed diagnostics. Compiler
ABI experiments were validated separately from ordinary source generation.
Native declarations and calls remain represented; native C++ bodies were outside
the recovery scope. The final result applies to the 23 present audited packages.
Original-client pointer spelling, other package sets and modern-client in-game
semantic equivalence remain unverified.
