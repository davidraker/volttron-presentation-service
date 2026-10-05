# Outside-in matrix on a real VOLTTRON platform

`run.py` stands up a real VOLTTRON instance from this venv and surrounds it with independent
implementations of every protocol, then drives the 24 telemetry and control paths between SunSpec,
DNP3, IEEE 2030.5 and OpenFMB from the outside: a stimulus at one external party, an observation at
another. The platform is a black box.

| Role | Implementation | Where |
|---|---|---|
| Platform | volttron-core (ZMQ, auth on), platform driver, presentation service, Device Adapter, Message Bus Adapter | `volttron_platform.py`, configured by `configs.py` through the config store |
| SunSpec inverter and SunSpec master | uModbus (not the pymodbus the proxy uses) | `external/sunspec_device.py` |
| DNP3 outstation and DNP3 master | IEEE 1815.2 test tool reference binaries (Rust, Step Function `dnp3` crate), from its cargo-cache volume, in its backend image on the host network | `external/dnp3_tool.py` |
| 2030.5 utility server | GridAPPS-D Go `sep2server` (`sep2server:e2e`, traffic capture on) | `external/sep2.py` |
| 2030.5 DER client | GridAPPS-D Go `inverterclient` (`inverterclient:e2e`, built from the client repo with a two-stage Dockerfile) | `external/sep2.py` |
| OpenFMB broker and participant | `eclipse-mosquitto:2`, paho-mqtt with the protobuf bindings | `external/openfmb_party.py` |

```shell
python tests/e2e_platform/run.py --openfmb bus      # OpenFMB on the VOLTTRON bus: bus adapter relays, Device Adapter translates
python tests/e2e_platform/run.py --openfmb rpc      # bus adapter translates and writes through the Device Adapter's RPC
E2E_PLATFORM=1 pytest tests/test_e2e_platform.py    # both, about 13 minutes each
```

`--keep` leaves the platform and the containers running; `--only telemetry:SunSpec>DNP3,...` runs a
subset; `--work DIR` (default `/tmp/e2e-platform`) holds the VOLTTRON_HOME, the configuration files,
the certificates, the Go server's traffic capture, the external parties' logs and
`device_adapter_reports.log` (the Device Adapter's result topics, recorded with `vctl subscribe`).

## What each check means

Telemetry is standing state at the external source. SunSpec and OpenFMB report distinct quantities
(W and Hz; var and a phase voltage) so what arrives at a shared target is attributable; the 2030.5
client's reports are its simulator's (DERSettings.setMaxW 10000, DERCapability, a PV curve), so the
checks on its paths look for those. Controls carry a limit that differs per source and per target,
because the bridges write changes only: a repeated value would not be a new write. The reference
outstation logs the analog operates it receives but not the binary ones, so BO_17 (the enable) is
verified through the Device Adapter's report of the outstation's DNP3 response, not independently.

## Environment it needs

- Docker with `sep2server:e2e`, `inverterclient:e2e`, `eclipse-mosquitto:2` and the test tool's
  `ieee-std-1815-2-test-tool-backend-dev` image plus its `ieee-std-1815-2-test-tool_cargo-cache`
  volume holding the compiled `reference-outstation` and `reference-control-station`.
- This venv with the driver stack, the proxies, `volttron`/`vctl`, `umodbus`, `paho-mqtt`, `protobuf`,
  and `volttron-lib-auth` matching `volttron-core` (rc36 needs rc11 or later).
- Poetry on the path: the platform records the environment in a poetry project on first start;
  `volttron_platform.py` leaves out the packages whose git and path sources cannot be locked together.

## Findings this stack surfaced (fixed unless noted)

- Platform driver: `set_multiple_points` planned every point of every remote and sent the whole list
  to each; foreign remotes refused the topics and the refusals were reported as failures.
- Presentation service: a stored config replaced the bundled hub transforms instead of adding to them.
- IPC: a frame larger than the 32 KB receive ring never completed (a 384-row served registration).
- Served 2030.5 server: the Go client POSTs readings to `<mup>/mr`; a superseded immediate control
  stayed listed and the Go client kept applying it (it arbitrates between listed events by order).
- DNP3: the generated registries use floating-point analog outputs (g41v3/v4); the 1815.2 profile is
  integer with multipliers and the reference outstation accepts g41v1/v2 only. The e2e overrides the
  AO variation to 1; the generator default is still open.
- Convention, not fixed: the service's `2030.5` format carries `opModMaxLimW` in percent while the
  schema (and the Go client) use hundredths of a percent: a limit of 50 is applied as 0.5 %.
- Limitation: the Go server exposes neither usage points nor readings; its traffic capture is the only
  outside view of the MirrorMeterReadings it accepts.
