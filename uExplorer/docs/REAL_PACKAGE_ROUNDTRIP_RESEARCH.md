# Real-package roundtrip research

## Stage-five validation in progress

The production API accepts `bytecode_profile="sdk-client-sort"` only for
SDK header 126/0. It enables opcode 0x47 without rewriting the package header;
opcode 0x46 remains rejected. The default profile stays strict, and API cache
identity includes the profile. Production roundtrip, metadata comparison,
profile switching, unknown-profile rejection and input hash checks passed.

The Sort rejection suite contains twelve actual source fixtures, including
optional/coerce comparator parameters and attempts to consume Sort as a return
value or an out argument. All twelve passed their specific diagnostic and
no-output-package checks. Empty and singleton Sort passed in both modern
clients, including one-time receiver evaluation and zero comparator calls.
All four new client reports match their build identities and installed artifact
hashes: modern totals are 21 PASS / 0 FAIL / 1 SKIP; legacy totals are
12 PASS / 0 FAIL / 2 SKIP. Screenshots confirm the buttons and totals.
Two clicks were user-confirmed; only final reports were supplied, so no
first/second report byte-equality claim is made. The metadata investigation is
now concluded with the incompatibility boundary described below.

The semantic fixture executes ten independently specified cases in both the
original and recovered packages. These cover receiver side effects, generated
int/bool/float context helpers, lexical enum conversion, dependent structs,
loops, switch, continue and break. Both packages passed. The isolated VM must
explicitly load Core.Object before fixture classes. No size assertion is
bypassed. The dedicated semantic mode records the two reconstructed function
ASTs and three added helpers, checks function flags/native IDs/replication
offsets, and requires native execution. Other functions retain strict AST
comparison. This is finite behavioral coverage, not general equivalence or
metadata fidelity certification.

### Metadata contract disposition

Controlled native experiments have now confirmed save/load ordering, class-flag
provenance and bounded copy/construction/GC effects. The SDK saver changes the
original GFxValue masks without recompilation, and the modern clients use a
different Serialize/Link contract. This is a documented incompatibility, not a
metadata-fidelity PASS. See
[Metadata lifecycle research](../../int64/docs/METADATA_LIFECYCLE_RESEARCH.md)
and [Russian workflow](../../int64/docs/METADATA_WORKFLOW.md).

The observations below are the initial findings that motivated those controls.

Independent symbolic inventories reconfirmed 782 Interface class object-flag
changes (`0xE0004` to `0xF0004`), 80 GFxValue-reference property-flag changes
(`0x400000` to `0x4000008`) and eight spelling-only changes. GFxValue class flags
remain `0x200112`; its native PtrProperty remains `0x1000`. Consequently the
property discrepancy cannot be explained by loss of the instanced class bit.

Focused SDK disassembly located an automatic transformation in
`UObjectProperty::Serialize`: export thunk RVA `0x2D3D` reaches RVA `0x64C60`.
The branch tests archive field `+0x14`, then referenced class flags at `+0x498`
for `0x200000`, and ORs property flags at `+0x3C` with `0x4000008` at RVA
`0x64CA6`, before calling base serialization. This establishes a native SDK
source of the added bits. Subsequent traces identify the saving branch and show
that it does not remove `0x400000`; the original and compiled masks arise under
different native linking contracts. Controls also identify class bit `0x10000`
as RF_LoadForClient and reproduce
its addition during native saving. Full client lifetime equivalence remains
unproven. No blanket flag normalization is justified.

The same SDK's `UObjectProperty::Link` export thunk RVA `0x37F1` reaches RVA
`0x64A90`. It adds `0x400000` when both `0x4000000` and `0x8` are present (or
when the high property-flag bit is set), at RVA `0x64AE7`. Thus serialized flags
and post-link flags must be inventoried separately. The controlled traces confirm
that loading the compiled mask adds this bit before the next native save; the
resulting symbolic metadata is stable on subsequent save/reload passes.

## Scope

This milestone improves fresh bytecode exports and isolated compilation with the
supported x86 SDK. Generation coverage, compilation, metadata fidelity and client
execution are separate validation gates.

External packages, recovered proprietary source, local paths, detailed logs and
artifact manifests remain in ignored local storage. Experiments use isolated SDK
copies and immutable tool snapshots; original packages are read-only inputs.

