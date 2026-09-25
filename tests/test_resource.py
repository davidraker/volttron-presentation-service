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
    agent.vip.rpc.call.assert_called_once_with('platform.presentation', 'resolve', ['site', 'pv'])
    assert resource.transform.execute({'701': {'W': 5}}) == {'W': 5}


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
