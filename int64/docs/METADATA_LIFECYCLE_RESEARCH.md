# Metadata save, load and lifetime contract

## Outcome

The stage-five metadata investigation is complete with a **documented SDK/client
incompatibility**, not a metadata-fidelity PASS. The SDK's native saver changes
original metadata even without decompilation or recompilation. No production
flag rewriting or comparison exemptions were added.

The investigation separates serialized flags, loaded flags, native copying,
template construction, garbage collection and actual game execution. The latter
is not established by these SDK experiments.

## Controlled experiment

`metadata_contract.py` uses three small classes: an `instanced` value, a plain
value and an owner with scalar, fixed-array, dynamic-array and out-parameter
references. `metadata_variant.py` changes only explicitly checked bytes in copies
of this exact synthetic class set. One variant reproduces the original property
masks and class export flags; another changes only class bit `0x10000`.

`metadata_lifecycle.py` stages a hash-checked SDK, saves in a separate process and
reloads in two further processes. Read-only inventories accompany each pass.
The native probe traces `UObjectProperty::Serialize` and `Link` without replacing
their behavior. Class lookup is typed; nested fields are resolved by their actual
outer, including the identically named dynamic-array inner property.

| Reference | Initial compiled file | After load/Link | After save and fresh reload |
|---|---:|---:|---:|
| Instanced scalar/fixed-array/array inner | `0x04000008` | `0x04400008` | `0x04400008` |
| Instanced out parameter | `0x04000188` | `0x04400188` | `0x04400188` |
| Plain scalar | `0` | `0` | `0` |
| Plain out parameter | `0x180` | `0x180` | `0x180` |
| Dynamic-array container | `0x00400000` | `0x00400000` | `0x00400000` |

The original-mask variant loads with `0x00400000` / `0x00400180` unchanged.
During saving, the native Serialize trace records archive field `+0x14 = 1`
and the transition to `0x04400008` / `0x04400188`. During loading that field is
zero. This identifies the observed branch as a saving branch; it does not remove
`0x00400000`. The next two symbolic serialized inventories are identical. Raw
reference indices can change with export order; the test resolves property
super/next links symbolically as well as comparing the inspector's symbolic type
references. This is metadata stability, not raw-byte or package byte equality.

The SDK Link implementation adds `0x00400000` for the inline/export pair or the
high property-flag bit. It does not have the modern clients' referenced-class
instancing test. Thus the apparent removed bit in an original-versus-compiled
comparison is not evidence that Serialize clears it: the compiled property was
constructed under a different native contract. Serialized and post-Link masks
must not be treated as interchangeable.

## Real GFxValue confirmation

Both the original NWindow package and its recompiled counterpart completed three
isolated native save/load passes. The original envelope was decoded; package
version and licensee fields were not rewritten.

* Original `GFxValue.SetElement.Value`: file/load `0x00400180`, save/reload
  `0x04400188`.
* Recompiled counterpart: file `0x04000188`, load/save/reload `0x04400188`.
* `GFxValue` class flags remain `0x200112`.
* Native `GFxValue.pValue` remains a genuine PtrProperty with flags `0x1000`.
* Original GFxValue class export flags change from `0xE0004` to `0xF0004` merely
  by native SDK saving. No source compiler is involved in this control.

Full serialized comparisons still report unequal metadata. Interface has 782
class export-flag changes, 80 property-flag changes and eight spelling changes
among matching identities. It also has 12,369 added helper metadata identities;
these are not silently excluded from the full comparison. NWindow has 7,000 rows
on each side and 157 differing identities overall. The focused GFxValue result
does not explain away every difference in either package.

Full Interface loading in this unmodified SDK probe is incompatible: the original
encounters bytecode token `0x46`; the compiled package encounters client Sort
token `0x47`. Both failed attempts are retained as failures. There is no claim of
a complete loaded-Interface inventory or execution equivalence from this test.

## Class object flag `0x10000`

This is the legacy package flag `RF_LoadForClient`, not a class instancing flag
or the `RF_Standalone` bit. The public legacy flag description is corroborated
by a native differential control: changing only this bit on the synthetic class
exports leaves editor/server loading successful, while SDK client-context loading
fails when a dependent ObjectProperty's class outer is unavailable. The expected
diagnostic is `Object is not packaged: ObjectProperty ...`; the first affected
fixture property depends on export order (Inline or Plain in the observed runs). All three contexts
load the unmodified compiled control.

The original-mask variant enters the SDK with class export flags `0xE0004`;
SavePackage produces `0xF0004`, and a fresh process reads that value. This proves
native saver provenance for the addition, independently of source generation.
Runtime flags also contain transient load/save/GC bits; they are recorded in full
but are not mistaken for serialized export flags.

Reference: [legacy package object flags](https://bunnytrack.net/ut-package-format/).
The differential test establishes this SDK's behavior. It does not establish that
the game clients use the same loading-context policy; their original packages
already use the other mask. Clearing the bit in production would break the tested
SDK client-context control and is not an approved fidelity correction.

## Copying, construction and lifetime

Native controls execute in each of the three processes for both synthetic inputs:

* `CopySingleValue` copies the reference for all three masks, with either a null
  owner or a supplied destination owner. Plain references are the control.
* Constructing an owner from a populated template produces a distinct instanced
  value when the property has `0x00400000` or `0x04400008`. With only
  `0x04000008`, it shares the reference. Payload `73` survives in every case.
  The reported cloned outer is not the new owner in this particular constructor
  call; the test does not assert destination reparenting.
* The native property DestroyValue entry does not destroy the referenced value.
* A rooted owner's reference retains the value through CollectGarbage. Clearing
  that last reference allows collection, verified by object lookup rather than
  dereferencing freed memory. The collector retains standalone objects in these
  editor-context controls.

These are scalar lifetime controls; arrays and out parameters have flag/link
coverage, not exhaustive array-element ownership or VM out-parameter lifetime
coverage. The tests demonstrate why dropping the post-Link constructor bit is
unsafe. They do not certify Scaleform native allocation, native GFx destruction,
client GC timing or general deep-copy equivalence. The separately verified modern
pointer fixture remains the evidence for nonzero native GFx payload copying.

## Initialized modern client instruction evidence

Bounded export samples were taken from isolated copies of the two tested client
Core builds, with module/probe/log hashes retained locally. No property method was
invoked in this inspection.

| Method | Client A RVA | Client B RVA |
|---|---:|---:|
| UObjectProperty::Serialize | `0xF2A30` | `0x103C50` |
| UObjectProperty::Link | `0xF27F0` | `0x103A10` |
| UObjectProperty::CopySingleValue | `0xF2230` | `0x103450` |

Both Serialize bodies call the base serializer and serialize the class reference;
they lack the SDK's saving-time inline/export OR. Both Link bodies set the
constructor bit for the inline/export pair **or** referenced class instancing
(`0x200000`). Both CopySingleValue bodies copy one reference without cloning.
These native differences explain why one SDK mask policy cannot be declared the
original client metadata contract. Export inspection is not a client lifetime run.

## Disposition

Preserve `instanced`, native declarations and PtrProperty identity in source;
retain strict metadata differences in reports. Do not strip or invent flags in
the production compiler/exporter. Exact original-metadata reproduction remains
unsupported by the tested SDK's default saver. A future target-specific writer
would require its own loading and native-lifetime validation. The current result
closes the investigation with an explicit incompatibility boundary, not by
converting those differences to PASS.
