# Resource inventory API

## Current task boundary

Independent structured readers, public resource APIs, tests and API documentation
remain in scope. The approved offline continuation also includes read-only GUI
resource viewers and client Graceful Exit. Entering the world, protocol-606
compatibility and in-session behavior are deferred until a test server is
available. Earlier API-only milestones do not establish GUI or runtime coverage.

### GUI continuation

Mode navigation, structured previews and the in-memory audio player with
waveform/FFT/spectrogram are implemented. See [GUI status](RESOURCE_GUI.md).
Texture visualization supports P8, RGBA8, DXT1/3/5 and G16, zoom/pan,
mip selection and local Cubemap faces. Diagnostic orthographic geometry,
reference skeletons and full-hierarchy skeletal animation playback are available.
The comparison UI matches resource identities and exact decoded fields while
excluding relocation offsets/reference slots, with explicit unsupported and
cancelled states. Textured rendering, skinning and VertMesh animation remain pending.

Mode buttons above the middle object list, between the list and the package
filter, select Code, Textures, Sounds, Materials, Models, Animations or Other.
The selected mode changes both the middle list and the right-hand viewer.
Availability follows package contents; selection, filtering and scroll position
are retained per mode.

- Textures: zoom/pan, fit, 1:1, transparency background, mip and cubemap faces.
- Sounds: play/pause, stop/reset, restart, seek, elapsed/duration, volume, mute
  and repeat; waveform, live FFT spectrum and time-frequency spectrogram.
  No autoplay; switching object, package or resource mode stops audio.
- Materials: structured fields, texture links and supported previews.
- Models: supported 3D geometry, camera controls, wireframe and collision view.
- Animations: compatible-model playback, pause/stop, seek, frames and speed.
- Other: structured properties, links and explicit unsupported-preview reasons.

Viewers must remain responsive for large inputs, release playback/resources on
transitions and never modify source packages. Resource editing is not included.

Send `{"operation":"resource_inventory","path":"Editor.u"}` to the CLI or
JSON API. No dependency loading or script decompilation is required.

Schema 1 returns the package profile and envelope, candidate exports grouped by
fully qualified class identity, serialized byte totals, export IDs, paths,
owners, flags and offsets, and typed import-table entries. The result omits the
input filesystem path. Offsets refer to the decoded package.

File loading supports `Lineage2Ver121` using the lowercase ASCII basename,
including extension, to derive its XOR key. Non-ASCII filename rules remain
unverified and are rejected. Normal package profile and table validation still
applies. This enables inventory of supported Korean texture containers; it does
not establish texture/material body reconstruction.

Known script metadata and TextBuffer exports are excluded. Candidates include
groups, class-owned objects and unknown native classes; they are not restricted
to a fixed list of mesh, texture or sound names. Export IDs and class identities
distinguish objects with equal paths.

This is table inventory, not resource reconstruction. `native_bodies_checked`
is false: payload properties, internal references, collision data and lazy
offsets have not been inspected. The imports list does not establish which
candidate uses an import. Full structural codecs and independent reconstruction
checks remain necessary.

## Saved BlockingVolume inspection

`{"operation":"blocking_volume","path":"Example.unr","object":"BlockingVolume43"}`
reads a narrowly qualified saved actor from profile `133/40`. It also accepts
`object_id` and participates in the atomic `resource_batch` API. The class must
be exactly `Engine.BlockingVolume`, with the observed saved-state frame and a
local `Model` brush reference. Unsupported profiles or frames, malformed
qualified tags or references, duplicate properties and trailing bytes are
rejected. This is not a generic actor reader.

The response contains the saved frame, ordered `properties`, resolved references
and `brush`. It preserves the frame's unknown 32-bit word without assigning a
meaning and reports exact float/vector bits, including signed zero and nonfinite
values. Recognized nested `Scale`, `PointRegion` and `TextureModifyinfo`
properties are bounded and qualified by field name and type. Other tagged
properties are listed as uninterpreted without copying their payload; the
response then has `status: partial`. `saved_properties_decoded` only means that
all *stored* tags in that response were handled by this bounded reader.

Inherited defaults, world transforms, events and runtime collision are not
resolved or executed; the response explicitly marks them unverified and sets
`reconstruction_supported: false`. The comparison UI always reports these
actors as `unverified`, not as reconstructed matches.

