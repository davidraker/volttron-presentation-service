"""Tooling that turns what a device exposes into configuration: device formats, their transforms, driver
registries and the service's mappings, from a SunSpec scan, an IEEE 1815.2 profile or a driver registry.

* :mod:`.device_formats`  a driver's flat point list as a format, with SunSpec and DNP3 point naming and the
  transforms between the device format and the protocol format
* :mod:`.sunspec`         SunSpec discovery with pysunspec2 (needs the ``discovery`` extra)
* :mod:`.dnp3`            IEEE 1815.2 point sets from a profile file or an index listing
* :mod:`.point_maps`      the IEEE 2030.5 agent's point map, generated from field maps

Nothing at runtime depends on this package; the service only needs the configuration it produces.
"""
