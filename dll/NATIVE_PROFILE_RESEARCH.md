# Native profile research

## Validation boundaries

Static export discovery, loaded instruction inspection, VM evaluation, extension
registration and loader modification are separate checks. Client UI execution is
not inferred from a successful standalone host test.

## Loaded code versus file code

The two modern profiles retain the expected exported entry points but their disk
bytes do not match the instructions observed after LoadLibrary. Their loaded Step
prefix is shared and differs from the legacy prefix. Catalog entries therefore
retain disk fingerprints separately from the loaded Step fingerprint.

Runtime profile selection checks the four exported addresses and the selected
loaded instruction fingerprint. Static patch eligibility checks the complete
original file hash, export addresses and disk fingerprints. The loader adaptation
has its own verification field.

## VM evidence

Isolated hosts verified integer and INT64 literal dispatch, the frame instruction
cursor, high/low INT64 word ordering and result-buffer canaries across four target
profiles. A temporary native handler verified two INT64 arguments, the returned
value and restoration of the native table slot. Occupied slots were not replaced.

Clean legacy backups were subsequently used to avoid preinstalled extensions.
The complete ExtensionL2 probe passed on all four profiles: conflict preflight,
idempotent registration, nested native calls, saturation, scalar values, string
arguments/results, UTF-8 files, relative paths, error handling and string ownership.

## Loader experiment

The existing import/entry-wrapper transformation preserved original sections and
exports in both modern inputs. Engine loaded successfully with each patched Core.
An initial VM host run loaded different copies of ExtensionL2 from the executable
and dependency directories, producing an occupied-index error. Co-locating the host
and the tested DLL removed that ambiguity. Automatic registration, repeated attach
and the complete VM/file suite then passed for both modern profiles.

The production native preparation workflow was exercised on all four profiles.
Each run generated a new copy, passed Engine loading and the complete patched-mode
extension probe, and recorded hashes and results. These tests do not establish
client startup with the patched modern Core or correct Test-button integration.

## Remaining investigation

Unknown profiles still require adapter research rather than hash-only acceptance.
Additional architectures, different frame/string layouts, occupied native ranges
and alternate loader transformations remain outside the exercised contract.
Client UI integration, package-level test execution and deployment checks remain
separate milestones.