On the Korea `16_19` map, independent field parsing and Windows/Linux API
responses agree for ten actors. Their saved frame words have nine distinct
values, and one actor explicitly stores `bWorldGeometry=False`. These are
serialized observations, not evidence of the live state or full scene.
The allowlist also includes observed `LocationName`, `bAcceptsProjectors`,
`bLightChanged`, `bPendingDelete`, `bSelected`, `bHiddenEd`,
`bLockLocationGroup`, `bHiddenEdGroup`, `bForceSunLight`, `bIgnoredRange`,
`bAutoAlignToTerrain`, `RangeForIgnoredRange` and `SwayRotationOrig` tags;
their presence and values remain saved data, not current runtime state.
After this extension, field-by-field independent parsing and Windows/Linux
responses agreed for 1,984 saved BlockingVolumes on 14 selected `133/40` maps.
An experimental Level-prefix walk found 1,974 in its saved actor lists and
ten outside those lists, all ten explicitly storing `bDeleteMe=True`. That
correlation does not establish a general deletion rule or live membership.
The Level tail remains unparsed, and this research is not a Level reader.
Three additional observed actors fail strict `PointRegion` bounds: a research
hypothesis can close each nested stream using one byte outside its declared
size, but the production reader does **not** adopt this guess or repair the
objects. Runtime acceptance is unknown.
In a later census of 365 selected client map files, 301 had profile `133/40`;
the other 64 were not included in this reader's coverage. Of 19,582 exact-class
BlockingVolume exports in those 301 files, 19,579 passed field-by-field
independent comparison on both Windows and Linux. The other three are the
strictly rejected `PointRegion` cases described above. No other properties
were left uninterpreted in the accepted responses. This is a saved-data census,
not proof of live membership, completeness of every actor class or collision.
The saved `Rotation` tag appears on one of the 19,579 accepted instances and
`PrePivot` is absent on 151; absence is not treated as zero. Across those
instances, 19,508 local Model/Polys links have matching unordered vertex-bit
multisets per nonempty record, while 71 differ. The three rejected actors were
excluded. These checks do not establish polygon-union equivalence, world
placement, live membership or collision.
For the same 19,579 saved brush links, the partial C++ API outputs were checked
against separate prefix parsing before comparing the box and point values.
Numerically, 19,566 Model boxes match the extrema of their
node-used points, two Models have no node-used points, and eleven have used
points outside the saved box. All eleven also have different Model/Polys
vertex multisets. The maximum observed axis excess is exactly 1/4096; no
tolerance, box repair, world placement or collision conclusion is applied.
On the ten linked `16_19` Models, a separate exact local investigation found
that only 36 of 60 saved node planes contain all associated face vertices
exactly; five faces have vertices on both sides. The maximum distance to a
saved node plane is approximately 0.0006521 local units. All ten associated
saved hull-plane sets mathematically define bounded positive-volume local
halfspace intersections, but only three have exactly the saved face-vertex
set. These are research diagnostics checked against the independent Model
API on Windows/Linux, not new collision or intersection features of the GUI.
No tolerance, repair, world placement or runtime equivalence is inferred.

## Completed whole-corpus comparison

The Model 123/37 milestone adds one complete 50-export container, including
independent reversed-table comparison. Coverage at that stage was
1,099/1,184 containers / 223,185 exports (261 static containers / 12,912 exports),
with 85 remaining rejections. Windows/Linux reconstruction is byte-identical
and both observed Model responses match across platforms.

`{"operation":"model","path":"brush.usx","object_id":1}` reads the observed
123/37 brush layout, also available in `resource_batch`. Schema 1 exposes bounds,
exact vector/plane/sphere words, BSP nodes and surfaces, vertex pool, collision
hulls, render bounds, shared-side count, root/linked flags and resolved
material/actor/Polys references. For 123/37, nonempty zones, leaves, lights and
render arrays are unverified and fall back to an opaque warning; trailing bytes
are reported as an unverified remainder. Invalid checked indices remain errors.

For 133/40, `model` separately reads the complete saved structure, including
zones, leaves, lights, render sections, lightmaps, both page buffers and the
compact-counted trailer for observed unstacked Models with no tagged
properties. Unverified tagged forms are attempted using bounded tag headers;
stacked forms use the opaque fallback below. It validates
nonzero absolute lazy boundaries and
reports exact data as words or hex. It remains a **read-only** API; the separate
OpenUCC writer performs reconstruction. Node-used point indices and
node-linked hull planes are strict; invalid indices outside those node ranges
and invalid planes in unlinked hulls are retained and diagnosed without
claiming they are unused at runtime. A Python parser independently matched
all fields of 1,865 Models on three maps, before and after reversed tables and
82 lazy fixups. Another 1,457 Models in 62 resource containers matched both
the independent field parser and OpenUCC byte identity. These are Model-body
checks, not claims about complete reconstructed containers, world placement,
or in-game collision.

