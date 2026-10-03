# Interoperability Service

A VOLTTRON platform service that lets agents address Distributed Energy Resource (DER)
data by a stable, protocol-neutral identifier and receive it in whatever data format
they understand. It does this with two cooperating pieces:

* A **mapping engine** that resolves a *Uniquely Addressable Identifier* (UAI) to the
  canonical resource that actually publishes the data, following aliases as needed.
* A **transform registry** that holds declarative field-mapping rules between data
  formats (for example IEC 61850-7-420, IEEE 1815.2 / MESA-DER, SunSpec) and finds a
  chain of transforms from the format a resource is published in to the format a
  consumer asked for.

Consumers call one RPC, `resolve`, and get back the canonical resource definition plus
the transform needed to read it in their preferred format. A small client helper,
`ResourceData`, wraps the lookup, subscription, and payload transformation so a consuming
agent never has to know which protocol the underlying device speaks.

The agent runs under the VIP identity `platform.presentation`.

## Requirements

* Python >= 3.10 (the workspace pins 3.11)
* VOLTTRON modular (`volttron-core` >= 2.0.0rc30). The agent also falls back to the
  monolithic `volttron.platform` imports if `volttron-core` is not installed.
* Runtime libraries (pulled in by the package): `convtools`, `networkx`, `pydantic` 2,
  `pyparsing`, `treelib`
* Optional extras: `discovery` (pysunspec2, for scanning SunSpec devices) and `openfmb` (the
  `protobuf` runtime, for encoding OpenFMB profiles as protobuf on the wire)

## Installation

With a VOLTTRON environment active, install from this directory and start it:

```shell
vctl install . --vip-identity platform.presentation --tag interop --start
vctl status
```

Other agents look the service up by the identity `platform.presentation`, so keep that
identity unless you also change the callers.

## Concepts

### UAI (Uniquely Addressable Identifier)

A UAI is an ordered tuple of path segments, for example
`("site1", "feeder2", "pv_inverter")`. Internally the service stores all UAIs in a tree
rooted at `uai`; each segment becomes a node. A UAI may be given as a tuple, a list, or a
JSON-encoded string of the tuple.

Resolution is *longest-prefix* by default. If `("site1", "feeder2", "pv_inverter", "W")`
is requested and no node exists for that full path, the engine walks up to
`("site1", "feeder2", "pv_inverter")` and so on until it finds a resource. Pass
`strict=True` to require an exact match.

### Resources

A leaf in the UAI tree is a resource. There are two kinds:

| Type        | Fields                                                | Meaning                                                                         |
|-------------|-------------------------------------------------------|---------------------------------------------------------------------------------|
| `canonical` | `data_format`, `owner`, `publication_topic`, `rpc_topic` | The real source of the data. `publication_topic` is the VOLTTRON pubsub topic the data appears on; `rpc_topic` is where writes go. |
| `alias`     | `data_format`, `owner`, `references`                  | A name that points at another UAI (`references`). `data_format` is the format the alias presents itself in. |

Both kinds also accept:

| Field        | Meaning |
|--------------|---------|
| `encoding`   | How the resource's messages travel on the wire: `json` (the default when unset) or `protobuf`. On an alias it is the encoding of the remote topic the alias stands for; the format declaration names the protobuf message (`proto`, below). |
| `parameters` | Per-resource values transform expressions reach with `param('name')`, for example `{"mrid": "...", "name": "ESS 1"}` for the device identity an OpenFMB header carries. An alias's parameters are merged over the canonical resource's, the outermost alias winning. |

Aliases can chain. When an alias is resolved the engine follows `references` until it
reaches a canonical resource. If the caller did not name a target format, the alias's own
`data_format` is used as the target, so an alias is a convenient way to say "this device,
but as seen through 61850." An alias whose UAI is the remote topic itself, such as
`["openfmb", "solarmodule", "SolarReadingProfile", "<mRID>"]` with
`"data_format": "openfmb.solar.reading"`, `"encoding": "protobuf"` and the device mRID in
`parameters`, is how a device is published as one OpenFMB profile on one topic.

### Formats and transforms

A *transform* is a declarative rule set that converts a message in one `input_format` to
one in an `output_format`. Transforms are stored as edges in a directed graph keyed by
format name. When a consumer asks for a resource in a format other than the one it is
published in, the registry finds the shortest path through the graph and returns the
ordered list of transform patterns along that path. If no path exists an empty list is
returned and a warning is logged.

## Configuration

The service reads a single `config` entry from the VOLTTRON configuration store with two
top-level lists, `mappings` and `transforms`, and an optional `formats` object.
`sample_config.json` in this directory shows the shape:

```json
{
  "mappings": [
    {
      "uai": ["site1", "feeder2", "pv_inverter"],
      "resource_type": "canonical",
      "resource": {
        "data_format": "sunspec",
        "owner": "platform.driver",
        "publication_topic": "devices/site1/feeder2/pv_inverter/all",
        "rpc_topic": "devices/site1/feeder2/pv_inverter"
      }
    },
    {
      "uai": ["site1", "pv_61850"],
      "resource_type": "alias",
      "resource": {
        "data_format": "61850",
        "owner": "platform.driver",
        "references": ["site1", "feeder2", "pv_inverter"]
      }
    }
  ],
  "formats": {
    "acme_inverter": { "hub": false, "fields": ["W", "V.PhaseA", "V.PhaseB", "V.PhaseC"] }
  },
  "transforms": [
    {
      "input_format": "sunspec",
      "output_format": "61850",
      "pattern": { "...": "..." }
    }
  ]
}
```

Store it with:

```shell
vctl config store platform.presentation config path/to/config.json
```

Each entry in `mappings`:

