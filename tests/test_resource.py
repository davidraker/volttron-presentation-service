"""Tests for ResourceData, the client-side helper that resolves a topic through the presentation service."""
import logging
from unittest import mock

import pytest

pytest.importorskip('volttron')
from volttron.utils.jsonrpc import RemoteError  # noqa: E402

from interoperability.resource import ResourceData  # noqa: E402


def _agent(resolve):
    """A fake agent whose resolve RPC returns ``resolve`` or raises it."""
    agent = mock.MagicMock()
    result = agent.vip.rpc.call.return_value
    if isinstance(resolve, Exception):
        result.get.side_effect = resolve
    else:
        result.get.return_value = resolve
    return agent


def _not_found_error():
    # What the RPC subsystem builds when the presentation service raises TransformNotFoundError.
    return RemoteError('No transform from "sunspec" to "61850": format "61850" has no registered transforms.',
                       exc_type="<class 'interoperability.transform_registry.TransformNotFoundError'>",
                       exc_args=['sunspec', '61850', 'format "61850" has no registered transforms'])


def test_lookup_builds_resource_with_transform_chain():
    agent = _agent({'data_format': 'sunspec', 'target_format': 'x', 'publication_topic': 'devices/pv',
                    'transform': [{'W': 'transform[701, W]()'}]})
    resource = ResourceData.lookup(agent, 'site/pv')
    agent.vip.rpc.call.assert_called_once_with('platform.presentation', 'resolve', ['site', 'pv'], strict=False)
    assert resource.transform.execute({'701': {'W': 5}}) == {'W': 5}


def test_lookup_strict_asks_the_service_for_the_exact_uai():
    # Inbound bus messages use this: a topic names its resource exactly, with no longest-prefix fallback.
    agent = _agent({'data_format': 'sunspec', 'publication_topic': 'devices/pv', 'transform': []})
    assert ResourceData.lookup(agent, 'a.b.c', delimiter='.', strict=True) is not None
    agent.vip.rpc.call.assert_called_once_with('platform.presentation', 'resolve', ['a', 'b', 'c'], strict=True)
    agent = _agent({})
    assert ResourceData.lookup(agent, ('a', 'b', 'unknown'), strict=True) is None


def test_lookup_without_transform_passes_messages_through():
    # No target format (empty chain, or no 'transform' key at all) means the resource is already in the wanted format.
    for definition in ({'data_format': 'sunspec', 'transform': []}, {'data_format': 'sunspec'}):
        resource = ResourceData.lookup(_agent(definition), ('site', 'pv'))
        assert resource.transform.execute({'701': {'W': 5}}) == {'701': {'W': 5}}


def test_lookup_returns_none_for_unknown_resource():
    assert ResourceData.lookup(_agent({}), 'site/pv') is None


def test_lookup_treats_missing_transform_as_unresolvable(caplog):
    with caplog.at_level(logging.WARNING, logger='interoperability.resource'):
        assert ResourceData.lookup(_agent(_not_found_error()), 'site/pv') is None
    assert 'site/pv cannot be provided in the requested format' in caplog.text
    assert 'format "61850" has no registered transforms' in caplog.text


def test_lookup_reraises_other_remote_errors():
    other = RemoteError('boom', exc_type="<class 'KeyError'>", exc_args=['x'])
    with pytest.raises(RemoteError):
        ResourceData.lookup(_agent(other), 'site/pv')


def test_lookup_binds_parameters_and_codec():
    pytest.importorskip('google.protobuf')
    from interoperability.codecs import openfmb as codec
    definition = {'data_format': 'openfmb.ess', 'target_format': 'openfmb.ess.reading', 'publication_topic': 'devices/ess',
                  'parameters': {'mrid': 'dev-1'}, 'encoding': 'protobuf',
                  'codec': {'encoding': 'protobuf', 'proto': 'essmodule.ESSReadingProfile'},
                  'transform': [{'ess': {'conductingEquipment': {'mRID': "param('mrid')"}}, 'essReading': 'transform[essReading]()'}]}
    resource = ResourceData.lookup(_agent(definition), 'openfmb/essmodule/ESSReadingProfile/dev-1')
    result = resource.transform.execute({'essReading': {'readingMMXU': {'Hz': {'mag': 60.0}}}})
    assert result['ess'] == {'conductingEquipment': {'mRID': 'dev-1'}}
    wire = resource.encode(result)
    assert isinstance(wire, bytes)
    assert codec.decode('essmodule.ESSReadingProfile', wire)['ess'] == {'conductingEquipment': {'mRID': 'dev-1'}}
    assert resource.decode(wire)['essReading'] == {'readingMMXU': {'Hz': {'mag': 60.0}}}
    assert resource.decode({'parsed': 'json'}) == {'parsed': 'json'}


