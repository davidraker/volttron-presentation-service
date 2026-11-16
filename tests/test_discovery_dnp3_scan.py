"""Scanning a DNP3 outstation for its points: an integrity poll of dnp3py's MESA outstation, loaded from a bundled
IEEE 1815.2 profile, lists the profile's points, so the live scan and the profile file yield the same registry rows.

Two things about that dummy, not about the scan: it also serves the standard's equipment points at 5000 and up, which
the profile does not list, and it keeps analog outputs outside its database, so class 0 carries no group 40 and the AO
table is absent. The IEEE 1815.2 test tool's reference outstation reports every table."""
from __future__ import annotations

import asyncio
import json
import threading
from importlib import resources

import pytest

pytest.importorskip('dnp3.mesa')

from interoperability.discovery import service as discovery_service  # noqa: E402
from interoperability.discovery.dnp3 import discover_indexes, discover_profile  # noqa: E402
from interoperability.discovery.dnp3_scan import TABLE_GROUPS, ScanResult, scan_outstation, scan_outstation_isolated  # noqa: E402

PROFILE = resources.files('dnp3.mesa') / 'data' / 'profiles' / 'mandatory_1547.json'
MASTER, OUTSTATION = 2, 1


class RunningOutstation:
    """dnp3py's MESA outstation on a free port, in a thread with its own event loop."""

    def __init__(self, profile_path):
        from dnp3.mesa import create_mesa_outstation
        self.outstation = create_mesa_outstation(profile_path, host='127.0.0.1', port=0, address=OUTSTATION, master_address=MASTER)
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def _serve(self):
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.outstation.run())
        except asyncio.CancelledError:
            pass

    def __enter__(self):
        self.thread.start()
        for _ in range(200):
            if self.outstation.is_running and self.outstation.local_address:
                self.port = self.outstation.local_address[1]
                return self
            threading.Event().wait(0.05)
        raise RuntimeError('the outstation did not bind')

    def __exit__(self, *exc):
        # stop() sets the runner's shutdown flag; run() then returns on its own and the thread's loop completes.
        asyncio.run_coroutine_threadsafe(self.outstation.stop(), self.loop).result(5)
        self.thread.join(5)
        self.loop.close()


def profile_indexes(path) -> dict[str, list[int]]:
    data = json.loads(path.read_text())
    rows = {table: (data[table].get('points', []) if isinstance(data[table], dict) else data[table]) for table in TABLE_GROUPS if table in data}
    return {table: sorted(int(p['point_index']) for p in points) for table, points in rows.items() if points}


def assert_covers_profile(indexes: dict[str, list[int]], expected: dict[str, list[int]]):
    for table, points in expected.items():
        if table == 'AO':
            continue                                    # see the module docstring: the dummy's class 0 has no group 40
        assert set(points) <= set(indexes.get(table, [])), f'{table}: the scan misses {sorted(set(points) - set(indexes.get(table, [])))[:10]}'


def test_scan_lists_the_outstations_points():
    expected = profile_indexes(PROFILE)
    with RunningOutstation(PROFILE) as running:
        result = scan_outstation('127.0.0.1', running.port, MASTER, OUTSTATION, timeout=10)
    assert_covers_profile(result.indexes, expected)
    assert 'AI_537' in result.values and isinstance(result.values['AI_537'], float) and isinstance(result.values['BI_0'], bool)
    assert result.points == sum(len(v) for v in result.indexes.values())
    assert [n for n in result.notes if 'ONLINE' not in n] == []                 # only the offline note, if the dummy serves any
    assert all(name in result.values for name in result.offline)


def test_points_without_the_online_flag_are_listed_and_noted():
    """The IEEE 1815.2 reference outstation adds its counters without an initial update, so they carry RESTART (0x02)
    and no ONLINE until a freeze-and-clear; the driver would report them offline on every poll. The scan says so."""
    from types import SimpleNamespace
    from interoperability.discovery.dnp3_scan import _handler_class, QUALITY_ONLINE
    handler = _handler_class()()
    handler.on_analog_input([SimpleNamespace(index=537, value=4200.0, quality=QUALITY_ONLINE)], None)
    handler.on_counter([SimpleNamespace(index=0, value=0, quality=0x02), SimpleNamespace(index=1, value=0, quality=QUALITY_ONLINE | 0x02)], None)
    handler.on_binary_input([SimpleNamespace(index=0, value=True)], None)      # no quality attribute: taken as online
    assert handler.quality['CTR'] == {0: 0x02, 1: 0x03} and handler.quality['BI'][0] == QUALITY_ONLINE
    result = ScanResult()
    for table, seen in handler.seen.items():
        if seen:
            result.indexes[table] = sorted(seen)
            result.offline += [f'{table}_{i}' for i in result.indexes[table] if not handler.quality[table][i] & QUALITY_ONLINE]
    assert result.offline == ['CTR_0']
    again = ScanResult.from_json(json.loads(json.dumps(ScanResult(result.indexes, {}, ['n'], result.offline).to_json())))
    assert again.offline == ['CTR_0'] and again.notes == ['n']


def test_scan_in_a_subprocess_and_the_discover_rpc_match_the_profile():
    with RunningOutstation(PROFILE) as running:
        isolated = scan_outstation_isolated('127.0.0.1', running.port, MASTER, OUTSTATION, timeout=10)
        assert isinstance(isolated, ScanResult)
        assert_covers_profile(isolated.indexes, profile_indexes(PROFILE))
        found = discovery_service.discover('dnp3', {'topic': 'site/der1', 'outstation_ip': '127.0.0.1', 'port': running.port, 'master_id': MASTER, 'outstation_id': OUTSTATION}, None)
    assert found['source'].startswith(f'outstation 127.0.0.1:{running.port}')
    from_file = discover_profile(PROFILE)
    from_scan = discover_indexes(isolated.indexes, isolated.values, 'scan')
    scanned_names, file_names = {p.name for p in from_scan.points}, {p.name for p in from_file.points}
    assert file_names - scanned_names <= {n for n in file_names if n.startswith('AO_')}, 'the live scan and the profile file describe the same device'
    registry = next(e for e in found['entries'] if e['type'] == 'csv')
    assert {row.get('volttron_point_name') or row.get('point_name') for row in registry['data']} == scanned_names
    device = next(e for e in found['entries'] if e['name'] == 'devices/site/der1')
    assert device['data']['remote_config']['port'] == running.port and found['remote_id'][:2] == ['dnp3', '127.0.0.1']


def test_no_outstation_is_a_clear_error():
    with pytest.raises(RuntimeError, match='no DNP3 outstation answered'):
        scan_outstation('127.0.0.1', 1, MASTER, OUTSTATION, timeout=1)
    with pytest.raises(ValueError, match='no DNP3 outstation answered'):
        discovery_service.discover('dnp3', {'topic': 'x', 'outstation_ip': '127.0.0.1', 'port': 1, 'timeout': 1}, None)