| Key             | Required | Type            | Description                                                                 |
|-----------------|----------|-----------------|-----------------------------------------------------------------------------|
| `uai`           | yes      | list or string  | The identifier being defined. A string is parsed as a JSON-encoded tuple.   |
| `resource_type` | yes      | string          | `canonical` (or `canon`) or `alias` (or `aliased`).                         |
| `resource`      | yes      | object          | The resource fields listed in the Resources table above.                    |

Each entry in `transforms`:

| Key             | Required | Type   | Description                                                          |
|-----------------|----------|--------|----------------------------------------------------------------------|
| `input_format`  | yes      | string | Format name of the incoming message.                                 |
| `output_format` | yes      | string | Format name of the produced message.                                 |
| `pattern`       | yes      | object | Output field name to transform expression (see the next section).    |
| `lossiness`     | no       | number | Overrides the measured loss of this transform, 0 (lossless) to 1, for example from an empirical round trip. |

Each entry in `formats` is keyed by format name:

| Key      | Type            | Description                                                                                   |
|----------|-----------------|-----------------------------------------------------------------------------------------------|
| `hub`    | boolean         | Whether transform chains may pass through this format. The bundled standard formats are hubs; anything else, such as a device's own point list, is a leaf by default and only ever starts or ends a chain. |
| `fields` | list of strings | The fields the format can carry, as dotted paths with `*` for repeating groups. Used to measure how much of the format a transform covers when no model package describes it (a platform driver's registry configuration is a natural source). |
| `proto`  | string          | The fully qualified protobuf message a resource in this format is encoded as when an alias asks for `"encoding": "protobuf"`, e.g. `essmodule.ESSReadingProfile`. Declared for the bundled `openfmb.<device>.<profile>` formats in `src/interoperability/formats/openfmb.json`. |

Other keys of a format declaration (`scaling`, written by the discovery tooling) are kept and
returned by the registry's `format_spec`, but the service does not act on them.

Mappings can also be added at runtime by publishing a list of mapping objects to the
`mapper/update` pubsub topic. Transforms can be added at runtime with the
`register_transform` RPC.

## Transform expression language

Each value in a `pattern` is a small expression that says where in the input message the
output field comes from and what functions to apply along the way. The grammar is parsed
with `pyparsing` and compiled to a `convtools` pipeline, so patterns are evaluated as
compiled Python rather than interpreted per message.

```
transform[<path segment>, <path segment>, ...](<function>(<args>), <function>(<args>), ...)
```

* The bracketed segments are the path into the input message. Segments may be dictionary
  keys or list indices. Bare identifiers may contain letters, digits, `_`, and `.`; a
  segment with any other character, such as `RegClas[1]`, must be quoted. Single and
  double quotes are both accepted. Unquoted digits are treated as integers.
* If the brackets are omitted, the path of output keys leading to the expression is used
  as the input path. For a nested pattern that is the full path, for example
  `("702", "WMaxRtg")`.
* The parenthesised functions are applied in order to the value found at that path. An
  empty pair of parentheses copies the value unchanged.
* Function arguments may be numbers (signed, decimal or scientific, such as `0.001`),
  quoted strings, bare identifiers, dotted paths (`phsA.mag`), or nested function calls.

Patterns may be nested. A value that is an object is a group, and the output will contain
the same group structure. This is how the bundled files organise fields under 61850
logical nodes or SunSpec model numbers. A value of `null` marks an output field with no
known source; it is skipped and does not appear in the output.

Source fields are optional. If the input message does not contain an expression's source
path, that field is left out of the output rather than raising an error, and a group whose
fields are all absent is left out too. A source that is present with a value of `null` is
copied through as `null`. This lets a transform written for a full device message be
applied to a partial update.

### Repeated groups

An output key ending in `[#]` produces a list. The group beneath it is evaluated once per
element of a source list. Inside the group, a path segment written `Pt[#]` names the list and
marks the iteration point; the segments after it are looked up in each element. Every path in
the group must name the same list.

```json
{
  "CurveData[#]": {
    "#": "transform(take('705.Crv.0.ActPt'))",
    "xvalue": "transform[705, Crv, 0, Pt[#], V]()",
    "yvalue": "transform[705, Crv, 0, Pt[#], Var]()"
  }
}
```

The reserved `"#"` entry adjusts the source. Written without a path, as above, its functions
are applied to the list the sibling paths name. Written with a path
(`"#": "transform[DERCurve, opModVoltVar](as_list())"`) it supplies the list explicitly, and
sibling paths then start with the bare segment `#`, meaning the current element
(`"ActPt": "transform[#, CurveData](count())"`). Written with functions only and no sibling
naming a list (`"#": "transform(as_list())"`), it applies the functions to the enclosing
element itself, which is how a flat message is wrapped into a one-element SunSpec `Crv` list.

Paths without a marker inside a repeated group are resolved against the message root, so
shared fields can be copied into every element. Groups nest; a path such as
`705, Crv[#], Pt[#], V` walks two levels, and a path starting with `#` always refers to the
element of the group it is written in. A repeated group whose list is absent or empty is left
out of the output, and elements whose fields are all absent are dropped.

Several groups may feed one list by adding a label after the marker, for example
`"sequence[#] volt-var"` and `"sequence[#] volt-watt"`; their lists are concatenated in
pattern order. Mistakes such as a marker outside a repeated group, sibling paths naming
different lists, or a group with no source are reported when the definition is compiled.

### Spread entries

A key starting with `*` (the rest of the key is a comment) holds an expression that produces
a group; its fields are merged into the enclosing group at that position. This turns a list of
curve points into numbered DNP3 point indices:

```json
{
  "AO": {
    "246": "transform[DERCurve, opModVoltVar, CurveData](count())",
    "*points": "transform[DERCurve, opModVoltVar, CurveData](unpairs(249, xvalue, yvalue))"
  }
}
```

Examples:

```json
{
  "foo": "transform[bar](multiple(7), add(9))",
  "bar": "transform[foo, 0](add(9), multiple(7))"
}
```

Applied to `{"foo": [5, 6], "bar": 4}` this yields `{"foo": 37, "bar": 98}`.

```json
{
  "W":   "transform[DECP, MMXU, TotW]()",
  "LNV": "transform[DECP, MMXU, PNV](mean(phsA.mag, phsB.mag, phsC.mag))"
}
```

This reads a 61850 style nested message, copies `TotW` straight through, and averages the
three phase magnitudes under `PNV`, skipping any that are missing or `None`.

Functions available in `src/interoperability/transforms/__init__.py`:

| Function                          | Effect                                                                                       |
|-----------------------------------|----------------------------------------------------------------------------------------------|
| `multiple(n)`                     | Multiply by `n`. Has an inverse.                                                             |
| `add(n)`                          | Add `n`. Has an inverse.                                                                     |
| `scale(n)`                        | Multiply by `n`, rounding away floating point noise to the decimal places of the operands (modbus_tk `scale`). Has an inverse. |
| `scale_int(n)`                    | Multiply by `n` and cast to `int`. Has an inverse.                                           |
| `scale_reg(path)`                 | Divide by the register at the quoted dotted `path`, resolved against the enclosing element; an absent register leaves the value unchanged. Has an inverse. |
| `scale_reg_pow_10(path)`          | Multiply by 10 to the power of the register at `path`, e.g. SunSpec scale factors: `scale_reg_pow_10('701.W_SF')`. Has an inverse. |
| `no_op()`                         | Copy the value unchanged. Its own inverse.                                                   |
| `mod10k(reverse)`, `mod10k64(reverse)`, `mod10k48(reverse)` | Decode the ION and PM800 M10K register formats, where each 16 bit register holds four decimal digits (modbus_tk). `reverse` may be `True`/`False`; positive values only. Have inverses. |
| `scale_decimal_int_signed(n)`     | Scale a decimal-encoded signed register (PM800 power factor style). Has an inverse.          |
| `cast_value(type_name)`           | Cast to `bool`, `str`, `int`, `float`, `list`, `tuple`, or `dict`. Boolean parsing accepts common truthy and falsy strings. |
| `mean(path, ...)`                 | Average of several dotted-path fields of the current value, ignoring missing or `None`.      |
| `take(n)`                         | Keep the first `n` elements of a list. `n` may be a quoted dotted path to the field holding the count, resolved against the element enclosing the expression (the message root at top level), e.g. `take('705.Crv.0.ActPt')`. |
| `pairs(start, count, x, y)`       | Turn a flat, position-indexed array of alternating X and Y values into a list of `{x, y}` points, e.g. `pairs(333, 100, xVal, yVal)` for DNP3 curve points. |
| `unpairs(start, x, y)`            | The inverse: lay a list of points out as numbered alternating X and Y values. Use in a spread entry. |
| `series(count, start, spec, ...)` | Gather numbered flat points into records: `series(4, 1, 'V:705_Crv1_Pt{}_V', 'Var:705_Crv1_Pt{}_Var')` turns a driver's `705_Crv1_Pt1_V` ... into `[{V, Var}, ...]`. Indices with no field present are skipped. |
| `unseries(start, spec, ...)`      | The inverse, for a spread entry: lay records out as numbered flat points.                    |
| `scale_fields(spec, ...)`         | Multiply named fields of every record in a list by constants: `scale_fields('V:0.01', 'Var:0.01')`. Has an inverse. |
| `prefix_keys(prefix)`             | Rename every key of a group by prefixing it, e.g. a DNP3 point table `{"244": 1}` to the driver's `{"AO_244": 1}`. For spread entries. Has an inverse. |
| `count()`                         | Number of elements in a list or group.                                                       |
| `as_list()`                       | Wrap the value in a one-element list.                                                        |
| `const(v)`                        | Replace the value with the literal `v` (only emitted when the source is present).            |
| `when(path, v)`                   | Pass the value through only when the field at the quoted dotted `path` equals `v`; otherwise treat it as missing. |
| `when_equal(path_a, path_b)`      | Pass the value through only when both fields are present and equal, e.g. `when_equal('AI.328', 'AI.297')`. |

Functions after a guard such as `when` are skipped once the value has become missing. Paths
given to `take`, `when`, `when_equal`, `scale_reg` and `scale_reg_pow_10` are resolved against the
element enclosing the expression: the message root at top level, or the current element inside a
repeated group. A path starting with `/` is resolved from the message root wherever it appears.

The register transforms mirror the ones in VOLTTRON's modbus_tk driver, rebuilt as convtools
conversions; where the driver looked scaling registers up by name on the device, these take a
path into the message. Functions that define an `inverse` are intended to support automatic
generation of reverse transforms in the future.

### Stage input

A `"#"` entry at the root of a pattern rebinds the input of that stage: its expression is applied
to the whole incoming message, and every other path in the pattern is then resolved against the
result (including root-relative `'/...'` paths inside repeated groups). The modular platform driver
publishes `devices/.../all` as a two-element list, `[values, meta]`, so every generated
device-format pattern starts with

```json
"#": "transform(device_values())"
```

`device_values()` yields the first element when the message is such a list and passes a bare
`{point: value}` dict through, so one pattern serves both shapes. Any expression may be used as the
rebind (`"#": "transform[payload]()"` reads a wrapped body); the rule is only allowed at the root
and directly inside a repeated group, where it has its list-naming meaning. The field map ignores
the root rebind, since it does not move the source paths.

### Parameters and generated values

Some output fields come from nowhere in the message. A library function written on its own,
without `transform[...]`, applies to the whole input and can produce such a value:

| Expression       | Produces |
|------------------|----------|
| `param('mrid')`  | the named entry of the resource's `parameters`, bound when the chain is compiled (`TransformParser(context=...)`, which `resolve` fills from the canonical resource and its aliases); an unbound name yields nothing and the field is dropped |
| `uuid4()`        | a fresh random UUID string per message |
| `timestamp()`    | the current time as `{"seconds": ..., "nanoseconds": ...}`, the OpenFMB `Timestamp` shape |

These carry nothing from the source, so they weigh nothing in the field map (like `const`).

## Bundled transforms

Transform definitions shipped with the package live in `src/interoperability/transforms/`.
The format names they use are:

| Format name       | Meaning                                                           |
|-------------------|-------------------------------------------------------------------|
| `61850`           | IEC 61850-7-420 logical nodes and data objects (DGEN, DECP, MMXU, ...) |
| `sunspec`         | SunSpec Modbus models, keyed by model number (`1`, `701`, `702`, ...) |
| `1815.2.inputs`   | IEEE 1815.2 (MESA-DER / DNP3) input points, grouped as `AI` and `BI` |
| `1815.2.outputs`  | IEEE 1815.2 output points, grouped as `AO` and `BO`, plus an optional `sequence` of point batches (see below) |
| `2030.5`          | IEEE 2030.5 resources keyed by resource then attribute (`DERCapability.rtgMaxW`); see below |
| `1547`            | IEEE 1547.1 function group and parameter names (`Nameplate` / `Active Power (unity)`) |
| `openfmb.ess`, `openfmb.solar` | OpenFMB v2.2 profiles for a storage or a solar device, in the protobuf JSON form adapters publish (`essReading.readingMMXU.W.net.cVal.mag`); see below |
| `openfmb.ess.reading`, `.status`, `.capability`, `.control`, and the `openfmb.solar.*` equivalents | One OpenFMB profile with its message header, as an adapter publishes it on one topic; leaves reached from the two hub formats above (`openfmb_profiles.json`); see below |

Every pairing of the first six formats ships as its own file, named `<input>_to_<output>.json`;
the 1815.2 files hold two definitions each, one for `1815.2.inputs` and one for
`1815.2.outputs`. The OpenFMB formats map to and from `61850` only (`openfmb_to_61850.json`,
`61850_to_openfmb.json`, two definitions each) and reach every other protocol through that hub. The IEEE 2030.5 and IEEE 1547 files, and the direct SunSpec to 1815.2
files, were derived from a single cross-reference table so the two directions of each pair
stay consistent.

Conventions the 2030.5, 1547 and SunSpec to 1815.2 files rely on, beyond those of the other files:

* `2030.5` messages are keyed by resource name and then attribute, following the parameter
  names in IEEE 2030.5-2023 Annex E and IEEE 1547.1-2020 Tables 57 to 68. Settings that
  belong to a curve live under `DERCurve.<curveType>` (for example
  `DERCurve.opModVoltVar.openLoopTms`), and the curve link attributes of `DERControl`
  (`opModVoltVar`, `opModHVRTMustTrip`, ...) carry the curve selection. Monitoring values are
  under `MirrorMeterReading` keyed by the ReadingType unit name (`W`, `var`, `Hz`, and `V`
  sub-keyed by `PhaseA`, `PhaseB`, `PhaseC`, `PhaseAB`, `PhaseBC`, `PhaseCA`). Multiplier
  sub-elements of 2030.5 quantities are not applied, just as SunSpec scale factors are not.
* `openfmb.ess` and `openfmb.solar` messages are single profiles as an OpenFMB adapter publishes
  them, so a message holds whichever of `essReading`, `essStatus`, `essControl`, `essCapability`
  (or the `solar` equivalents) that profile carries, and one transform covers all of them. Readings
  go to `DECP.MMXU`, ratings to `DGEN`, `DSTO` and `DECP.VRef`, nameplate to `LPHD.PhyNam`, status to
  `DSTO`, `DGEN` and `CALH`. Control profiles are schedules (`...ScheduleFSCH.ValDCSG.crvPts`) and map
  entry by entry onto `FSCH.SchdEntr`; in the reverse direction the 61850 top-level control nodes
  become one schedule point without a start time, followed by the `FSCH.SchdEntr` entries with
  theirs. Two formats exist because ESS and solar profiles hold the same data under different keys
  and a 61850 message must become one kind of profile. The hub formats carry no message header. The
  leaf shapes in these definitions (`setMag`, `mag`, `cVal.mag`, `stVal`, ...) follow the generated
  OpenFMB classes.
* The hub's metering node is `DECP.MMXU` (`TotW`, `TotVAr`, `TotVA`, `TotPF`, `Hz`, `PhV.phsA.mag`, `A.phsA.mag`,
  ...). The SunSpec, OpenFMB and IEEE 1815.2 files all read and write it there; the MESA profile's "system meter"
  points (AI 535 to 564, the AO limit points) that the PICS workbook names `MMXU0` live under it, so a DNP3
  outstation's readings reach the OpenFMB and SunSpec profiles. The function-specific MESA meters (`MMXU1`...) keep
  their own names.