For profiles 127/39, 128/39, 130/40 and 132/40, only the observed unstacked,
empty-tag form with empty additional arrays and a five-zero-byte suffix is
confirmed. Other forms and other package profiles accepted by the package
reader are attempted as unverified 133/40-layout interpretations. A successful
attempt has `status: "unverified"`, an explicit warning and
`reconstruction_supported: false`. If the candidate layout cannot be parsed
safely, `model` returns an opaque warning with the serialized size and at most
256 initial raw bytes, not fabricated geometry. Strict errors for malformed
fields of the confirmed form remain. The read-only API does not assert
reconstruction, world placement or collision for either fallback. Resource
comparison reports a Model as unverified unless both results are complete
`decoded` structures; matching assumed fields or raw previews are not
counted as structural equality.
All 68 observed Models matched an independent Python field
reader on both platforms. Their 11 containing packages / 1,003 exports also
matched independent structured comparison after ordinary and reversed-table
reconstruction on Windows and Linux; corresponding output hashes match.
Combined corpus coverage is 1,183/1,184 containers / 234,612 exports; one
source with invalid wire indices remains rejected. These are structural checks,
not client loading, world placement or collision.

The distinct `model_collision` operation is only a partial 133/40 brush
inspection. It requires its observed five-byte zero suffix but does not decode
or reconstruct those bytes. Point indices referenced by any node are checked
strictly. Invalid indices in vertex-pool records outside all node ranges are
reported, when present, in `invalid_unused_vertices`; this does not establish
whether some other runtime use exists. The separate 123/37 full decoding still
rejects invalid pool entries.
Independent prefix parsing matched 1,457 partial responses from 62 previously
surveyed 133/40 containers on Windows and Linux. Sixteen of those Models have
64 invalid pool entries outside all node-used ranges. This earlier partial test
does not interpret the suffix or itself increase reconstruction coverage.
Separately, the strict partial level-geometry API agreed with the node-range
diagnostic on 301 saved level Models; 520,360,487 render bytes remain unread
across those responses. The GUI can navigate to an explicitly linked local
Polys as a separate saved resource; it is never automatically substituted for
Model node geometry or represented as verified collision.
The Model GUI frames only the points of the faces it draws and labels those
display bounds accordingly. All saved points remain in the API response;
excluding a point from the preview is not a claim about other game use.

The earlier blocker-closure milestone additionally matches 46 exports in three early
embedded-texture containers, including reversed name/import/export tables.
Textures in 123/12 have no native material prefix; 123/19 and 123/23 expose an
`obsolete_material_word` unsigned scalar before mip data. The early reader also
accepts observed Palette in 123/12 and Shader in 123/23; other early class/profile
combinations remain rejected. This brings combined coverage to 1,098/1,184
containers / 223,135 exports, including 260 static containers / 12,862 exports.
The remaining 86 failures are Model, obsolete material layouts or invalid wire
indices. The earlier stage's totals below are retained as its baseline.

The final animation/sound comparison uses an immutable reader-library copy and
matches all 174,898 exports in 167 reconstructed containers: 100 animation
containers / 131,478 exports and 67 sound containers / 43,420 exports. Inventories
exclude no script exports; every resource is compared and source/candidate/tool
hashes are checked. This replaces reliance on an interrupted earlier run whose
per-package pathname hashes did not consistently identify its loaded reader.
The earlier report and provenance audit remain separate private evidence.

Together with 671 texture containers / 35,375 exports and 257 static containers /
12,816 exports, deduplicated public-API coverage is 1,095/1,184 containers /
223,089 exports. The remaining 89 containers are explicit writer rejections for
Model, obsolete material/texture layouts or invalid source wire indices. This
establishes structured-data agreement, not runtime rendering/collision/audio
equivalence.

## StaticMesh diagnostic reader

The `polys` and `karma_props` operations accept the same object selectors and
`resource_batch` requests. Polys exposes polygon vectors/vertices as exact bits,
flags, actor/material references, item names, compact link/brush indices and
trailing scalar words. KMeshProps exposes nine scalar words and four empty
geometry arrays; nonempty geometry and unknown properties are rejected.
Observed profiles are 123/37, 127/39, 130/40, 132/40 and 133/40; Polys also
supports 128/39. Model native bodies have their own separately bounded profile
support described above.

