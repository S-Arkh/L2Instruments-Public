# High Five / Gracia Epilogue: optional CRC32 trailer

## Current result

The 20-byte envelope contains a **little-endian CRC32 at +12**, calculated over
every byte before the envelope. This is confirmed by eight independently supplied
legacy XDAT fixtures, including Gracia Epilogue and High Five. The other four
words' meanings and the original producer remain unresolved. This trailer is
not additional UI content and is not consumed by the tested native XDAT readers.

## Established facts

The supplied HF and Gracia Epilogue plaintext XDATs have 20 bytes after the
schema-defined chat-channel list. The editor preserves these bytes verbatim.
This is distinct from Essence/Korea/Japan, whose final HeadDisplay and
ScalableData sections are now parsed structurally.

Native inspection confirms that both older root serializers finish at the
chat-channel definition, with no subsequent archive reads:

| Profile | Module | Root serializer RVA | Final chat serializer RVA | LoadXdat RVA |
| --- | --- | --- | --- | --- |
| Gracia supplied sample | NWindow | 0x1cfc90 | 0x26ff40 | 0x1cdf70 |
| HF supplied sample | loaded NWindow | 0x3aafa0 | 0x456550 | 0x3a9290 |

In both LoadXdat implementations the root serializer is followed by archive
destruction, without an explicit end-of-file assertion or trailer read in that
function. This does not independently validate all lower-level archive behavior.

The bytes can be represented as five little-endian uint32 words:

| Sample | Words at offsets +0, +4, +8, +12, +16 |
| --- | --- |
| HF | 0, 65, 211, 0x6d06ba80, 0 |
| Gracia | 0, 55, 182, 0xf74ff723, 0 |

Two examined HF files with different payloads and lengths have identical tails.
The word at +12 does **not** equal CRC32 of the supplied plaintext before the
tail: the checked HF payload yields 0xf0bc9a35 and Gracia yields 0xf68a9e08.
Those five supplied/edited files retain identical trailers within each profile
despite different payloads: three HF files share one tail and two Gracia files
share another. Together with the eight matching reference files, this supports
stale checksum metadata retained by previous edits. A mismatch is not a parsing
failure. The editor deliberately does not recalculate the stored value.

The independent open-l2encdec oracle also uses a 20-byte wrapper trailer with
CRC32 at +12, but that resemblance does not identify the producer of these
plaintext XDAT envelopes. Do not add an encryption header or XOR the payload
when checking the plaintext XDAT checksum.

## Independent corpus evidence

`evidence/legacy-tail-corpus.json` records 14 samples: eight matching CRC trailers,
five nonmatching trailers, and one tail-free Freya reference. No client bytes or
paths are included. Reference identities are verified against the existing
external-fixture SHA256 manifest before analysis.

| Reference profile | Word +4 | Word +8 | Stored and calculated CRC32 |
| --- | ---: | ---: | --- |
| Interlude | 15 | 100 | 0x64abda69 |
| Kamael | 20 | 110 | 0xf95cd9c9 |
| Hellbound | 26 | 121 | 0x9f987dff |
| Gracia Part 1 | 29 | 131 | 0xd174a6f7 |
| Gracia Part 2 | 31 | 136 | 0x2ec7b2e7 |
| Gracia Final | 40 | 152 | 0x2fdd6693 |
| Gracia Epilogue | 49 | 169 | 0xcbeee7ed |
| High Five | 60 | 198 | 0x494fe35b |

The increasing words at +4/+8 are suggestive of producer/build metadata, but
they are **not established counters, format versions or network protocols**.
For example, the supplied HF tail has 65/211 while its launcher reports protocol
268; the supplied Gracia tail has 55/182 while its launcher reports 152.

## Reproduction

```text
python tools/inspect_xdat_tail.py --schema ct26.XDAT --sample <HF.xdat> --output <HF-report.json>
python tools/inspect_xdat_tail.py --schema ct24.XDAT --sample <Gracia.xdat> --output <Gracia-report.json>
python tools/audit_legacy_tails.py --fixtures <external-fixture-directory> --sample ct26.XDAT=<HF.xdat> --sample ct24.XDAT=<Gracia.xdat> --output <corpus-report.json>
```

Reports contain hashes, lengths, five trailer words and the explicit CRC
comparison; no sample paths or UI payloads. Keep client files external.

## Schema/editor handling

`ct24.XDAT` and `ct26.XDAT` retain their optional, variable-length `tail`
operation, annotated with `"layout": "legacy-crc32"`. A 20-byte tail whose first
and last words are zero is treated as a candidate CRC envelope. The root property
panel exposes `_tail_word0`, `_tail_word1`, `_tail_word2`, `_tail_crc32` and
`_tail_word4` as **read-only uint32 values**. Only the CRC has an established
meaning. Structural recognition is not proof of integrity: diagnosis separately
reports the calculated CRC and whether it matches. Arbitrary other tails remain
opaque, and files without a tail remain valid. Save, JSON roundtrip and Undo
preserve the exact original trailer; new documents do not invent one.

