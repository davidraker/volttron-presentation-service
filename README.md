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

Aliases can chain. When an alias is resolved the engine follows `references` until it
reaches a canonical resource. If the caller did not name a target format, the alias's own
`data_format` is used as the target, so an alias is a convenient way to say "this device,
but as seen through 61850."

### Formats and transforms

A *transform* is a declarative rule set that converts a message in one `input_format` to
one in an `output_format`. Transforms are stored as edges in a directed graph keyed by
format name. When a consumer asks for a resource in a format other than the one it is
published in, the registry finds the shortest path through the graph and returns the
ordered list of transform patterns along that path. If no path exists an empty list is
returned and a warning is logged.

## Configuration

The service reads a single `config` entry from the VOLTTRON configuration store with two
top-level lists, `mappings` and `transforms`. `sample_config.json` in this directory shows
the shape:

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
* Function arguments may be integers, quoted strings, bare identifiers, dotted paths
  (`phsA.mag`), or nested function calls.

Patterns may be nested. A value that is an object is a group, and the output will contain
the same group structure. This is how the bundled files organise fields under 61850
logical nodes or SunSpec model numbers. A value of `null` marks an output field with no
known source; it is skipped and does not appear in the output.

Source fields are optional. If the input message does not contain an expression's source
path, that field is left out of the output rather than raising an error, and a group whose
fields are all absent is left out too. A source that is present with a value of `null` is
copied through as `null`. This lets a transform written for a full device message be
applied to a partial update.

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
| `scale_int(n)`                    | Multiply by `n` and cast to `int`. Has an inverse.                                           |
| `scale_decimal_int_signed(n)`     | Scale a decimal-encoded signed register (PM800 power factor style). Has an inverse.          |
| `cast_value(type_name)`           | Cast to `bool`, `str`, `int`, `float`, `list`, `tuple`, or `dict`. Boolean parsing accepts common truthy and falsy strings. |
| `mean(path, ...)`                 | Average of several dotted-path fields of the current value, ignoring missing or `None`.      |

`scale`, `scale_reg`, `scale_reg_pow_10`, `no_op`, and the `mod10k*` family are declared
but not yet implemented. Functions that define an `inverse` are intended to support
automatic generation of reverse transforms in the future.

## Bundled transforms

Transform definitions shipped with the package live in `src/interoperability/transforms/`.
The format names they use are:

| Format name       | Meaning                                                           |
|-------------------|-------------------------------------------------------------------|
| `61850`           | IEC 61850-7-420 logical nodes and data objects (DGEN, DECP, MMXU, ...) |
| `sunspec`         | SunSpec Modbus models, keyed by model number (`1`, `701`, `702`, ...) |
| `1815.2.inputs`   | IEEE 1815.2 (MESA-DER / DNP3) input points, grouped as `AI` and `BI` |
| `1815.2.outputs`  | IEEE 1815.2 output points, grouped as `AO` and `BO`                 |

| File                      | Direction                                                    |
|---------------------------|--------------------------------------------------------------|
| `1815.2_to_61850.json`    | `1815.2.inputs` -> `61850` and `1815.2.outputs` -> `61850`   |
| `61850_to_1815.2.json`    | `61850` -> `1815.2.inputs` and `61850` -> `1815.2.outputs`   |
| `61850_to_sunspec.json`   | `61850` -> `sunspec`                                         |
| `sunspec_to_61850.json`   | `sunspec` -> `61850`                                         |

The `transforms/unfinished/` directory holds drafts that are not loaded. The
`1547_related/` drafts map IEEE 1547 functional names to and from each protocol and still
use human-readable descriptions on the right-hand side rather than transform expressions.
`sunspec_61850_curves.json` holds the curve-point mappings between SunSpec models 705 to
712 and the 61850 DER curve nodes, which use a `[#]` "for each point" placeholder the
language does not support yet. The remaining drafts cover IEEE 2030.5 and direct SunSpec
to 1815.2 conversions.

At startup the agent loads every JSON file directly inside `transforms/` and `mappings/`
as configuration defaults. Subdirectories are ignored. Anything supplied through the
configuration store is applied on top of these defaults.

## Agent interface

RPC methods exported by the service:

| Method                                              | Returns                  | Description                                                                                                   |
|-----------------------------------------------------|--------------------------|---------------------------------------------------------------------------------------------------------------|
| `resolve(uai, as_format=None, strict=False)`        | dict                     | Resolve a UAI to its canonical resource. When `as_format` is given, the result also includes `target_format` and `transform`, the ordered list of transform patterns from the resource's `data_format` to `as_format`. Returns `{}` if nothing canonical is found. |
| `lookup_transform(input_format, output_format)`     | list of pattern dicts    | The transform chain between two formats, or `[]` if there is no path.                                         |
| `register_transform(input_format, output_format, pattern)` | none              | Add a transform edge at runtime.                                                                              |

