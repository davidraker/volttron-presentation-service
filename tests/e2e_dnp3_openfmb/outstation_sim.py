"""A dnp3py outstation serving the fake DNP3 case's point set: every row of the fake driver registry becomes a point
with its starting value, overridden by the JSON given as the third argument ({"AI_537": 12500, ...}). Every control is
accepted; analog output commands are tracked into the database by the outstation itself."""
import asyncio
import csv
import json
import sys

from dnp3.core.enums import ControlCode
from dnp3.core.flags import AnalogQuality, BinaryQuality, CounterQuality
from dnp3.database import (AnalogInputConfig, AnalogOutputConfig, BinaryInputConfig, BinaryOutputConfig, CounterConfig,
                           Database, EventClass)
from dnp3.outstation import CommandResult, DefaultCommandHandler, Outstation, OutstationConfig, OutstationTcpRunner


class Handler(DefaultCommandHandler):
    def __init__(self, database):
        self.database = database

    def _binary(self, index, code):
        if code in (ControlCode.LATCH_ON, ControlCode.LATCH_OFF):
            self.database.update_binary_output(index, code == ControlCode.LATCH_ON, quality=BinaryQuality.ONLINE)
        return CommandResult.success()

    def select_binary_output(self, index, code, count, on_time, off_time):
        return CommandResult.success()

    def operate_binary_output(self, index, code, count, on_time, off_time, select_sequence):
        return self._binary(index, code)

    def direct_operate_binary_output(self, index, code, count, on_time, off_time):
        return self._binary(index, code)

    def select_analog_output(self, index, value):
        return CommandResult.success()

    def operate_analog_output(self, index, value, select_sequence):
        return CommandResult.success()

    def direct_operate_analog_output(self, index, value):
        return CommandResult.success()


def build_database(registry_csv: str, overrides: dict) -> Database:
    db = Database()
    with open(registry_csv, newline='') as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        name = row['Volttron Point Name']
        table, index = name.split('_', 1)
        index = int(index)
        raw = overrides.get(name, row['Starting Value'])
        if table == 'AI':
            db.add_analog_input(index, AnalogInputConfig(event_class=EventClass.CLASS_1))
            db.update_analog_input(index, float(raw or 0), quality=AnalogQuality.ONLINE)
        elif table == 'BI':
            db.add_binary_input(index, BinaryInputConfig(event_class=EventClass.CLASS_1))
            db.update_binary_input(index, str(raw).lower() in ('true', '1'), quality=BinaryQuality.ONLINE)
        elif table == 'BO':
            db.add_binary_output(index, BinaryOutputConfig())
            db.update_binary_output(index, str(raw).lower() in ('true', '1'), quality=BinaryQuality.ONLINE)
        elif table == 'AO':
            db.add_analog_output(index, AnalogOutputConfig())
            db.update_analog_output(index, float(raw or 0), quality=AnalogQuality.ONLINE)
        elif table == 'CTR':
            db.add_counter(index, CounterConfig())
            db.update_counter(index, int(float(raw or 0)), quality=CounterQuality.ONLINE)
    return db


async def main(port: int, registry_csv: str, overrides: dict):
    database = build_database(registry_csv, overrides)
    outstation = Outstation(config=OutstationConfig(address=1, master_address=2), database=database, handler=Handler(database))
    await OutstationTcpRunner(outstation=outstation, host='127.0.0.1', port=port).run()


if __name__ == '__main__':
    asyncio.run(main(int(sys.argv[1]), sys.argv[2], json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}))
