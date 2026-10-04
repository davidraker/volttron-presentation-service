from interoperability import openfmb_bus


def test_openfmb_bus_convention():
    h = openfmb_bus.headers('essmodule.ESSControlProfile', 'platform.device_adapter', remote=('mqtt', 'site'))
    assert openfmb_bus.is_openfmb(h) and openfmb_bus.origin_of(h) == 'platform.device_adapter'
    assert openfmb_bus.proto_of(h) == 'essmodule.ESSControlProfile' and h[openfmb_bus.HEADER_REMOTE] == "('mqtt', 'site')"
    assert not openfmb_bus.is_openfmb({}) and not openfmb_bus.is_openfmb(None) and openfmb_bus.origin_of(None) is None
    assert openfmb_bus.topic_of(['openfmb', 'essmodule', 'ESSReadingProfile', 'm1']) == 'openfmb/essmodule/ESSReadingProfile/m1'
    assert openfmb_bus.HEADER_PROTO not in openfmb_bus.headers(None, 'x')
