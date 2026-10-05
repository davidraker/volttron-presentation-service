"""An external SunSpec inverter and an external Modbus master, both on uModbus (an independent Modbus implementation,
not the pymodbus our proxy uses).

``SunSpecDevice`` is a Modbus TCP slave holding the fake_sunspec_pv register map (the platform's Modbus master polls
it and writes controls to it); ``ModbusMaster`` reads and writes a unit the platform serves. Values are typed by the
registry's ``Data Type`` column and stored as big-endian 16-bit words, as SunSpec specifies."""
import csv
import re
import socket
import struct
import threading
from pathlib import Path
from socketserver import TCPServer

from umodbus import conf
from umodbus.client import tcp
from umodbus.server.tcp import RequestHandler, get_server

conf.SIGNED_VALUES = False

FORMATS = {'INT16': '>h', 'UINT16': '>H', 'INT32': '>i', 'UINT32': '>I', 'INT64': '>q', 'UINT64': '>Q', 'FLOAT32': '>f'}


class PointTable:
    """The registry's points: name -> (address, data type, register count)."""
    def __init__(self, registry_csv: Path):
        self.points: dict[str, tuple[int, str, int]] = {}
        self.defaults: dict[str, object] = {}
        with Path(registry_csv).open(newline='') as f:
            for row in csv.DictReader(f):
                name, dtype = row['Volttron Point Name'], row['Data Type'].strip()
                address = int(row['Point Address'])
                self.points[name] = (address, dtype, self.count_of(dtype))
                default = row.get('Default Value', '')
                if default not in ('', None):
                    self.defaults[name] = self.parse(dtype, default)

    @staticmethod
    def count_of(dtype: str) -> int:
        if m := re.fullmatch(r'string\[(\d+)\]', dtype, re.IGNORECASE):
            return (int(m.group(1)) + 1) // 2                     # string[N]: N characters, two per register
        return struct.calcsize(FORMATS[dtype.upper()]) // 2

    @staticmethod
    def parse(dtype: str, text: str):
        if dtype.lower().startswith('string'):
            return text
        return float(text) if dtype.upper() == 'FLOAT32' else int(float(text))

    @staticmethod
    def to_words(dtype: str, value) -> list[int]:
        if dtype.lower().startswith('string'):
            count = PointTable.count_of(dtype)
            data = str(value).encode('utf8')[:2 * count].ljust(2 * count, b'\x00')
        else:
            fmt = FORMATS[dtype.upper()]
            data = struct.pack(fmt, float(value) if fmt == '>f' else int(value))
        return list(struct.unpack(f'>{len(data) // 2}H', data))

    @staticmethod
    def from_words(dtype: str, words: list[int]):
        data = struct.pack(f'>{len(words)}H', *words)
        if dtype.lower().startswith('string'):
            return data.rstrip(b'\x00').decode('utf8', 'replace')
        return struct.unpack(FORMATS[dtype.upper()], data)[0]


class SunSpecDevice:
    """A Modbus TCP slave (unit ``unit_id``) whose holding registers are the registry's points at their addresses,
    seeded from the registry's default values. The harness reads and sets its state directly: it *is* the device."""
    def __init__(self, registry_csv: Path, host: str = '127.0.0.1', port: int = 0, unit_id: int = 1):
        self.table = PointTable(registry_csv)
        self.unit_id = unit_id
        self.words: dict[int, int] = {}
        self.written: list[tuple[str, object]] = []        # what masters wrote, in order
        self._lock = threading.Lock()
        for name, value in self.table.defaults.items():
            self.set_point(name, value)
        for name, (address, dtype, count) in self.table.points.items():
            for a in range(address, address + count):
                self.words.setdefault(a, 0)
        TCPServer.allow_reuse_address = True
        self.server = get_server(TCPServer, (host, port), RequestHandler)
        self.host, self.port = self.server.server_address[:2]
        words = self.words
        lock = self._lock
        device = self

        @self.server.route(slave_ids=[unit_id], function_codes=[3, 4], addresses=list(words))
        def read(slave_id, address, function_code):
            with lock:
                return words[address]

        @self.server.route(slave_ids=[unit_id], function_codes=[6, 16], addresses=list(words))
        def write(slave_id, address, value, function_code):
            with lock:
                words[address] = int(value) & 0xFFFF
            device._note_write(address)
        self._thread = threading.Thread(target=self.server.serve_forever, name='sunspec-device', daemon=True)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def _note_write(self, address: int):
        for name, (start, dtype, count) in self.table.points.items():
            if start <= address < start + count:
                self.written.append((name, self.get_point(name)))
                return

    def set_point(self, name: str, value):
        address, dtype, count = self.table.points[name]
        with self._lock:
            for i, word in enumerate(PointTable.to_words(dtype, value)):
                self.words[address + i] = word

    def get_point(self, name: str):
        address, dtype, count = self.table.points[name]
        with self._lock:
            return PointTable.from_words(dtype, [self.words[address + i] for i in range(count)])

    def writes_of(self, name: str) -> list:
        return [v for n, v in self.written if n == name]


class ModbusMaster:
    """An external Modbus TCP master (uModbus client) reading and writing the unit the platform serves."""
    def __init__(self, registry_csv: Path, host: str, port: int, unit_id: int = 1, timeout: float = 5.0):
        self.table = PointTable(registry_csv)
        self.host, self.port, self.unit_id, self.timeout = host, port, unit_id, timeout

    def _call(self, adu):
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
            return tcp.send_message(adu, sock)

    def read_point(self, name: str):
        address, dtype, count = self.table.points[name]
        words = self._call(tcp.read_holding_registers(self.unit_id, address, count))
        return PointTable.from_words(dtype, list(words))

    def write_point(self, name: str, value):
        address, dtype, count = self.table.points[name]
        words = PointTable.to_words(dtype, value)
        if len(words) == 1:
            return self._call(tcp.write_single_register(self.unit_id, address, words[0]))
        return self._call(tcp.write_multiple_registers(self.unit_id, address, words))
