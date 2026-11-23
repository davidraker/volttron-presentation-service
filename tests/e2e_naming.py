"""Names the two matrix harnesses share (``e2e_matrix/harness.py``, in process, and ``e2e_platform``, on a real
platform): the protocols and their formats, the OpenFMB families and mRIDs, and how a party's UAI, device topic and
bridge are named. One copy, so the two harnesses cannot drift apart."""
import csv
import os
from pathlib import Path

TESTS = Path(__file__).resolve().parent

SUNSPEC_CASE = TESTS / 'integration' / 'fake_sunspec' / 'transform_scaling'
DNP3_CASE = TESTS / 'integration' / 'fake_dnp3' / 'transform_scaling'
DEVICES = ('SunSpec', 'DNP3', '2030.5')
CLIENT_FORMAT = {'SunSpec': 'fake_sunspec_pv', 'DNP3': 'fake_dnp3_der', '2030.5': 'fake_sunspec_pv_sep2'}
SERVED_FORMAT = {'SunSpec': 'fake_sunspec_pv', 'DNP3': 'fake_dnp3_der_served', '2030.5': 'fake_sunspec_pv_sep2_served'}
OPENFMB_FAMILY = {'SunSpec': 'solar', 'DNP3': 'ess', '2030.5': 'ess'}
PROFILE = {'solar': 'Solar', 'ess': 'ESS'}
PROTO = {'solar': ('solarmodule.SolarReadingProfile', 'solarmodule.SolarControlProfile'),
         'ess': ('essmodule.ESSReadingProfile', 'essmodule.ESSControlProfile')}
MRID = {('SunSpec', 'client'): '7d1a2b3c-0000-4000-8000-000000000001', ('SunSpec', 'served'): '7d1a2b3c-0000-4000-8000-000000000011',
        ('DNP3', 'client'): '9c2e4f10-0000-4000-8000-000000000002', ('DNP3', 'served'): '9c2e4f10-0000-4000-8000-000000000012',
        ('2030.5', 'client'): '5e6f7a80-0000-4000-8000-000000000003', ('2030.5', 'served'): '5e6f7a80-0000-4000-8000-000000000013'}
RTC_UAI = ['matrix', 'RTC']
RTC_FORMAT = 'rtc_controller'
for _role in ('rtc', 'client', 'served'):
    MRID[('RTC', _role)] = 'a1b2c3d4-0000-4000-8000-000000000021'
OPENFMB_FAMILY['RTC'] = 'ess'
CEE_APP_PATH = os.environ.get('CEE_APP_PATH', str(TESTS.parents[1] / 'ctrl-eval-engine' / 'app'))
JULIA_PATH = os.environ.get('JULIA', str(Path.home() / '.juliaup' / 'bin' / 'julia'))


def uai(protocol, role):
    return ['matrix', protocol, role]


def device_topic(protocol, role):
    return f'devices/matrix/{protocol}/{role}'


def roles(kind, src, dst):
    """Which role of each party a path uses: our side's device at the source and at the target."""
    if kind == 'telemetry':
        return ('served' if src == '2030.5' else 'client'), ('client' if dst == '2030.5' else 'served')
    return ('client' if src == '2030.5' else 'served'), ('served' if dst == '2030.5' else 'client')


def bridge_name(kind, src, dst):
    return f'{kind}_{src}_{dst}'.replace('.', '_')


def openfmb_alias(protocol, role, kind):
    family = OPENFMB_FAMILY[protocol]
    return ['openfmb', f'{family}module', f'{PROFILE[family]}{"Reading" if kind == "reading" else "Control"}Profile', MRID[(protocol, role)]]


def rows_of(path):
    with Path(path).open(newline='') as f:
        return list(csv.DictReader(f))
