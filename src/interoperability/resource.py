import logging

from pydantic import BaseModel, ConfigDict
from typing import Callable

from .transform_parser import TransformParser

_log = logging.getLogger(__name__)

class Resource(BaseModel):
    model_config = ConfigDict(validate_assignment=True, populate_by_name=True)
    data_format: str
    owner: str

    @classmethod
    def create(cls, resource_config):
        try:
            match resource_config['resource_type'].lower():
                case 'canon' | 'canonical':
                    return CanonicalResource(**resource_config['resource'])
                case 'alias' | 'aliased':
                    return AliasedResource(**resource_config['resource'])
                case _:
                    raise TypeError(f"Resource type {resource_config['resource_type']} is not supported")
        except KeyError:
            raise TypeError(f"Malformed resource definition {resource_config['resource']}.")

class CanonicalResource(Resource):
    model_config = ConfigDict(validate_assignment=True, populate_by_name=True)
    publication_topic: str | None = None
    rpc_topic: str | None = None


class AliasedResource(Resource):
    model_config = ConfigDict(validate_assignment=True, populate_by_name=True)
    references: tuple

class ResourceData:
    def __init__(self, agent, local_topic, resource_def):
        self.agent = agent
        self.local_topic = local_topic
        self.resource_def = resource_def
        self.transform = TransformParser().build_transform_from_schema(self.resource_def['transform'])
        # TODO: One step further, make actual Resource (or include all this in Resource?).
        #   This version, however, does not contain all the fields of canonical nor aliased resources.
        # self.resource = Resource(**resource_def)

    def subscribe(self, callback: Callable):
        def handle_incoming(peer, sender, bus, topic, headers, message):
            _log.debug(f'@@@@@ CANONICAL MESSAGE ({topic}): {message}')
            transformed_payload = self.transform.execute(message)
            callback(peer, sender, bus, self.local_topic, headers, transformed_payload)

        return self.agent.vip.pubsub.subscribe(peer='pubsub', prefix=self.resource_def['publication_topic'],
                                               callback=handle_incoming).get()

    @classmethod
    def lookup(cls, agent, local_topic: tuple | list | str, delimiter='/'):
        # Find the resource to subscribe:
        if isinstance(local_topic, list):
            uai = tuple(local_topic)
        elif isinstance(local_topic, str):
            uai = local_topic.split(delimiter)
        elif not isinstance(local_topic, tuple):
            _log.warning(f'Invalid topic received: {local_topic}')
            return None
        else:
            uai = local_topic
        resource_def = agent.vip.rpc.call('platform.presentation', 'resolve', uai).get()
        _log.debug(f'@@@@@@@@ RESOURCE DEF: {resource_def}')
        return cls(agent, local_topic, resource_def) if resource_def else None
