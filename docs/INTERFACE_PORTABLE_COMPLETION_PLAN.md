# Interface compilation and portable delivery completion plan

## Objective and scope

Deliver a minimal portable SDK compiler workspace with usable Interface sources
and matching compiler-side dependencies for Gracia (protocol 152), High Five
(268), Japan (591) and Korea (606). Validate all four actual builds and reconcile
their results with the completed full-package matrix.

Native SDK/client ABI and layout repair remains excluded. A standalone compiler
is a separate project described in
[the native compatibility handoff](NATIVE_COMPATIBILITY_AND_COMPILER_DESIGN.md).
Essence remains deferred. No push or new actual-client run is part of automatic
execution of this plan; actual-client validation is a final user-assisted stage.

## Starting evidence

* Main matrix: 141 completed packages, 51,627 recovered classes, zero reported
  partial/failed class exports. ORIGINAL: 4 PASS, 9 FAIL, 125 BLOCKED, 3 SKIP;
  CHAIN: 4 PASS, 5 FAIL, 129 BLOCKED, 3 SKIP.
* The separate indexed-default exporter run completed 141 inputs with unchanged
  input/tool hashes. This did not compile all emitted sources.
* Adapted-SDK portable Interface builds: Korea PASS; Gracia, High Five and Japan
  FAIL. These are a third compilation mode, not replacements for original-mode
  or rebuilt-chain evidence.
* Gracia's leading omitted argument is lost by the exporter's string join helper.
  A correction and an optional-array regression fixture are edited but not yet
  built/tested/committed as a repair.
* High Five InventoryWnd's saved ScriptText includes the third bool argument to
  RequestGetItemFromPet; forced-bytecode output omits it. The package's stored
  bytecode must be audited before assigning the defect to the exporter, historical
  compiler or dependency setup. No missing argument may be guessed.
* Japan's EL2_STATUE exists in original Engine metadata but is unresolved in the
  selected compiler environment. The precise enum sequence/profile must be checked.
* Portable positive/negative/relocation controls passed. Minimal SDK experiments
  established DLL import requirements plus User.ini and Editor.int. Full-profile
  results after final packaging changes still need to be recorded together.

## Ordered work

### 1. Freeze and reconcile evidence

- Preserve source/package/tool hashes, the four failed/successful build logs and
  current portable contents before replacing any generated files.
- Inventory pending repository edits; keep launcher work, exporter repair and
  documentation in separate commits.
- Record protocol provenance separately from patch labels and package headers.

Acceptance: each subsequent comparison identifies the exact input, exporter,
compiler pair, compiler dependencies and profile switches.

### 2. Validate the leading-argument exporter repair

- Build the corrected exporter in an isolated build directory.
- Run the optional-array strict roundtrip with a leading omitted parameter and
  the existing interior omission, plus C++ tests and the hash-bound regression.
- Re-export the affected Gracia class and check the preserved call positions
  against decoded bytecode. Do not edit its meaning merely to satisfy the SDK.

Acceptance: the call is emitted as OptionalValues(, 7), not OptionalValues(7),
  and the targeted roundtrip preserves the argument AST/metadata contract.

### 3. Diagnose and resolve the High Five discrepancy

- Compare original ScriptText, decoded call operands, callee parameter metadata
  and the selected NWindow dependency.
- Check relevant bool calls for malformed arity; compare the previously recorded
  token-marker defect without assuming it explains this input.
- If stored bytecode is defective, retain that failure and use the independently
  validated saved source for the user build. If decoding/emission is wrong, repair
  it with a minimal regression. If dependencies differ, select matching metadata.

Acceptance: all affected calls have evidence-backed arguments; a successful build
  is not represented as equivalence to malformed original bytecode.

### 4. Correct Japan compiler-profile preparation

- Compare enum owners, ordered names and numeric values in original Engine and
  compiler-side Engine. Check whether the existing verified extension exactly
  matches; do not enable a differently named profile solely on similarity.
- Adjust only the compiler-side profile/dependency setup needed for script
  compilation. Keep client originals and native layout untouched.

Acceptance: EL2_STATUE and neighboring values resolve with correct numeric values,
  and the full Japan Interface build proceeds successfully.

### 5. Select and label deliverable source sets

- Prefer complete, declaration-validated embedded ScriptText for a user source
  package when available; retain forced-bytecode exports as separate audit evidence.
- Use repaired bytecode recovery where source is absent. Record provenance and
  discrepancies per class outside the minimal user bundle.
