# Package profile 133/40

## Verified scope

The supplied Essence, Korean and Japanese Core, Engine, NWindow, Interface and
InterfaceClassic packages use Unreal version 133 / licensee 40, wrapped in
`Lineage2Ver111`. These numbers are independent of the game's network protocol.
The existing compact-index Name/Import/Export layout works for these samples.

Added decoding:

* `0x46`: signed little-endian 64-bit literal; nine script-memory bytes including
  the opcode. Source rendering uses `INT64("decimal")` to preserve precision.
* `0x47`: dynamic-array sort with two expressions, array then comparator delegate.
  Object references consume four script-memory bytes despite compact disk encoding.
  Observed references include `TimeZoneWnd.RestrictFieldInfos` and
  `TimeZoneWnd.__SortCompare__Delegate`. Source rendering uses `.Sort(...)`.
* `DelegateProperty`: a compact function reference follows common property metadata.
  For example, `DialogBox.__DelegateOnOK__Delegate` references `DialogBox.DelegateOnOK`.

Both new opcodes are gated to 133/40. Synthetic CTest coverage checks signed
extremes, script-PC accounting, truncation, unknown tokens, delegate metadata and
123/37 and 126/0 regression behavior. No client fixtures are bundled.
The native checks passed on Linux and Windows x64 Release; Windows DLL/CLI builds
also completed successfully.

## Reproduce external verification

Build uExplorer with CMake, then run `ctest --test-dir <build> --output-on-failure`.
Build the independent decoder from
<https://github.com/ritsuwastaken/open-l2encdec> at revision
`870fc5be32e17abbb499e777c36dad0116e2e6e0` (1.3.11).

```sh
python uExplorer/tests/audit_profiles.py \
  --library <build>/libuexplorer_core.so \
  --decoder <decoder-build>/cli/l2encdec \
  --profile Essence=<essence-system> \
  --profile Korea=<korean-system> \
  --profile Japan=<japanese-system> \
  --output <report.json>
```

Use anonymous labels. Reports contain filenames, hashes and structural results,
not input directory paths. `evidence/133-40-audit.json` records the supplied samples:
all 15 have zero audit failures and match independent wrapper decoding byte for byte.
The oracle command is `l2encdec -c decode -t -o <output> <input>`: these samples
have no removable 20-byte footer. Omitting `-t` discards actual export-table bytes.

The API request `{"operation":"audit","path":"<package>"}` does not load
dependencies. Functions, enum/const values and properties are checked through
their serialized ends. Class/State/Struct checking covers structural prefixes
and scripts, **not complete defaults or semantic validity**. `checked` therefore
does not mean fully decompiled. The first 100 failures are retained with a total
count and truncation flag.

## Remaining limitations

Delegate declarations/assignments and some state/default constructs remain
unsupported by the source writer and produce `partial` results. The inspected
TimeZoneWnd, HelpWnd and RelicSummonWnd classes still report delegate issues.
Successful structural audit does not establish recompilability, client execution
equivalence, or the native XDAT layout. The latter is a separate investigation.