`{"operation":"static_mesh","path":"Editor.u","object":"TexPropCube"}`
inspects observed StaticMesh layouts. `object_id` may be used instead of `object`.

Supported profiles are 118/0; 123/{12,14,15,16,18,19,20,22,23,25,28,31,33,35,
36,37,38}; 125/38–39; 126–128/39; and 130–133/40. Collision arrays before
licensee 17 omit lazy boundaries. `license_fields` is empty for 118/0; otherwise
`words_1_10` contains only the serialized slots, preserving their order.
`trailing_word` is absent before version 120. Auxiliary data is present for
observed versions 125 onward. Invalid vertex indices remain errors.
It reads tagged scalar properties and Materials entries, bounds, sections,
vertex/color/UV/index streams, collision faces and nodes, license scalar fields
and references, source triangles, auxiliary UV pairs and four final scalar words.
Float values are exported as unsigned
32-bit bit patterns to retain signed zero and non-finite representations.

Counts, vertex indices, section ranges and three absolute lazy-array ends are
checked. Scalar license fields with unverified semantics retain ordinal slot
names. Successful results have `status: decoded` and `remaining_bytes: 0`;
trailing bytes are rejected. `reconstruction_supported: false` describes this
read-only API: uExplorer does not provide a resource writer. It does not describe
openUCC's separate codec, independently checked on two rebuilt Editor meshes and
505 corpus meshes with relocated tables/offsets, including 107 nonempty auxiliary
arrays. These checks establish structural fidelity, not rendering or collision
behavior. The 123/37 layout ends before the auxiliary UV/word suffix; it does not
silently accept a 133/40 suffix. Other profiles are currently rejected.

## Material structural reader

`{"operation":"material","path":"Materials.utx","object":"ExampleShader"}`
reads the observed 123/37 and 133/40 native material layouts. `object_id` may
replace `object`. Supported classes are Shader, FinalBlend, Combiner,
TexCoordSource, TexPanner, FadeColor, TexOscillator, TexEnvMap, VertexColor,
TexRotator, ColorModifier, TexPannerTriggered, TexScaler and ConstantColor.

The result contains typed property references, exact scalar bits, Color/Rotator
components, named Matrix/Plane members, material stage fields, strings, shader
text and material version. Unknown properties/structures, malformed matrix
members and trailing native bytes are rejected. A successful result has
`status: decoded` and `remaining_bytes: 0`. As with `static_mesh`,
`reconstruction_supported: false` denotes a read-only API, not a runtime verdict.
Texture and Cubemap bodies are also supported, including bounded mip byte arrays,
dimensions and absolute lazy boundaries. The `texture` operation selects only
these two classes and returns the inherited material fields plus `mips` entries
with `width`, `height`, `ubits`, `vbits` and exact `data_hex`. Supported storage
formats are P8, RGBA8, DXT1/3/5 and G16. The observed 133/40 DXT3 empty terminal
1×1 mip is retained after preceding levels. Unknown formats and invalid storage
sizes are rejected. The same terminal-placeholder rule also covers the observed
132/40 and 133/40 RGBA8 1×1 mips, with zero dimension exponents.

Expanded material/texture layouts cover 123/38, 125/38, 125/39, 126/39, 127/39,
128/39, 129/39 and 130/40–132/40 in addition to the initial profiles. Versions below 129
have one stage containing two bytes and three words; versions 130 onward have
five stages containing six bytes and two words. Version 129 instead has five
stages containing two bytes and three words.
TexOscillatorTriggered, TexPlanningPanner and FresnelMaterial use the same
inherited material-body reader, with strict property and trailing-byte checks.
L2ColorModifier is supported as well. MaterialSequence adds SequenceItems
`elements`, preserving nested Material references, Time bits and Action bytes.
The `texture` API additionally reads 133/40 MaskTexture, exposing RLEData as
32-bit `words` alongside inherited texture fields.
WetTexture 127/39 is also accepted by `texture`: ADrop `members` retain named
byte properties and fixed-array subscripts. Observed parametric P8 mips are
empty 128×128 or 256×256 levels with matching dimension exponents. No procedural
pixel generation is performed by the API.

`palette` reads a Palette export through the same selector and batch APIs. Its
result contains ordered `tags` and exactly 256 `colors`, each represented by four
stored bytes in their original order. Invalid counts, truncation, class-selector
mismatches and trailing bytes are rejected.