- Do not replace an incomplete package with a smaller test Interface or silently
  remove supplied test classes/native declarations to obtain a successful build.

Acceptance: all expected classes are present (Gracia 241, High Five 255, Japan 794,
  Korea 782), and the source basis of each profile is explicit.

### 6. Rebuild and verify all four Interface packages

- Run clean builds through the actual portable scripts and selected dependencies.
- Continue fixing newly exposed source-emission or profile-preparation defects
  within scope; verify each repair before continuing.
- Inspect produced packages, class/function inventories, references and supported
  bytecode bodies. Keep compilation, structural fidelity, metadata differences
  and semantics as separate results.
- If a newly exposed issue requires excluded native work, report the exact blocker
  and seek a scope decision rather than weakening validation or claiming success.

Acceptance: four reproducible compile PASS results, or an explicit unresolved
  scope blocker. Warnings are recorded. Runtime equivalence is not inferred.

### 7. Complete matrix follow-up

- Keep the completed ORIGINAL/CHAIN results immutable.
- Add the four adapted-SDK Interface results as a distinct mode with source
  provenance. Do not turn earlier BLOCKED entries into PASS retrospectively.
- Audit exporter changes across frozen inputs for omitted-argument/arity effects;
  rerun affected exports and compile controls. A new full-export run, if used,
  must have its own exporter hash and cannot borrow the previous 141-package PASS.
- Summarize actual limitations: an issue-free export is not proof of compilable
  source, exact metadata or client behavior.

Acceptance: one reconciled report links each result to its mode and evidence,
  with no conflation of source recovery and compilation success.

### 8. Finalize the minimal user bundle

- Retain compiler/bridge, required SDK files, source sets, necessary profile
  dependency differences, launch scripts, licenses, short Russian instructions
  and concise build status.
- Keep research documents, original reference packages, manifests used for
  investigation, test sources and validation work/log directories outside it.
- Verify the final layout after deduplication, including a relocated path with
  spaces/non-ASCII text, nonzero error exit and stale-output handling.
- Retain a delivered-file hash inventory in local evidence outside the bundle.

Acceptance: a user can choose a profile, edit its Classes and run its command
  without installing Python or development tools. Instructions accurately state
  output location, protocol, encoding, dependency handling and tested limits.

### 9. Close documentation and hand off client validation

- Update the private results/continuation files and sanitized public documentation.
- Commit repairs/tests separately from documentation; scan publication changes
  for private paths and other private data. Do not push without authorization.
- Only after automatic checks, offer the final user-assisted client checks with
  artifact identities, visible results and System/test.txt. Server/network checks
  unavailable in that environment remain SKIP; no historical report substitutes
  for a test of newly delivered artifacts.

## Completion criteria

The current 141-package export result alone does not close this plan. Completion
requires the repaired exporter controls, resolved in-scope Interface build failures,
verified final portable layout, reconciled reports and a clearly separated status
for any pending actual-client checks. Native compatibility development is not a
hidden prerequisite and is not counted as repaired by this work.

## Completed automatic execution

The leading-omission repair passes the targeted strict roundtrip, seven C++ tests
and the unchanged-input 25-check regression. A read-only instruction audit of
all 141 frozen packages covers 121,910 functions/states with zero decode errors;
18 affected calls in ten classes were re-exported and compared.

Two independent decoders confirm missing bool operands in the supplied High Five
bytecode while saved ScriptText retains them. Source selection yields 241 saved
classes for Gracia and 255 for High Five; Japan's 794 and Korea's 782 classes
require bytecode recovery. Japan and Korea have the exact same seven-member
EL2ObjectType sequence required by the existing compiler enum extension.
These findings resolve the preparation decisions without modifying client DLLs.

All four full Interface compilations now pass, with matching class inventories
and inheritance and zero supported structural-audit failures. Final High Five
call inspection confirms the four required bool operands. Symbolic metadata
differences for the modern profiles remain reported rather than normalized away.
Detailed totals and source provenance are in
[the completion evidence](FULL_PACKAGE_REPAIR.md#completed-adapted-sdk-interface-delivery-checks).

The final CMD/PowerShell launcher passes the short relocated-path and failure
controls. Deep-path SDK failure remains a documented limitation. Research and
test artifacts are excluded from the minimal user workspace. Original/chain
matrix records are preserved alongside the distinct adapted-SDK follow-up.
Automatic implementation and validation steps are complete; publication and
manual client verification are tracked separately. Manual checks are postponed
until user availability and are not counted as PASS.
