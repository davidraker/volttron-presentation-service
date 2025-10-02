import logging

from importlib.metadata import distribution, PackageNotFoundError

try:
    distribution('volttron-core')
    from volttron.client.logs import setup_logging
    from volttron.client.vip.agent import Agent, RPC
except PackageNotFoundError:
    from volttron.platform.agent.utils import setup_logging
    from volttron.platform.vip.agent import Agent, RPC

from .uai_tree import deserialize_uai, UAINode, UAITree, UAR

setup_logging()
_log = logging.getLogger(__name__)


class MapEngineAgent(Agent):
    def __init__(self, **kwargs):
        super(MapEngineAgent, self).__init__(**kwargs)
        self.mapping_tree = UAITree()
        self.vip.pubsub.subscribe('pubsub', 'mapper/update', self.ingest_mappings)

    def ingest_mappings(self, _, __, ___, ____, _____, message):
        if not isinstance(message, list) or not all(isinstance(m, dict) for m in message):
            _log.warning(f'Ingest mappings expects a list of dictionaries. '
                         f'Received improperly formatted message: {message}')
        for mapping in message:
            uai = mapping['uai']
            if isinstance(uai, str):
                uai = deserialize_uai(uai)
            if not isinstance(uai, (list, tuple)):
                _log.warning(f'Ingest mappings received UAI that was not a tuple or list: {uai} of type {type(uai)}')
            self.mapping_tree.add_resource(uai, UAR(**mapping['resource']))

    @RPC.export
    def resolve(self, uai: tuple, strict=False):
        if strict:
            return self.mapping_tree.get_node_by_uai(uai)
        else:
            while ((node := self.mapping_tree.get_node_by_uai(uai)) is None) and not len(uai) < 2:
                uai = uai[:-1]
            return node.uar.model_dump() if node is not None and node.is_uar() else None