def test_subscribe_relays_encoded_payloads():
    pytest.importorskip('google.protobuf')
    agent = _agent({'data_format': 'openfmb.ess', 'target_format': 'openfmb.ess.reading', 'publication_topic': 'devices/ess',
                    'codec': {'encoding': 'protobuf', 'proto': 'essmodule.ESSReadingProfile'}, 'transform': []})
    resource = ResourceData.lookup(agent, 'remote/topic')
    received = []
    resource.subscribe(lambda *args: received.append(args))
    handler = agent.vip.pubsub.subscribe.call_args.kwargs['callback']
    assert agent.vip.pubsub.subscribe.call_args.kwargs['prefix'] == 'devices/ess'
    handler('pubsub', 'platform.driver', 'bus', 'devices/ess/all', {}, {'essReading': {'readingMMXU': {'Hz': {'mag': 60.0}}}})
    (peer, sender, bus, topic, headers, payload), = received
    assert topic == 'remote/topic' and isinstance(payload, bytes)


def test_subscribe_covers_the_device_polls_and_pushes():
    from unittest import mock
    from interoperability.resource import ResourceData
    agent = mock.MagicMock()
    data = ResourceData(agent, 'openfmb/x', {'data_format': 'f', 'publication_topic': 'devices/site1/pv/all'})
    assert data.publication_topics() == ['devices/site1/pv/all', 'devices/site1/pv/multi']
    data.subscribe(lambda *a: None)
    assert [c.kwargs['prefix'] for c in agent.vip.pubsub.subscribe.call_args_list] == ['devices/site1/pv/all', 'devices/site1/pv/multi']
    assert ResourceData(agent, 't', {'data_format': 'f', 'publication_topic': 'devices/pv'}).publication_topics() == ['devices/pv']


# ---- ResourceWriter -------------------------------------------------------------------------------------------------
from interoperability.resource import ResourceWriter, publication_topics  # noqa: E402


def _writer(**kwargs):
    agent = mock.MagicMock()
    clock = {'now': 1000.0}
    writer = ResourceWriter(agent, 'devices/site1/mirror', 'devices/site1/mirror/all', clock=lambda: clock['now'], **kwargs)
    return agent, writer, clock


def test_writer_writes_what_the_device_is_not_known_to_hold():
    agent, writer, clock = _writer()
    assert writer.select({'A': 1, 'B': 2}) == {'A': 1, 'B': 2}                 # nothing known: write everything
    writer.record({'A': 1, 'B': 2})
    assert writer.select({'A': 1, 'B': 2}) == {}                               # provisionally held: nothing to do
    assert writer.select({'A': 1, 'B': 3, 'sequence': [{'C': 1}]}) == {'B': 3, 'sequence': [{'C': 1}]}
    assert writer.select({'A': 1}, force=True) == {'A': 1}
    agent.vip.rpc.call.assert_not_called()                                      # stale_after unset: the driver is never asked


def test_writer_follows_the_device_and_reports_drift():
    agent, writer, clock = _writer()
    assert writer.subscribe() == ['devices/site1/mirror/all', 'devices/site1/mirror/multi'] == publication_topics('devices/site1/mirror/all')
    handler = agent.vip.pubsub.subscribe.call_args.kwargs['callback']
    writer.record({'A': 1})
    handler('pubsub', 'platform.driver', 'bus', 'devices/site1/mirror/multi', {}, [{'A': 7}, {}])   # someone else wrote A
    assert writer.drifted() == {'A': (1, 7)}
    assert writer.select({'A': 1}) == {'A': 1}                                 # the intended value is a change again
    writer.record({'A': 1})
    assert writer.drifted() == {}
    writer.unsubscribe()
    assert agent.vip.pubsub.unsubscribe.call_count == 2 and writer.subscribe() == ['devices/site1/mirror/all', 'devices/site1/mirror/multi']


def test_writer_refreshes_unknown_and_stale_points_from_the_driver():
    agent, writer, clock = _writer(stale_after=10, rpc_timeout=3)
    agent.vip.rpc.call.return_value.get.return_value = {
        'devices/site1/mirror/A': {'value': 1, 'updated': '2026-10-26T12:00:00+00:00'},
        'devices/site1/mirror/B': {'value': None, 'updated': None}}
    assert writer.select({'A': 1, 'B': 2}) == {'B': 2}                         # A known from the driver, B never seen
    agent.vip.rpc.call.assert_called_once_with('platform.driver', 'last', ['devices/site1/mirror/A', 'devices/site1/mirror/B'])
    agent.vip.rpc.call.return_value.get.assert_called_with(timeout=3)
    writer.record({'B': 2})
    clock['now'] += 5
    assert writer.select({'B': 2}) == {} and agent.vip.rpc.call.call_count == 1   # fresh enough: no second ask
    clock['now'] += 10
    agent.vip.rpc.call.return_value.get.return_value = {'devices/site1/mirror/B': {'value': 9, 'updated': None}}
    assert writer.select({'B': 2}) == {'B': 2} and agent.vip.rpc.call.call_count == 2   # stale, refreshed, differs


def test_writer_survives_a_failed_refresh():
    agent, writer, clock = _writer(stale_after=0)
    agent.vip.rpc.call.return_value.get.side_effect = RuntimeError('driver down')
    assert writer.select({'A': 1}) == {'A': 1}
    writer.record({'A': 1})
    clock['now'] += 1
    assert writer.select({'A': 1}) == {}                                       # knowledge kept when the driver cannot answer