## Source generation

- Preserve qualified struct types, parent-first declaration dependencies and
  dependency ordering between structures.
- Separate receiver lookup from the lexical scope evaluating call arguments.
- Preserve enum result types through object contexts and reconstruct erased
  byte-to-enum and cross-enum conversions from resolved type identities.
- Retain package qualification in enum object literals and explicit conversions
  needed for leading foreign-enum comparisons.
- Prevent unary-minus token collisions and preserve integer zero/one contexts.
- Recover visible serialized constant names where literal spelling matches;
  exclude arbitrary integer substitutions for ByteConst instructions.
- Bound typed helper identifiers and handle naming collisions.
- Preserve the `instanced` class modifier.
- Stage compiler input as BOM-marked UTF-16 while retaining UTF-8 exports.

Generated helpers and PC-dispatch reconstruction can change the original AST.
Their compilation is not evidence of exact original bytecode equivalence.

## Event names

Visible, unique EV-prefixed integer constants can replace literal event IDs in
native RegisterEvent, ExecuteEvent and UnregisterEvent calls. Recovery also covers
direct switch selectors and native integer equality/inequality comparisons in
verified void OnEvent(int, string) handlers, including inherited event declarations.

Aliases, shadowed names, unknown IDs and computed selectors remain numeric.
Fixtures check scope and compare the ASTs of named and numeric spellings of the
same generated program. This does not establish equivalence between an original
switch and its reconstructed PC dispatcher. Composed event IDs remain open.

## Compiler extensions

Explicit enum-to-INT64 conversion uses the enum's byte representation. Implicit
enum widening remains rejected. Dynamic-array descriptors retain their outer
optional flag, allowing omitted optional arguments without empty-array substitutes.

The following features require explicit opt-in:

| Runner option | Environment variable | Scope |
|---|---|---|
| `--client-array-sort` | `UCC64_CLIENT_ARRAY_SORT=1` | Client Sort compilation and serialization |
| `--client-enum-profile korea290` | `UCC64_CLIENT_ENUM_PROFILE=korea290` | Validated dependency enum overlay |
| `--scoped-enum-casts` | `UCC64_SCOPED_ENUM_CASTS=1` | Lexical-first enum conversion lookup |

Runners clear inherited opt-in variables when the corresponding option is absent.

### Client Sort

The extension emits original opcode 0x47, the receiver expression and the backing
instance DelegateProperty. It preserves receiver evaluation through the SDK retry
mechanism. It checks writable dynamic arrays, two matching scalar comparator
parameters and an int result. No replacement sorting algorithm is introduced.

Positive fixtures cover primitive and struct arrays, inherited delegates, local,
struct and indexed receivers, and existing Insert/Remove operations. Negative
fixtures reject const receivers, out parameters, incorrect types/results/arity,
ordinary functions, missing comparators and static-function instance comparators.
Dependency reload is verified.

The serializer extends its dispatch using the existing two-expression traversal;
opcode 0x46 remains unsupported. SDK output retains header 126/0. A test-only probe
selects the modern instruction grammar in memory without rewriting package bytes
or relaxing public decoder checks. Production dialect identification, actual Sort
execution and MinGW validation remain open.

### Enum metadata and lookup

The tested SDK and client disagree on Engine.Actor.EL2ObjectType: four SDK entries
versus seven client entries, including a shifted existing ordinal. The explicit
profile validates the old layout and installs the client names in compiler memory
using SDK allocation/name APIs. Unexpected layouts are rejected. Package files
and symbolic enum identity are preserved. Tests verify client ordinals and the
unchanged legacy ordinal when the profile is disabled.

Lexical-first enum conversion lookup is restricted to the verified SDK conversion
call site. A two-class same-name enum fixture reproduces default global lookup
failure and passes exact roundtrip with the option enabled. Arbitrary qualified
foreign enum casts remain unresolved. Profiles require independent validation;
the tested overlay must not be assumed correct for other clients.

## Validation results