Pubsub subscriptions:

| Topic           | Payload                  | Effect                                              |
|-----------------|--------------------------|-----------------------------------------------------|
| `mapper/update` | list of mapping objects  | Ingests the mappings into the UAI tree at runtime.  |

## Consuming a resource from another agent

`interoperability.resource.ResourceData` is a client-side helper. It resolves a UAI through
the service, compiles the returned transform, subscribes to the canonical publication
topic, and delivers transformed payloads to your callback under your own local topic.

```python
from interoperability.resource import ResourceData

def on_data(peer, sender, bus, topic, headers, message):
    ...  # message is already in the requested format

resource = ResourceData.lookup(self, ('site1', 'feeder2', 'pv_inverter'))
if resource:
    resource.subscribe(on_data)
```

`lookup` accepts a tuple, a list, or a delimited string (default delimiter `/`).

## Repository layout

```
interoperability_service/
  pyproject.toml                  Poetry package metadata (name: interoperability-service)
  setup.py                        Legacy VOLTTRON agent packaging shim
  sample_config.json              Skeleton of the config store entry
  openfmb_information_model.py    Pydantic models generated from OpenFMBInformationModel.json
  src/interoperability/
    agent.py                      PresentationService agent, RPC and pubsub endpoints
    mapping_engine.py             UAI tree, resource nodes, resolution and alias following
    resource.py                   Resource pydantic models and the ResourceData client helper
    transform_parser.py           Expression grammar and convtools pipeline builder
    transform_registry.py         networkx graph of transforms between formats
    transforms/                   Bundled transform JSON files and the transform function library
    transforms/unfinished/        Draft transforms that are not loaded
    mappings/                     Bundled default mappings (currently none)
    models/openfmb/               Hand-organised OpenFMB pydantic models by module, plus profile builders and sample generators
    scripts/DNP3_and_IEC61850.py  Builds 1815.2 <-> 61850 transform JSON from the MESA DER PICS spreadsheet
  src/mapping/                    Scratch scripts for deriving mappings from the IEEE 1547 mapping spreadsheet
  tests/                          pytest suite for the parser, registry, bundled files, and loader
  doc/                            Placeholder, currently empty
```

### Generating transform files

`src/interoperability/scripts/DNP3_and_IEC61850.py` reads the
`MESA_DER_PICS_for use in 1815.2 v3.xlsx` workbook (not included in the repository) and
emits the `1815.2_to_61850.json` and `61850_to_1815.2.json` files. It needs `pandas`,
`numpy`, and `openpyxl`, which are not runtime dependencies of the service. The scripts in
`src/mapping/` play a similar role for the IEEE 1547 functional mapping spreadsheet kept
alongside the `interoperability_agent` project, and `convert_interop_agent.py` converts
that agent's older mapping dictionaries into transform expressions.

### OpenFMB models

`models/openfmb/` contains pydantic models for each OpenFMB module (breaker, cap bank,
ESS, EVSE, generation, interconnection, load, meter, recloser, regulator, reserve,
resource, solar, switch, and common types). `profile_builders.py` provides keyword-only
constructors for full profiles and imports the regenerated information model from the
sibling `openfmb` project in this workspace, so it needs that project importable to run.
`generate_samples.py` produces example solar reading and status profiles as JSON. These
models are groundwork for an `openfmb` data format and are not yet wired into the
transform registry.

## Running the tests

```shell
pytest tests
```

The suite exercises the expression language, checks that every bundled transform
definition compiles, verifies multi-hop lookups in the registry, and confirms the agent's
default loader reads the bundled files. The loader test is skipped if VOLTTRON is not
installed.

## Status and known limitations

This is an early-stage service. Things to be aware of:

* **Array and curve mappings are not supported.** There is no way to express "for each
  element of a list" in a pattern, so curve-point mappings are parked in
  `transforms/unfinished/`.
* **Transform weighting.** All transform edges have weight 0, so path selection is by hop
  count only. Weighting by lossiness is a planned improvement.
* **Inverse transforms** are attached to several functions but reverse pipelines are not
  yet generated automatically.
* **No default mappings ship with the package.** The `mappings/` directory is empty, so
  UAIs must be supplied through the configuration store or the `mapper/update` topic.
* There are no agent-level tests; the service's RPC and pubsub behaviour is untested.

## License

Apache License 2.0. Developed at Pacific Northwest National Laboratory, operated by
Battelle for the United States Department of Energy under Contract DE-AC05-76RL01830.