* `openfmb.<device>.<profile>` (`openfmb.ess.reading`, `openfmb.solar.status`, ...) is a single
  profile ready to publish: `openfmb_profiles.json` selects that profile's body out of the hub
  format's dict and adds the header the hub lacks. `readingMessageInfo` (or `status`, `capability`,
  `control`) gets a fresh `uuid4()` as the message mRID and `timestamp()` as `messageTimeStamp`; the
  `ess` or `solarInverter` block gets `conductingEquipment.mRID` from `param('mrid')` and its name
  from `param('name')`, so the alias for the topic supplies the device identity in its `parameters`.
  Per OpenFMB the message mRID identifies the message and the equipment mRID the device; the sample
  generator in `models/openfmb/generate_samples.py` predates this and reuses the device mRID for both.
  The reverse definitions (`openfmb.ess.reading -> openfmb.ess`) drop the header so an inbound profile
  reaches `openfmb_to_61850.json`. A device publishes through
  `device -> sunspec -> 61850 -> openfmb.solar -> openfmb.solar.reading`, four transforms, which is
  the registry's hop limit. The formats are declared, with their protobuf message names, in
  `src/interoperability/formats/openfmb.json`, loaded as configuration defaults like the transforms.
* Schedules carry every planned control, not a decision about which one is current. In `2030.5`
  a scheduled control is an entry of `DERControlList`, a list whose entries each hold an
  `interval` (`start`, `duration` in seconds) plus the same `DERControl` and `DERCurve` groups
  used at the top level for the immediate settings. In `61850` the equivalent is
  `FSCH.SchdEntr`, a list whose entries hold `StrTm` (start, seconds), `SchdIntv` (duration,
  seconds) and the same control and curve logical nodes (`DVVR`, `DHFW`, `DFPF`, ...) used at
  the top level; the naming follows the IEC 61850 FSCH schedule node. The two lists map onto
  each other entry by entry. SunSpec and IEEE 1815.2 have no place for scheduled settings, so
  schedules do not cross into them and the field map reports the loss. Choosing the entry in
  force belongs to the consumer of the message, not to the transform.
