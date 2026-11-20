"""A real VOLTTRON platform (ZMQ, auth on) in a fresh VOLTTRON_HOME, run from this venv.

Built on volttron-testing's ``PlatformCLI`` (start, vctl install/config store, shutdown). The platform records the
environment in a poetry project; the project leaves out the dnp3py packages, whose git and path sources poetry cannot
reconcile, which is harmless: agents import from this venv regardless.

The agents are installed from their checkouts, found by ``volttrontesting.configs.AgentSources``: the Platform Driver
through ``VOLTTRON_MODULAR_DRIVERS``, an editable install, the modular tree, or else PyPI; this service, the Resource
Bridge, the Message Bus Adapter and the RTC agent (none published) through ``DER_CONTROL_MODULES`` (the directory
holding their checkouts) or an editable install."""
from pathlib import Path

from volttrontesting.configs import AgentSources, AgentSpec
from volttrontesting.platform_cli import PlatformCLI, PlatformError    # noqa: F401  (PlatformError re-exported)

# Unlockable git/path sources, and the RTC agent's classic-VOLTTRON pin.
EXCLUDED = ('protocol-proxy-dnp3', 'dnp3py', 'volttron-lib-dnp3-driver', 'volttron-realtime-control')

SOURCES = AgentSources()
for name, distribution, checkout in (('interoperability-service', 'interoperability-service', 'interoperability_service'),
                                     ('resource-bridge', 'volttron-resource-bridge', 'resource-bridge'),
                                     ('message-bus-adapter', 'volttron-message-bus-adapter', 'message-bus-adapter'),
                                     ('rtc-agent', 'volttron-realtime-control', 'rtc_agent')):
    SOURCES.register(name, distribution=distribution, tree=('DER_CONTROL_MODULES', checkout), published=False)

AGENTS = [AgentSpec('platform-driver', 'platform.driver', 'driver'),
          AgentSpec('interoperability-service', 'platform.presentation', 'interop'),
          AgentSpec('resource-bridge', 'platform.resource_bridge', 'resource_bridge'),
          AgentSpec('message-bus-adapter', 'platform.bus_adapter', 'bus_adapter')]
RTC_AGENT = AgentSpec('rtc-agent', 'der.rtc', 'rtc')     # the real-time control agent (--rtc)


class Platform(PlatformCLI):
    def __init__(self, home: Path, instance_name: str = 'der-e2e'):
        super().__init__(home, instance_name, exclude=EXCLUDED)

    def start(self, timeout: float = 900.0):
        return super().start(timeout)

    def install_all(self, log=print, include_rtc=False):
        self.install(AGENTS + ([RTC_AGENT] if include_rtc else []), SOURCES, log)

    def store_all(self, entries, log=print):
        for entry in entries:
            self.store_config(entry.identity, entry.name, entry.path, csv=(entry.kind == 'csv'))
        log(f'stored {len(entries)} configuration entries')
