"""Scan a reachable DNP3 outstation for the points it implements.

IEEE 1815.2 fixes what every index means, so the one thing a device adds is which indexes it has. An integrity
poll (READ of classes 0 to 3) answers that: every static object the outstation reports is an implemented point.
The result is the ``{table: [index, ...]}`` listing :func:`interoperability.discovery.dnp3.discover_indexes`
takes, plus the values read, which seed the fake registry.

The poll runs on dnp3py's asyncio master. The service agent runs on gevent, so it does not run the poll in its
own process: :func:`scan_outstation_isolated` runs this module as a subprocess and reads its JSON.

    python -m interoperability.discovery.dnp3_scan --host 127.0.0.1 --port 20000 --master-id 2 --outstation-id 1
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any

#: The 1815.2 tables and the static object groups an integrity poll reports them in.
TABLE_GROUPS = {'AI': 30, 'AO': 40, 'BI': 1, 'BO': 10, 'CTR': 20}
QUALITY_ONLINE = 0x01       # bit 0 of every DNP3 quality byte; clear means the outstation does not vouch for the value


@dataclass
class ScanResult:
    indexes: dict[str, list[int]] = field(default_factory=dict)      # table -> sorted indexes
    values: dict[str, Any] = field(default_factory=dict)             # "AI_537" -> value read
    notes: list[str] = field(default_factory=list)
    offline: list[str] = field(default_factory=list)                 # points reported without the ONLINE quality flag

    @property
    def points(self) -> int:
        return sum(len(v) for v in self.indexes.values())

    def to_json(self) -> dict:
        return {'indexes': self.indexes, 'values': self.values, 'notes': self.notes, 'offline': self.offline}

    @classmethod
    def from_json(cls, data: dict) -> 'ScanResult':
        return cls({k: [int(i) for i in v] for k, v in data.get('indexes', {}).items()}, dict(data.get('values', {})), list(data.get('notes', [])),
                   list(data.get('offline', [])))


def _handler_class():
    from dnp3.master import DefaultSOEHandler

    class RecordingHandler(DefaultSOEHandler):
        """Every static value the poll delivers, by table and index."""

        def __init__(self):
            super().__init__()
            self.seen: dict[str, dict[int, Any]] = {table: {} for table in TABLE_GROUPS}
            self.quality: dict[str, dict[int, int]] = {table: {} for table in TABLE_GROUPS}

        def _record(self, table, values, cast):
            for v in values:
                self.seen[table][v.index] = cast(v.value)
                self.quality[table][v.index] = int(getattr(v, 'quality', QUALITY_ONLINE))

        def on_binary_input(self, values, info):
            self._record('BI', values, bool)
            return super().on_binary_input(values, info)

        def on_binary_output(self, values, info):
            self._record('BO', values, bool)
            return super().on_binary_output(values, info)

        def on_analog_input(self, values, info):
            self._record('AI', values, float)
            return super().on_analog_input(values, info)

        def on_analog_output(self, values, info):
            self._record('AO', values, float)
            return super().on_analog_output(values, info)

        def on_counter(self, values, info):
            self._record('CTR', values, int)
            return super().on_counter(values, info)

    return RecordingHandler


async def scan_outstation_async(host: str, port: int = 20000, master_id: int = 2, outstation_id: int = 1, timeout: float = 10.0) -> ScanResult:
    """One integrity poll of the outstation at host:port; the implemented points per table and their values."""
    try:
        from dnp3.master import Master, MasterConfig, MasterTcpRunner
    except ImportError as e:   # pragma: no cover - depends on the environment
        raise RuntimeError('scanning a DNP3 outstation needs the dnp3py package: pip install "interoperability-service[discovery]"') from e
    handler = _handler_class()()
    master = Master(handler=handler, config=MasterConfig(address=master_id, outstation_address=outstation_id))
    runner = MasterTcpRunner(master=master, host=host, port=port, response_timeout=timeout)
    try:
        async with runner:
            infos = await asyncio.wait_for(runner.integrity_poll(), timeout=timeout * 3)
    except Exception as e:      # dnp3py's ChannelError family, OSError, a timeout: one message for the caller
        raise RuntimeError(f'no DNP3 outstation answered at {host}:{port} (master {master_id}, outstation {outstation_id}): {e or type(e).__name__}') from e
    result = ScanResult()
    for table, seen in handler.seen.items():
        if seen:
            result.indexes[table] = sorted(seen)
            result.values.update({f'{table}_{index}': seen[index] for index in result.indexes[table]})
            result.offline += [f'{table}_{index}' for index in result.indexes[table] if not handler.quality[table][index] & QUALITY_ONLINE]
    if result.offline:
        shown = ', '.join(result.offline[:8]) + (' …' if len(result.offline) > 8 else '')
        result.notes.append(f'{len(result.offline)} point(s) are served without the ONLINE quality flag ({shown}): the outstation has not '
                            'updated them since it started (typical of counters it never increments). The driver reports such points as '
                            'offline on every poll until the outstation sets them; leave them out of the registry if the device never will.')
    truncated = [info for info in infos if getattr(info, 'truncation', None)]
    if truncated:
        result.notes.append(f'{len(truncated)} response fragment(s) were truncated; some points may be missing')
    if not result.indexes:
        result.notes.append('the outstation answered the integrity poll with no static objects')
    return result


def scan_outstation(host: str, port: int = 20000, master_id: int = 2, outstation_id: int = 1, timeout: float = 10.0) -> ScanResult:
    """:func:`scan_outstation_async` from synchronous code without a running event loop."""
    return asyncio.run(scan_outstation_async(host, port, master_id, outstation_id, timeout))


def scan_outstation_isolated(host: str, port: int = 20000, master_id: int = 2, outstation_id: int = 1, timeout: float = 10.0) -> ScanResult:
    """The scan in a subprocess of this interpreter: the service agent's gevent loop and dnp3py's asyncio stay apart."""
    cmd = [sys.executable, '-m', 'interoperability.discovery.dnp3_scan', '--host', host, '--port', str(port), '--master-id', str(master_id),
           '--outstation-id', str(outstation_id), '--timeout', str(timeout), '--json']
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout * 4 + 15)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f'the DNP3 scan of {host}:{port} did not finish in time') from e
    if done.returncode != 0:
        message = (done.stderr or done.stdout).strip().splitlines()
        raise RuntimeError(message[-1] if message else f'the DNP3 scan of {host}:{port} failed ({done.returncode})')
    return ScanResult.from_json(json.loads(done.stdout))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Integrity-poll a DNP3 outstation and list the points it implements, per IEEE 1815.2 table.')
    p.add_argument('--host', required=True)
    p.add_argument('--port', type=int, default=20000)
    p.add_argument('--master-id', type=int, default=2, help='this master\'s DNP3 address')
    p.add_argument('--outstation-id', type=int, default=1, help='the outstation\'s DNP3 address')
    p.add_argument('--timeout', type=float, default=10.0, help='seconds to wait for each response fragment')
    p.add_argument('--json', action='store_true', help='print the result as JSON (indexes, values, notes)')
    args = p.parse_args(argv)
    try:
        result = scan_outstation(args.host, args.port, args.master_id, args.outstation_id, args.timeout)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result.to_json()))
    else:
        for table, indexes in result.indexes.items():
            print(f'{table}: {len(indexes)} points: {", ".join(map(str, indexes[:20]))}{" …" if len(indexes) > 20 else ""}')
        for note in result.notes:
            print(f'note: {note}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