| Check | Result and limits |
|---|---|
| Fresh Interface export and compilation | All 782 classes recovered and compiled; zero errors, 60 warnings |
| Fresh NWindow export and compilation | All 140 classes compiled; metadata differences remain |
| Nine immutable compiler suites | Generation, metadata, defaults, replication, iterators, states, pointers, INT64 enums and optional arrays passed with all three opt-ins |
| Expression suites | Exact requested AST/metadata/default checks passed with opt-ins enabled and disabled |
| Event comparison fixtures | Scope assertions and named/numeric generated-program AST equality passed |
| Generator CTests | All seven passed after the event-comparison change |
| Five-profile generation audit | 23 packages, 7,716 classes recovered from bytecode, zero regressions on an earlier immutable snapshot |
| Client smoke check | Reported launch to the login screen with only Interface replaced and original NWindow retained |

The completed profile audit predates later byte-to-enum and event-name changes;
an audit of the final snapshot remains necessary. The successful full Interface
build predates direct event-comparison recovery. The client smoke check was
reported against the supplied build, but installed file hashes were not
independently collected. Authentication, world entry and gameplay scenarios were
unavailable without a server. No general runtime-equivalence claim is made.

All four missing-return warnings in the complete build were checked against
original bytecode and correspond to Return(Nothing). No fabricated zero or false
returns were added. Other warning categories include unused locals and shadowing.

## Metadata fidelity

`tests/compare_metadata.py` produces path-free, hash-bound comparisons. It compares
symbolic identities and metadata fields, excluding raw index-bearing property
bytes and export order. A same-package control reports zero differences.

NWindow has 7,000 rows in each inventory and 157 differing identities: 140 class
object flags, 13 property flags and four spelling differences. All 13 property
flag differences reference GFxValue, including array elements. SDK serialization
and linking propagate flags from `instanced` classes; preserving that modifier
alone does not establish fidelity. No blanket flag rewrite is applied.

Interface has 63,850 original and 76,219 compiled rows, with 13,240 differing
identities. Added properties comprise 11,466 recovered-PC locals and 903 helper
properties. No identities were removed. There are 782 class object-flag differences,
81 property-flag differences and eight spelling differences. Eighty property flags
change from 0x400000 to 0x4000008; one property loses bit 0x1. Editable declarations
and instancing propagation require further investigation.

## Reproduction tools

- `tests/compile_generation.py`: isolated synthetic compiler roundtrips and
  expected-rejection checks, recording active options and tool hashes.
- `tests/compile_external.py`: fresh external exports, UTF-16 staging and isolated
  compilation with hashed input/tool manifests in local storage.
- `tests/compile_event_switch.py`: event scope assertions and named/numeric AST
  comparison for generated programs.
- `tests/inspect_metadata.cpp`: metadata inventory and optional enum inventory or
  import inspection.
- `tests/inspect_sdk_sort.cpp`: test-only SDK-output instruction grammar adapter.
- `tests/compare_metadata.py`: structured metadata differences with flag-bit detail.

These tools accept input paths as arguments. External SDKs and packages are not
distributed with the repository.

## Remaining work

### Editable metadata follow-up

Editable declarations now preserve their category and edit flag. A fixture covers
default and named categories, const fields and editable structure members. The SDK
accepts only `var()` on structure members and supplies their category itself;
the generator follows that rule. Exact AST/metadata/default roundtrip and all seven
generator CTests passed. The metadata probe now also compares property categories.
A fresh original-package export and compilation with this change recovered all
782 classes and completed with zero errors and 60 warnings. The affected editable
property now matches the original flag and category in the compiled artifact.
The inventory has 13,239 differing identities, one fewer than the preceding build;
the remaining 80 property-flag and 782 class object-flag differences are unresolved.
This newer artifact includes direct event comparisons and has not been run in a
client.

External compilation can require an expected input SHA-256 before creating a
workspace. This distinguishes original inputs from installed experimental builds.

1. Resolve editable declaration and class/property flag fidelity in both packages.
2. Validate remaining enum ambiguities, typed helpers and composed event IDs.
3. Repeat full export/compilation and the five-profile audit on the final snapshot.
4. Expand per-profile compilation coverage with matching dependencies.
5. Validate client execution and the output dialect against identified artifacts.
6. Extend genuine Core.PtrProperty support: fixed arrays, explicit zero defaults,
   expressions, then locals/parameters. Replication needs a separate contract.

Native declarations/calls and pointer types must be preserved. Compilation success
must remain distinct from metadata fidelity and actual client behavior.
