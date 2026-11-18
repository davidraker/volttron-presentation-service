"""The whole contract of a served outstation's multiplexed areas: the builder's registry rows, read by the driver's row
model, registered as the interface registers them, build the proxy's stores; a master then edits a curve through the
buffer and the platform sees store rows. Skipped where the driver interface or the proxy is not importable."""
import asyncio

import pytest

pytest.importorskip('dnp3.mesa')
dnp3_interface = pytest.importorskip('volttron.driver.interfaces.dnp3.dnp3')
dnp3_config = pytest.importorskip('volttron.driver.interfaces.dnp3.config')
server = pytest.importorskip('protocol_proxy.protocol.dnp3.server')
client = pytest.importorskip('protocol_proxy.protocol.dnp3.client')

from interoperability.discovery import service as discovery_service  # noqa: E402

TOPIC = 'site/served'


def registration(result):
    """Rows and remote config of a discovery result, through the driver's row model and register, as the registration carries them."""
    rows = next(e for e in result['entries'] if e['type'] == 'csv')['data']
    device = next(e for e in result['entries'] if e['name'].startswith('devices/'))['data']
    points = []
    for row in rows:
        cfg = dnp3_config.Dnp3PointConfig(**row)
        register = dnp3_interface.Dnp3Register(cfg)
        points.append(register.point_fields(f'devices/{TOPIC}/{cfg.volttron_point_name}', served=True))
    return points, device['remote_config']


class Pushes:
    def __init__(self):
        self.values = {}

    async def __call__(self, values):
        self.values.update(values)


def test_a_composed_outstation_serves_its_curves_to_a_master():
    asyncio.run(_composed_outstation_serves_its_curves_to_a_master())


async def _composed_outstation_serves_its_curves_to_a_master():
    result = discovery_service.discover('dnp3', {'topic': TOPIC, 'role': 'server', 'conformance': 'none', 'bind_host': '127.0.0.1', 'port': 0,
                                                 'compose': {'functions': ['volt_var'], 'curves': {'pairs': 4, 'stored': 3}}}, None)
    points, remote = registration(result)
    assert remote['driver_role'] == 'outstation' and remote['mux_areas']['curve']['references'][0]['point'] == {'group': 40, 'index': 217}
    store_rows = [p for p in points if str(p.get('mux_slot', '')) not in ('', 'selector')]
    assert len(store_rows) == 3 * (4 + 8) and all(p['readback']['group'] == 30 for p in store_rows)
    pushes = Pushes()
    served = server.ServedOutstation('127.0.0.1', 0, outstation_address=1, master_address=2, push=pushes)
    count = served.configure_points(points, {}, remote['mux_areas'])
    assert count == len(points)
    area = served.mux.areas['curve']
    assert area.slots == 3 and area.selector[1] == 244
    await served.start()
    host, port = served.runner.local_address
    master = client.OutstationClient(host, port, master_address=2, outstation_address=1, response_timeout=3.0, integrity_poll_interval=0)
    # curve X and Y values carry no multiplier in the point list (their units are chosen per curve), so raw is engineering
    master.configure_points([{'topic': 'm/sel', 'group': 40, 'index': 244}, {'topic': 'm/x1', 'group': 40, 'index': 249},
                             {'topic': 'm/x1_rb', 'group': 30, 'index': 333}, {'topic': 'm/crvidx', 'group': 40, 'index': 217},
                             {'topic': 'm/referenced', 'group': 1, 'index': 107}])
    try:
        results, errors = await master.write([{'topic': 'm/sel', 'value': 2}])
        assert errors == {}
        results, errors = await master.write([{'topic': 'm/x1', 'value': 95}])
        assert errors == {}
        await asyncio.sleep(0.05)
        assert pushes.values[f'devices/{TOPIC}/curve_Selector'] == 2.0 and pushes.values[f'devices/{TOPIC}/curve2_X1'] == 95.0
        results, errors = await master.read(['m/x1_rb', 'm/referenced'], mode='integrity')
        assert results['m/x1_rb']['value'] == 95.0 and results['m/referenced']['value'] is False
        await master.write([{'topic': 'm/crvidx', 'value': 2}])
        results, _ = await master.read(['m/referenced'], mode='integrity')
        assert results['m/referenced']['value'] is True, 'Volt-Var now references the selected curve'
        results, _ = await served.read([f'devices/{TOPIC}/curve2_X1', f'devices/{TOPIC}/curve1_X1'])
        assert results[f'devices/{TOPIC}/curve2_X1']['value'] == 95.0 and results[f'devices/{TOPIC}/curve1_X1']['online'] is False
    finally:
        await master.close()
        await served.close()