## Animated resource and sound readers

Use the same CLI/JSON ABI with an explicit export ID, for example:

```json
{"operation":"skeletal_mesh","path":"Example.ukx","object_id":1}
```

`object` (export path) is an alternative selector; explicit IDs avoid ambiguous
paths. No dependency loading, DLL execution or UI integration is required.
For corpus work, `resource_batch` loads the package once and accepts an `objects`
array of 1..256 selectors, each containing `operation` and `object_id` (or
`object`). Results are returned in request order. Any invalid selector or decode
failure rejects the request; no partial success is reported. Material, texture,
StaticMesh and animated-resource operations can be combined in a batch.

```json
{"operation":"resource_batch","path":"Example.ukx","objects":[{"operation":"skeletal_mesh","object_id":1},{"operation":"mesh_animation","object_id":2}]}
```

The following operations support profile 133/40:

| Operation | Export classes and decoded body |
| --- | --- |
| `skeletal_mesh` | SkeletalMesh, LodMesh 5/6/7: bounds, original vertices, materials, transforms, impostor fields, extension bytes, bones/poses, attachments, weights, LODs, source geometry and trailing fields |
| `vert_mesh` | VertMesh: LodMesh prefix, animated vertex stream, packed vertices/normals, sequences/events, frame counts and per-frame bounds |
| `mesh_animation` | MeshAnimation version 1: bones, moves, tracks, root tracks and complete sequence/event records |
| `animation_notify` | 32 observed property-only notification classes, including AnimNotify_PlayCustomAnimation; native tails must be empty |
| `sound` | Sound with WAV format name: exact `audio_hex` and `audio_size`, without transcoding |
| `resource_group` | Empty Package groups; properties and native tails must be empty |

Each result contains `schema: 1`, `path`, `class`, ordered `tags`, structured
`body`, `native_offset`, `decoded_native_bytes`, `remaining_bytes: 0`,
`status: decoded` and `reconstruction_supported: false`. References contain
`id`, resolved `path` and `class`; names are resolved strings. Floating-point
fields use unsigned 32-bit words (`*_bits`); packed vertices/normals and ordinal
extension words are retained without conversion. Event `text_utf16` is an array
of raw 16-bit units, preserving embedded zeros and unpaired units.

Tagged properties preserve booleans, integer values, float bits, names, strings,
object references, Vector/Rotator words and Color bytes.
Bool properties expose `declared_size` as well as `value`; their value is carried
in the tag, with no payload. This distinguishes observed zero-sized Bool tags
from size-one or other declared sizes when comparing reconstruction metadata.
VertMesh Materials and
RandomSound Sounds are reference arrays. Unsupported structures and arrays are
explicit errors. Supported notifications are CameraLocation, Sound, RandomSound,
AttackShot, Illusion, BoneScaleScript, Effect, SwimSound, Channeling and
PlayCustomAnimation (all with the `AnimNotify_` prefix).

The expanded allowlist additionally includes AttackPreShot, DestroyEffect,
AttackItem, ViewShake, Light, BoneScale, AttackVoice, JumpSound,
LaunchAccumulativeBeam, ModifyVisBound, JumpDown, JumpUp, PawnStatusVoice,
EventAnimEnd, BoneDirect, Ribbon, HideWeapon, PendingPawnEffectState, SkillEffect,
HidePawn, ScreenFade and IdleSound. PawnStatusVoice's SoundName array is decoded
as FStrings. An independent inventory consumed 114,726 notifications across
these 32 classes and found no native tails.

Additional verified reader profiles are SkeletalMesh 123/36, 131/40 and 132/40;
VertMesh 123/37; MeshAnimation 123/36 and 131/40; Sound 123/23, 128/39, 130/40 and
131/40; notifications 131/40. Legacy LodMesh original vertices use
`packed_original_vertices` instead of `vertices_bits`. Event text is absent
before version 131. The package input limit is 1 GiB; array limits still apply.

Readers validate export bounds, count/stride limits, lazy-array and animation
move boundaries, reference/name validity and complete native-body consumption.
Unsupported profiles, class/operation mismatches, stacked objects and unknown
tails are rejected. Most native arrays and event-text counts are capped at one
million entries; audio length is bounded by the export and the package reader's
size limit. Reading success establishes structural coverage, not playback or
rendering equivalence. At that API milestone GUI and runtime checks were
unperformed. The current offline continuation above includes GUI and Graceful
Exit; in-world/network checks still require the unavailable server.
