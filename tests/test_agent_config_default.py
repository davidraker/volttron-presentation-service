"""Regression test for issue #1: set_default needs a config name.

Both host config stores (the fastlib compatibility layer and upstream
VOLTTRON) implement `set_default(name, value)` and match a subscription
`pattern` against that same name with fnmatch. Calling `set_default` with
only a value raises a TypeError on either host, and even where it did not,
the default would never reach `configure_main` because no name would match
the subscribed pattern.
"""

from typing import Any

import interoperability.agent as agent_module

STUB_MAPPINGS = [{'id': 'stub-mapping'}]
STUB_TRANSFORMS = [{'id': 'stub-transform'}]
STUB_FORMATS = {'stub.format': {'hub': False}}


class _FakeConfigStore:
    """Records calls the way both hosts' real config stores do."""

    def __init__(self) -> None:
        self.set_default_calls: list[tuple[Any, Any]] = []
        self.subscribe_calls: list[tuple[Any, Any, Any]] = []

    def set_default(self, name, value):
        self.set_default_calls.append((name, value))

    def subscribe(self, callback, actions=None, pattern=None):
        self.subscribe_calls.append((callback, actions, pattern))


def _build_service(monkeypatch):
    """Constructs PresentationService with a stub vip.config, bypassing the
    real Agent transport, and with bundled-definition loading stubbed to
    fixed values so the assertions do not depend on the bundled JSON files.
    """
    fake_config = _FakeConfigStore()

    def fake_agent_init(self, **kwargs):
        self.vip = type('FakeVip', (), {'config': fake_config})()

    def fake_load_bundled_definitions(directory) -> list[dict]:
        return STUB_MAPPINGS if directory.name == 'mappings' else STUB_TRANSFORMS

    monkeypatch.setattr(agent_module.Agent, '__init__', fake_agent_init)
    monkeypatch.setattr(
        agent_module.PresentationService,
        '_load_bundled_definitions',
        staticmethod(fake_load_bundled_definitions),
    )
    monkeypatch.setattr(agent_module.PresentationService, '_load_bundled_formats', staticmethod(lambda directory: STUB_FORMATS))
    service = agent_module.PresentationService()
    return service, fake_config


def test_set_default_is_called_with_a_name_and_the_bundled_value(monkeypatch):
    service, fake_config = _build_service(monkeypatch)

    assert len(fake_config.set_default_calls) == 1
    name, value = fake_config.set_default_calls[0]
    assert value == {}                                   # the bundled definitions are the base, not the default entry
    assert service._bundled == {'mappings': STUB_MAPPINGS, 'transforms': STUB_TRANSFORMS, 'formats': STUB_FORMATS}
    assert isinstance(name, str) and name


def test_set_default_uses_the_name_configure_main_subscribes_to(monkeypatch):
    _, fake_config = _build_service(monkeypatch)

    default_name, _ = fake_config.set_default_calls[0]
    _, _, subscribed_pattern = fake_config.subscribe_calls[0]
    assert default_name == subscribed_pattern