`tools/update_legacy_profiles.py` reproducibly applies these annotations and the
display labels **Gracia Epilogue (protocol 152)** and **High Five (protocol 268)**.
The numbers come from static inspection of the supplied launchers' explicit
`-L2ProtocolVersion` handlers, not from the trailer. See
`evidence/legacy-client-protocols.json`: the respective embedded `$Revision`
strings are at RVAs 0x32ec8 / 0x32ea0, with parse calls at 0x27480 / 0x2741c.
This identifies the investigated launchers; it is not a network-handshake test
or a guarantee for every build using the same XDAT schema.

## Archive-level follow-up

In the Gracia launcher, `FL2FileDecryptArchive` constructor 0x8f70 falls back
to a raw stream when there is no `Lineage2Ver` header. Its TotalSize method
0x92b0 returns the underlying size unchanged for plaintext; no 20-byte subtraction
occurs. The corresponding HF constructor/TotalSize RVAs are 0x8e30 / 0x9170.

The investigated Gracia `XMLDataManager::SaveXdat` (0x1ce070) calls the root
serializer and destroys the archive. Its launcher CreateFileWriter (0x9f30)
selects plain output for `.xdat`; `FL2FileEncryptArchive::Close` (0x97f0) flushes
and closes, and Flush (0x98c0) writes the buffered payload without appending this
envelope. No trailer-generation code was found on this examined plaintext save
path. This narrows the likely origin to another production/postprocessing path;
it does not identify that tool or establish the remaining word meanings.

## Remaining work

- Identify the trailer writer and the meaning of the remaining words.
- Identify whether another producer actively uses the non-CRC words.
- Preserve arbitrary existing tail bytes and tail-free legacy fixtures meanwhile.

## Independent native-reader experiment

`native_xdat_probe.cpp` constructs the native XMLDataManager and invokes its
serializer through a bounded in-memory FArchive in a separate Windows x86
process. Its allocator is supplied by the host because client appInit is not
run. This tests the actual native deserializer, not the full game startup,
file-wrapper handling or rendering. The host terminates without client teardown.

Both HF and Gracia accepted edited window names and dimensions in three forms:
original 20-byte trailer, replacement bytes 0..19, and no trailer. In every case
the reader stopped at the same payload boundary and did not request any trailer
bytes. See `evidence/native-hf.json` and `evidence/native-gracia.json`.
Thus these trailers are not required by the tested native XDAT serializers.
Their originating writer and the non-CRC word meanings are still unresolved.

## Gracia startup check

A private working copy with matching assets and the edited XDAT reached the
rendered login screen during a bounded 40-second Windows launch. A window-only
capture was inspected: the login form, buttons and background were visible.
No credentials were entered. Follow-up full-client launches also reached the
rendered login screen with the trailer removed and with replacement bytes 0..19;
window-only captures of both were inspected. This is
startup/login rendering evidence, not validation of every edited or in-game
window. The capture and client assets remain private.
The sanitized result is recorded in `evidence/startup-gracia.json`.
The additional variants are recorded in `evidence/startup-legacy-tail-variants.json`.

## High Five startup check

A separate complete working copy of the supplied protocol-268 client also
reached the rendered login screen with an edited window name in all three
variants: original trailer, no trailer, and replacement bytes 0..19. The
login form, background and buttons were inspected in all three window captures.
The executable was launched with `-windowed -NoSound` and process-local
`__COMPAT_LAYER=RunAsInvoker`, without elevation; the initial ordinary subprocess
launch had returned Windows error 740 before the game started. Each successful
trial was bounded to 40 seconds and then terminated. No login was attempted.
The captures remain private; hashes/results are in the same variants report.
The working-copy XDAT was restored after the experiments and source clients
were not modified.

## Editor verification after annotation

Linux tail/research tests: **28 passed**. Windows tail/schema-GUI/JSON tests:
**80 passed**. Both native cores rebuilt successfully. The independent Gracia
Epilogue and HF reference files additionally passed binary and JSON roundtrip
with the annotated schemas; the C++ CRC implementation agrees with Python/zlib.
The tests exercise correct/stale CRC, edit/undo, read-only trailer properties,
arbitrary 20-byte tails, short/long tails and absent tails.

Build from an x86 MSVC developer prompt:

```text
cl /EHsc /W4 /MT /Fe:<private-output> /Fo:<private-object> tools/native_xdat_probe.cpp
python tools/run_native_xdat_probe.py --probe <probe.exe> --module <working-copy-NWindow.dll> --sample <edited.xdat> --constructor 0x3aae30 --serializer 0x3aafa0 --stack-ctor --output <report.json>
```

The shown RVAs/stack-constructor ABI apply only to the investigated HF module.
Gracia uses constructor 0x1cfb20 and serializer 0x1cfc90 with stack-constructor ABI.
Do not reuse these offsets on another module build without verifying them.
