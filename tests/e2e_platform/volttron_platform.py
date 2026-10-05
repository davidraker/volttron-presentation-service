"""A real VOLTTRON platform (volttron-core 2.0.0rc36, ZMQ, auth on) in a fresh VOLTTRON_HOME, run from this venv.

Reuses the Modbus driver's ``platform_cli.PlatformCLI`` (start, vctl install/config store, shutdown). The platform
records the environment in a poetry project; the pre-seeded project leaves out the dnp3py packages, whose git and path
sources poetry cannot reconcile, which is harmless: agents import from this venv regardless."""
import os
import sys
from pathlib import Path

PYMODBUS_TESTS = Path(os.environ.get('PYMODBUS_DRIVER_REPO', '/home/dmr/Projects/volttron/modular/drivers/interfaces/pymodbus')) / 'tests'
sys.path.insert(0, str(PYMODBUS_TESTS))
import platform_cli                                                   # noqa: E402
from platform_cli import PlatformCLI, PlatformError                    # noqa: E402

EXCLUDED = {'protocol-proxy-dnp3', 'dnp3py', 'volttron-lib-dnp3-driver', 'volttron-testing'}   # unlockable git/path sources; a pytest<8 pin
_original_project = platform_cli.poetry_project_for_current_environment

AGENTS = [('/home/dmr/Projects/volttron/modular/drivers/platform-driver-agent', 'platform.driver', 'driver'),
          ('/home/dmr/Projects/der_control_modules/interoperability_service', 'platform.presentation', 'interop'),
          ('/home/dmr/Projects/der_control_modules/device-adapter', 'platform.device_adapter', 'device_adapter'),
          ('/home/dmr/Projects/der_control_modules/message-bus-adapter', 'platform.bus_adapter', 'bus_adapter')]


def poetry_project() -> str:
    """platform_cli's pyproject for this environment without the packages poetry cannot lock together."""
    text = _original_project()
    lines = [line for line in text.splitlines()
             if not any(line.startswith(f'"{name}"') for name in EXCLUDED)]
    return '\n'.join(lines) + '\n'


class Platform(PlatformCLI):
    def __init__(self, home: Path, instance_name: str = 'der-e2e'):
        super().__init__(home)
        self.instance_name = instance_name

    def start(self, timeout: float = 900.0):
        platform_cli.PLATFORM_CONFIG = platform_cli.PLATFORM_CONFIG.replace('modbus-driver-test', self.instance_name)
        platform_cli.poetry_project_for_current_environment = poetry_project
        super().start(timeout)

    def install_all(self, log=print):
        import time
        for source, identity, tag in AGENTS:
            t0 = time.time()
            self.install_agent(source, identity, tag)
            log(f'installed {identity} in {time.time() - t0:.0f}s')

    def store_all(self, entries, log=print):
        for entry in entries:
            self.store_config(entry.identity, entry.name, entry.path, csv=(entry.kind == 'csv'))
        log(f'stored {len(entries)} configuration entries')
