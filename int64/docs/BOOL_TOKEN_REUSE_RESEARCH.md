# Boolean token reuse and emission markers

## Observation

Fresh Interface builds with the MSVC and MinGW bridges had identical generated
source files, name tables, import/export ordering and 76,219 metadata rows, but
different bytecode. Only 26 function export payloads differed between those two
builds. Their total serialized-size difference was 26 bytes; shifted offsets made
a whole-file byte comparison look much larger.

`RelicWndUpgrade.OnUpgradeDialogCancel` supplied a concrete counterexample: the
MSVC output called native 242 with `DialogIsMine()` but omitted the following
`true` operand. The MinGW output retained that operand. In the 26 differing
functions, an arity check found 27 malformed equality calls in the MSVC output
and none in the MinGW output. This did not establish that the rest of either
package was correct.

## Cause and correction

The bridge records an already-emitted expression with a marker in token payload
bytes beyond the scalar boolean value. Both explicit INT64 casts and
`PointerEqual` use this mechanism. The SDK lexer reuses token storage without
initializing all unused payload bytes. A later ordinary bool constant can
therefore retain the marker and be mistaken for an expression whose bytecode was
already emitted. Stack layout makes the symptom build-dependent.

The correction clears the private marker after the SDK returns a newly lexed
bool constant. This happens before the bridge recognizes and emits its special
expressions, so a newly generated `PointerEqual` result retains its intentional
marker. No package metadata flags or native indices are changed.

## Evidence and scope

The pointer fixture now exercises INT64 casts followed by true/false comparisons
and `PointerEqual` combined with ordinary bool comparisons. Its strict
source/AST roundtrip passes. An earlier conditional fixture produced a
PC-dispatch rewrite and was not a valid isolated reproduction of this defect;
the real Interface function is the confirmed pre-fix counterexample.

After the correction, fresh compilations of the same full Interface sources
with both bridges produce equal-size packages differing only in the 16-byte
GUID. Both retain all 76,219 metadata rows unchanged from the pre-fix compiled
baseline. The previously missing operand is present in the inspected function.
These checks establish cross-toolchain agreement for this input, not original
client semantic equivalence or a new actual-client execution result.

A complete scan of the corrected MSVC Interface decoded every function and
checked the operand count of native bool equality/inequality calls: 1,215
comparisons, zero invalid arities. The corrected MinGW package has identical
contents outside its GUID, so this bytecode result also applies to that package.

The earlier compiler archives predate this correction and are superseded by
the compiler bundles built from `6543d5d`. The portable exporter is unchanged.

The completed pre-fix comparison covered 20,203 functions in each of three
packages. Function sets, native IDs, flags and replication offsets matched.
Canonical AST hashes, excluding only numeric object-reference fields, differed
for 26 functions across MSVC/MinGW and for 41 functions against the earlier
compiled baseline. The latter differences remain historical comparison evidence,
not a claim that every old difference was independently classified or that the
old packages were semantically equivalent.