* `1547` messages are grouped by the function group of the 1547.1 mapping tables
  (`Nameplate`, `Configuration`, `Monitoring`, `Constant PF`, `Volt-VAR`, `Watt-VAR`,
  `Constant VAR`, `Volt-Watt`, `Voltage Trip`, `Momentary Cessation`, `Frequency Trip`,
  `Frequency-Watt`, `Enter Service`, `Limit Watt`) and then by parameter name. Curve
  point arrays are copied whole between the 1547 view and a protocol.
* DNP3 indices come from the IEEE 1815.2-2025 MESA DER PICS, not the DNP3-AN2018-001
  numbers printed in IEEE 1547.1-2020, which differ for several points.
* Curves are lists. SunSpec curve points are the `Pt` list of the active stored curve
  (`Crv[0]`, trimmed to `ActPt`), 2030.5 curves are `DERCurve.<curveType>.CurveData`, and
  61850 curves are the `crvPts` list of the curve object (`DVVR.VVArCrv`,
  `DHVT.TrZnSt.PTOV.TmVCrv`, ...) with `numPts`. Writing into SunSpec emits a one-element
  `Crv` list; picking a writable stored curve and issuing `AdptCrvReq` is left to the driver.
* IEEE 1815.2 exposes curves through a single edit window: a selector (AI328 / AO244), the
  curve type (AI329 / AO245), the point count (AI330 / AO246) and up to 100 X,Y pairs from
  AI333 / AO249. Each mode only carries the index of the curve it uses (AI297 / AO217 for
  Volt-VAR). Reading is stateless: the window is mapped into a mode's curve only when the
  selector equals that mode's curve index (`when_equal`), so the outstation, or whoever polls
  it, must step the selector through the curves to read them all. Writing produces
  `sequence`, a list of `{"AO": {...}}` batches to apply in order after the plain `AO` and
  `BO` groups; within a batch the keys are in write order (select, type, count, points, then
  the mode's curve index). Each mode is written to a fixed curve slot: Volt-VAR 1, Watt-VAR 2,
  Volt-Watt 3, HVRT must trip 4, HVRT momentary cessation 5, LVRT must trip 6, LVRT momentary
  cessation 7, HFRT must trip 8, LFRT must trip 9. The generic 61850 curve logical node
  (`DGSMn`, `FMARn.PairArr.CrvPts`) maps the window directly, without a guard.
* Bitmaps whose bit assignments differ between protocols (`DERCapability.modesSupported`,
  SunSpec `CtrlModes`, DNP3 BI31 to BI51) are only copied to and from the `1547` view.

At startup the agent loads every JSON file directly inside `transforms/` and `mappings/`
as configuration defaults. Subdirectories are ignored. Anything supplied through the
configuration store is applied on top of these defaults.

## Device formats

The platform driver (always the modular `volttron-platform-driver` package and its interface libraries,
whichever VOLTTRON runtime hosts it) publishes a device as a flat `{point name: value}` message, wrapped
on `devices/.../all` as `[values, meta]` with the point metadata (units, type) in the second element. That
flat point list is a format of its own: a leaf in the transform graph that maps onto one protocol and reaches the
others through it. Every generated device-to-protocol pattern begins with the stage input
`"#": "transform(device_values())"`, so the same pattern reads either the wrapped or the bare message. When the device speaks SunSpec and its registry names each point after the SunSpec path it
holds (`701_W`, `704_PFWInj_PF`, `705_Crv1_ActPt`, `705_Crv1_Pt3_Var`, `708_Crv1_MustTrip_Pt1_V`, with
a 1-based index on repeating groups), `interoperability.discovery.device_formats` derives everything from the
names alone, validated against the SunSpec model classes:

* `sunspec_point_path('705_Crv1_Pt3_Var')` gives `('705', 'Crv', 0, 'Pt', 2, 'Var')`.
* `sunspec_device_transforms(format_name, point_names)` gives the two transform definitions between the
  device format and `sunspec`. Repeating groups become one-element lists; numbered point rows become
  `series()` lists trimmed to the group's `ActPt`; the reverse flattens them again with `unseries()`.
* `device_format_declaration(point_names, scaling)` gives the `formats` entry (a leaf whose fields are
  the points, recording who applies scale factors).
* `resource_mappings(device_format, device_topic, uai, alias_formats)` gives the canonical resource and one
  alias per requested format. An alias is a format name, or a dict `{"format", "encoding", "parameters", "uai"}`
  when it should be published as protobuf, carry per-resource parameters, or live under another UAI, as an
  OpenFMB topic alias does.

**Scale factors.** SunSpec values are integers scaled by a companion `_SF` register, and where that
scaling happens is a build-time choice, `scaling`, that fixes the registry and the transforms together:

* `transform`: the driver publishes raw registers, the `_SF` points included. Reads apply
  `scale_reg_pow_10('/705_V_SF')` against the published factor (the leading `/` resolves the path from
  the message root, even inside a curve). Writes bake the discovered factor in as a constant with
  `scale()` and `scale_fields()`, since a write arriving from another protocol carries no factor; points
  whose factor was not discovered are listed in the result's `notes` and left unscaled.
* `driver`: the driver applies the factors itself. The modbus registry carries a `Transform` column
  entry per scaled point (`scale_reg_pow_10(705_V_SF)`, the modbus_tk syntax the platform driver is
  adopting), the `_SF` points are omitted, and the transforms pass values through unchanged.

`infer_scaling(rows)` tells the two apart for an existing registry. Whichever side scales, the SunSpec
message that comes out is the same; the integration test asserts it.

**Discovery.** `interoperability.discovery.sunspec` (extra `discovery`, which installs pysunspec2) scans
a device over Modbus TCP or RTU, or reads a pysunspec2 JSON device description offline, and writes the
whole configuration set: a registry for the `modbus` driver with absolute addresses and register types,
a registry for the `fake` driver with the discovered values as starting values, the device configs for
both, the presentation service configuration and a `vctl` script:

```shell
PYTHONPATH=src python -m interoperability.discovery.sunspec --host 10.0.0.21 --unit 1 --scaling driver --out build/
PYTHONPATH=src python -m interoperability.discovery.sunspec --file device.json --out build/   # offline
```

`tests/integration/fake_sunspec/` is the worked case: `device_1547.json` (pysunspec2's 1547 test device,
models 1 and 701 to 713 with three stored curves per curve model), `build_configs.py` generating one
configuration set per scaling mode, and `tests/test_integration_fake_sunspec.py` driving the fake driver's
`all` message (in both its shapes) through the `sunspec`, `2030.5` and `1815.2.inputs` aliases and through
an `openfmb.solar.reading` alias under an OpenFMB topic, protobuf-encoded, exactly as the service resolves
it, in both modes, and checking that the generated files are current.

**IEEE 1815.2 devices.** The same machinery serves an outstation behind the `dnp3` driver, with point names
`<table>_<index>` (`AI_297`, `AO_217`, `BI_93`), validated against the service's IEEE 1815.2 point
registry. `dnp3_device_transforms` maps the device onto `1815.2.inputs` (AI, BI, CTR) and
`1815.2.outputs` (the AO and BO read-back), and back from `1815.2.outputs` only, since inputs are
read-only on a device; the curve edit window's `sequence` batches are carried to the device as ordered
lists of flat points. Multipliers and offsets come from the profile, so both scaling modes work without
device discovery: `transform` applies them on the device edge, `driver` writes them into the registry's
`Transform` column (`scale(0.1)`) and `Scaling` column for the driver to apply with their inverses. The
current dnp3 driver applies neither, so `transform` is the mode that works today. DNP3 has no
self-description: `interoperability.discovery.dnp3` takes the point set from a test-tool profile file
(`--profile mandatory_1547.json`) or from any index listing such as an integrity poll, and writes the
same configuration set as the SunSpec tool. `tests/integration/fake_dnp3/` is the worked case, with
`tests/test_integration_fake_dnp3.py` covering reads to `sunspec`, `2030.5` and `61850` and writes back
through the edit window in both modes.

**IEEE 2030.5.** There is no register device to discover: the VOLTTRON 2030.5 agent mirrors a driver
device to a 2030.5 server through a point map of `Object::property` rows. `interoperability.discovery.point_maps`
generates that map for any device format that reaches `2030.5`, from the composed field map of the
chosen chain; curve points and meter readings, which the agent configures elsewhere, are listed in the
notes. Messages from a 2030.5 source are already in the service's `2030.5` format and need no device
format. The `2030.5` field universe is derived from the generated `sep` models following the service's
convention.

## Choosing between chains

When more than one chain of transforms connects two formats, the registry picks the one that
preserves the most meaning, not the shortest. Each registered pattern is analysed, without
running it, into a field map: which source fields reach which target fields, and with what
fidelity. Fidelity is 1 for a plain copy or an invertible function, and lower for functions
that lose information (`scale_int` and `take` 0.9, guards such as `when_equal` 0.7, `mean`
0.5, `count` 0.3, `const` 0). An author can mark an approximate mapping with `approx(f)`,
which copies the value unchanged but records that only a fraction `f` of its meaning carries
over. Field maps compose along a chain, so a field dropped at the first hop cannot reappear
later.

A lookup enumerates every chain of up to four hops whose intermediate formats are hubs,
scores each on the same set of source fields (the fields a resource publishes if the caller
supplies them, otherwise every source field any candidate's first step reads), and keeps the
chain with the highest retention; ties go to fewer hops. Leaf formats never appear in the
middle of a chain, so adding hundreds of device formats adds no candidate chains between the
standards. The hubs by default are the bundled standard formats, including the two OpenFMB
formats. Each edge also carries a weight, `-ln(retention) + 0.01`, measured against the
format's full field universe (from the model packages for SunSpec and IEEE 1815.2, from the
`formats` configuration, or failing both from the fields the registered transforms mention).
That number is informational, available through `score_transform`, and small in absolute
terms for broad formats like SunSpec, whose universe spans every published model.

## Agent interface

RPC methods exported by the service:

| Method                                              | Returns                  | Description                                                                                                   |
|-----------------------------------------------------|--------------------------|---------------------------------------------------------------------------------------------------------------|
| `resolve(uai, as_format=None, strict=False)`        | dict                     | Resolve a UAI to its canonical resource. When `as_format` is given (or the UAI is an alias, whose format is used), the result also includes `target_format` and `transform`, the ordered list of transform patterns from the resource's `data_format` to `as_format` (empty when they are the same format), `parameters` (the canonical resource's merged with each alias's, outermost winning), `encoding` (`json` unless an alias declares otherwise) and, for a non-JSON encoding, `codec`: `{"encoding": "protobuf", "proto": "<format's protobuf message>"}`. Returns `{}` if nothing canonical is found, fails with a `TransformNotFoundError` if the resource cannot be converted to `as_format`, and with a `ValueError` if protobuf is asked for a format that declares no `proto`. |
| `lookup_transform(input_format, output_format)`     | list of pattern dicts    | The transform chain between two formats. An empty list means no transform is needed (same format). When no chain exists the call fails with a `TransformNotFoundError` saying whether a format is unknown or the formats are simply not connected. |
| `register_transform(input_format, output_format, pattern, update=False, lossiness=None)` | bool | Add a transform edge at runtime. If the pair already has a different transform it is kept, with a warning, unless `update` is true. Registering the same pattern again is a no-op. Malformed patterns are rejected here. Returns whether the registry changed. |
| `score_transform(input_format, output_format, fields=None)` | dict | The chain `lookup_transform` would choose, as `path` (the formats passed through) and `retention`, the fraction of source fields that reach the end, scored over `fields` if given. |

Pubsub subscriptions:

| Topic           | Payload                  | Effect                                              |
|-----------------|--------------------------|-----------------------------------------------------|
| `mapper/update` | list of mapping objects  | Ingests the mappings into the UAI tree at runtime.  |

## Consuming a resource from another agent

`interoperability.resource.ResourceData` is a client-side helper. It resolves a UAI through
the service, compiles the returned transform with the resource's `parameters` bound, subscribes
to the canonical publication topic, and delivers transformed payloads to your callback under
your own local topic, encoded as the resource's `codec` says (`bytes` for a protobuf alias;
`encode` and `decode` are also available directly for the message bus adapter's inbound path).

```python
from interoperability.resource import ResourceData

def on_data(peer, sender, bus, topic, headers, message):
    ...  # message is already in the requested format

resource = ResourceData.lookup(self, ('site1', 'feeder2', 'pv_inverter'))
if resource:
    resource.subscribe(on_data)
```

`lookup` accepts a tuple, a list, or a delimited string (default delimiter `/`). It returns
`None` when the UAI does not resolve to a canonical resource, and also when it does resolve
but no transform can convert the resource into the format the alias asks for; the reason is
logged as a warning. A resource that is already in the requested format is delivered
unchanged. Other RPC failures, such as the service being unreachable, are raised.

## Repository layout

```
interoperability_service/
  pyproject.toml                  Poetry package metadata (name: interoperability-service)
  setup.py                        Legacy VOLTTRON agent packaging shim
  sample_config.json              Skeleton of the config store entry
  src/interoperability/
    agent.py                      PresentationService agent, RPC and pubsub endpoints
    mapping_engine.py             UAI tree, resource nodes, resolution and alias following
    resource.py                   Resource pydantic models and the ResourceData client helper
    transform_parser.py           Expression grammar and convtools pipeline builder
    transform_registry.py         networkx graph of transforms between formats
    discovery/                    configuration tooling, not needed at runtime
      device_formats.py           a driver's flat point list as a format; SunSpec and DNP3 transforms from point names
      sunspec.py                  registries and configuration from a SunSpec device scan (pysunspec2)
      dnp3.py                     registries and configuration from an IEEE 1815.2 profile or point listing
      point_maps.py               the IEEE 2030.5 agent's point map, generated from field maps
    field_universe.py             every field a format can carry, from models, configuration or the transforms
    codecs/                       wire codecs: protobuf encoding of OpenFMB profiles (extra ``openfmb``)
    transforms/                   Bundled transform JSON files and the transform function library
    formats/                      Bundled format declarations (the OpenFMB profile formats and their protobuf messages)
    mappings/                     Bundled default mappings (currently none)
    models/openfmb/               OpenFMB pydantic models generated from the protobuf PSM, plus profile builders and sample generator
    models/openfmb/proto/         the vendored psm-protobuf-python bindings the codec and the model generator read
    models/sunspec/               Generated SunSpec Modbus models (one module per model id), SunSpecDevice container, builders
    models/ieee1815_2/            Generated IEEE 1815.2 (MESA-DER) point enums, function-group profiles, PointDatabase, builders
    models/ieee2030_5/            Generated IEEE 2030.5 schema types, enums and builders
  tests/                          pytest suite for the parser, registry, bundled files, loader, and the generated protocol models
  doc/                            Placeholder, currently empty
```

### Where the transform files came from

The `1815.2_to_61850.json` and `61850_to_1815.2.json` files were built from the
`MESA_DER_PICS_for use in 1815.2 v3.xlsx` workbook, and the IEEE 2030.5, IEEE 1547 and
SunSpec to 1815.2 files from a cross-reference table of the IEEE 1547.1 mapping tables.
Neither source nor the scripts that read them are part of this package; edit the JSON files
directly.

### OpenFMB models

`models/openfmb/` is generated by its `generate_models.py` from the OpenFMB protobuf PSM
(v2.2, the `psm-protobuf-python` bindings kept at `openfmb/psm-protobuf-python` in this
workspace), which is the authority for message shapes. There is one package per OpenFMB module
(`ess_module`, `solar_module`, `common_module`, ...) holding a pydantic class per protobuf
message and an `Enum` per enumeration; `PROFILES` maps the 67 profile names to their classes.
The classes follow protobuf's JSON mapping, which is what OpenFMB adapters publish: field names
as in the `.proto` files (`essReading.readingMMXU.W.net.cVal.mag`), enumerations by name,
wrapper types collapsed to scalars, 64 bit integers accepted as strings or numbers. Unknown
fields are rejected, so a message of the wrong shape fails validation rather than silently
matching nothing. Regeneration needs `protobuf>=6.31` on the path; the generated package needs
only pydantic. `profile_builders.py` offers hand-written constructors for the DER profiles and
`generate_samples.py` writes example messages to `solar_json_output/`. The `openfmb` field
universe used by the transform registry is derived from these classes.

The protobuf bindings themselves are vendored in `models/openfmb/proto/` (see its `SOURCE.md`),
and `interoperability.codecs.openfmb` uses them to turn a transform's output dict into protobuf
bytes and back (`encode`, `decode`), keyed by the message name the format declares as `proto`.
This needs the `protobuf` runtime, installed by the `openfmb` extra; nothing else in the service
does.

### SunSpec, IEEE 1815.2 and IEEE 2030.5 models

The sibling packages `models/sunspec/`, `models/ieee1815_2/` and `models/ieee2030_5/` give
the other three DER protocols the same treatment: pydantic models of every class the
standard defines plus keyword-only `build_*` constructors in a `profile_builders.py`. All
three are generated; each package has a `generate_models.py` whose docstring names the
source and the command. Run the generators as scripts from this directory, for example
`python src/interoperability/models/sunspec/generate_models.py`, so a broken generated
module cannot stop regeneration. Hand-written code lives only in each package's
`common.py` and in the generators.

| Package        | Source                                                                                     | Shape                                                                                                                                                                                                                                       |
|----------------|--------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `sunspec`      | SunSpec Alliance `models/json/model_*.json` (copy under `1547_standards/SunSpecModbus/`)   | One module per model id (`models/model_701.py`). Group classes mirror the model's groups; repeating groups are lists. `enum16` / `bitfield32` points get `IntEnum` / `IntFlag` classes but also accept plain ints. Point metadata (type, size, units, scale-factor point, access, mandatory) is kept in `json_schema_extra`, and `scaled_value()` applies the scale factor. `SunSpecDevice` is the `{model_id: model}` mapping the `sunspec` transform format uses and dispatches each entry to its class. |
| `ieee1815_2`   | `full.json` profile of the IEEE 1815.2 test tool (`ieee-std-1815-2-test-tool/data/profiles/`) | `points.py` has an `IntEnum` per point type named by IEC 61850 identifier (`AI.DGEN_WMaxRtg == 4`) and a `POINTS` registry of `PointDefinition` metadata. `profiles.py` has one class per function group (`Nameplate`, `VoltVar`, `Curve`, `Scheduling`, ...) split into `AI` / `AO` / `BI` / `BO` / `CTR` sub-models, plus `Meter`, `Inverter`, `Battery` and `DERUnit` blocks that resolve indexes by instance number. `to_points()` / `from_points()` convert to and from the flat `PointDatabase`, whose `inputs()` and `outputs()` match the `1815.2.inputs` and `1815.2.outputs` formats. |
| `ieee2030_5`   | Eclipse VOLTTRON's xsdata dataclasses of `sep.xsd` (Apache-2.0, pinned to one commit; downloaded on regeneration) | `sep.py` has all 283 schema types with the schema's inheritance, element and attribute names, descriptions and integer bounds; hex-binary values are hex strings. Every field is optional so partial payloads validate, and `missing_required()` reports what the schema would still demand. `enums.py` carries the enumerations the source defines. Builders are generated for resources, not for `*Link` or `*List` containers. |

The 2030.5 source reflects the 2018 edition of the schema; the 2023 additions are not in
it. None of these models are wired into the transform registry yet, but their field names
match what the bundled transform definitions address.

## Running the tests

```shell
pytest tests
```

The suite exercises the expression language, checks that every bundled transform
definition compiles, verifies lookups in the registry, confirms the agent's default loader
reads the bundled files, exercises `resolve` and the `ResourceData` helper, round-trips OpenFMB
profiles through the protobuf codec, and instantiates every OpenFMB, SunSpec, IEEE 1815.2 and
IEEE 2030.5 model and builder. The loader, resolve and helper tests are skipped if VOLTTRON is
not installed; the codec tests if `protobuf` is not.

`tests/test_e2e_dnp3_to_openfmb.py` runs the whole telemetry path in a subprocess: a dnp3py outstation
serving the fake DNP3 case's points, the modular DNP3 driver interface through the real DNP3 protocol
proxy, the driver's `[values, meta]` message, this service's chain to `openfmb.ess.reading` and its
protobuf encoding, the message bus adapter, and the MQTT proxy's publish (paho mocked). It needs the
driver stack, the DNP3 proxy, dnp3py, the bus adapter and protobuf importable, and is skipped otherwise;
the `~/Scratch/drivers_proxies/.venv` environment has all of them.

## Status and known limitations

This is an early-stage service. Things to be aware of:

* **Transform weighting** is measured from the patterns alone (see "Choosing between chains"
  above). It does not know when a mapping is semantically approximate unless the author marks
  it with `approx()`, and there is no empirical round-trip check yet; the `lossiness` override
  exists so one can be applied when it is written.
* Agent-level tests cover `resolve` and the default loader only; the remaining RPC and pubsub
  behavior is untested.
* The transform chain runs in one direction, canonical format to alias format. Inbound messages
  in an alias's format (a control profile from a remote bus) still need inverse chains, which
  exist only as a TODO in `transform_parser.py`.

## License

Apache License 2.0. Developed at Pacific Northwest National Laboratory, operated by
Battelle for the United States Department of Energy under Contract DE-AC05-76RL01830.
