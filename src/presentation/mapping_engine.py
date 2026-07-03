import json
import logging

from treelib import Tree, Node
from treelib.exceptions import DuplicatedNodeIdError
from typing import cast

from .resource import AliasedResource, CanonicalResource, Resource

_log = logging.getLogger(__name__)


def serialize_uai(uai, root_name):
    if isinstance(uai, str):
        uai = (uai,)
    if isinstance(uai, list):
        uai = tuple(uai)
    elif not isinstance(uai, tuple):
        raise ValueError(f'UAI passed to serialize_uai must be a tuple, list, or a string. Received type({type(uai)}: {uai}')
    if root_name is not None and uai[0] != root_name:
        uai = (root_name,) + uai
    ret_val = ','.join(json.dumps(u) for u in uai)
    return ret_val


def deserialize_uai(identifier, remove_prefix=False):
    uai = tuple(json.loads(identifier))
    return uai[:-1] if remove_prefix else uai


class UAINode(Node):
    """A Node representing a Uniquely Addressable Identifier."""
    def __init__(self, identifier: tuple, data=dict|None, root_name='uai', segment_type='UAI_SEGMENT', *args, **kwargs):
        identifier_string = serialize_uai(identifier, root_name) # if identifier != (root_name,) else serialize_uai(identifier, None)
        kwargs.pop('tag', None)
        super(UAINode, self).__init__(identifier=identifier_string, tag=identifier[-1], *args, **kwargs)
        self.data: dict = data if isinstance(data, dict) else {}
        self.data['segment_type'] = segment_type
        self.root_name = root_name

    @property
    def segment_type(self):
        return self.data['segment_type']

    @property
    def is_segment(self):
        return True if self.segment_type == 'UAI_SEGMENT' else False

    @property
    def is_resource(self):
        return True if self.segment_type == 'RESOURCE' else False

    @property
    def is_alias(self) -> bool:
        return isinstance(self, AliasedResourceNode)

    @property
    def is_canonical(self) -> bool:
        return isinstance(self, CanonicalResourceNode)

    @property
    def uai(self):
        return deserialize_uai(self.identifier, remove_prefix=True)


class ResourceNode(UAINode):
    """A Node representing a Uniquely Addressed Resource."""
    def __init__(self, identifier: tuple, resource: Resource, segment_type='RESOURCE', *args, **kwargs):
        super(ResourceNode, self).__init__(segment_type=segment_type, identifier=identifier, *args, **kwargs)
        self.data['resource'] =  resource

    @property
    def resource(self) -> Resource:
        return self.data['resource']

    @property
    def data_format(self):
        return self.data['resource'].data_format

    @data_format.setter
    def data_format(self, value):
        self.data['resource'].data_format = value

    @property
    def owner(self):
        return self.data['resource'].owner
    
    @owner.setter
    def owner(self, value):
        self.data['resource'].owner = value


class AliasedResourceNode(ResourceNode):
    def __init__(self, identifier: tuple, resource: AliasedResource, *args, **kwargs):
        super(AliasedResourceNode, self).__init__(identifier=identifier, resource=resource, *args, **kwargs)

    @property
    def references(self) -> tuple:
        return self.data['resource'].references

    @references.setter
    def references(self, value: tuple):
        self.data['resource'].references = value


class CanonicalResourceNode(ResourceNode):
    def __init__(self, identifier: tuple, resource: CanonicalResource, *args, **kwargs):
        super(CanonicalResourceNode, self).__init__(identifier=identifier, resource=resource, *args, **kwargs)

    @property
    def publication_topic(self):
        return self.data['resource'].publication_topic

    @publication_topic.setter
    def publication_topic(self, value):
        self.data['resource'].publication_topic = value

    @property
    def rpc_topic(self):
        return self.data['resource'].rpc_topic

    @rpc_topic.setter
    def rpc_topic(self, value):
        self.data['resource'].rpc_topic = value


class UAITree(Tree):
    default_root_name = 'uai'

    def __init__(self, uai_list=None, node_class=UAINode, root_name=None, *args, **kwargs):
        node_class = node_class if node_class else UAINode
        self.root_name = root_name if root_name else self.default_root_name
        super(UAITree, self).__init__(node_class=node_class, *args, **kwargs)
        if uai_list:
            self.build_branches_from_uai_list(uai_list)
        else:
            self.create_node(identifier=(self.root_name,)).data['segment_type'] = 'UAI_ROOT'

    def build_branches_from_uai_list(self, uai_list: list[tuple[str]]):
        unrooted_uai_list = [uai[1:] if uai[0] == 'uai' else uai for uai in uai_list]
        if not self.get_node(serialize_uai(self.root_name, None)):
            self.create_node(self.root_name, self.root_name).data['segment_type'] = 'UAI_ROOT'
        for uai in unrooted_uai_list:
            parent = (self.root_name,)
            for segment in uai:
                nid = parent + (segment,)
                try:
                    self.create_node(nid, nid, parent=serialize_uai(parent, None))
                except DuplicatedNodeIdError:
                    pass
                parent = nid

    def add_resource(self, uai: tuple, resource: Resource, *args, **kwargs):
        parent_uai = uai[:-1]
        self.build_branches_from_uai_list([parent_uai])
        if isinstance(resource, AliasedResource):
            resource_node = AliasedResourceNode(identifier=uai, resource=resource, *args, **kwargs)
        elif isinstance(resource, CanonicalResource):
            resource_node = CanonicalResourceNode(identifier=uai, resource=resource, *args, **kwargs)
        else:
            resource_node = ResourceNode(uai, resource, *args, **kwargs)
        try:
            self.add_node(resource_node, serialize_uai(parent_uai, self.root_name))
        except DuplicatedNodeIdError:
            existing = self.get_node(serialize_uai(uai, self.root_name))
            _log.warning(f'Attempted to add already existing resource node -- existing: {existing.data["resource"]}, new: {resource}')

    def get_node_by_uai(self,uai: tuple):
        return cast(UAINode, self.get_node(serialize_uai(uai, self.root_name)))

    def ingest_mappings(self, mappings: dict):
        for mapping in mappings:
            uai = mapping['uai']
            if isinstance(uai, str):
                uai = deserialize_uai(uai)
            if not isinstance(uai, (list, tuple)):
                _log.warning(f'Ingest mappings received UAI that was not a tuple or list: {uai} of type {type(uai)}')
            self.add_resource(uai, Resource.create(mapping))
        _log.debug(f'@@@@@@@@@@ CREATED TREE WITH: {self.all_nodes()}')

    def resolve(self, uai: tuple, as_format: str | None = None, strict: bool = False
                 ) -> tuple[UAINode | None, str| None]:
        if strict:
            node: UAINode | None = self.get_node_by_uai(uai)
        else:
            while ((node := self.get_node_by_uai(uai)) is None) and not len(uai) < 2:
                uai = uai[:-1]
        if isinstance(node, UAINode) and node.is_alias:
            aliased_node = cast(AliasedResourceNode, node)
            # If a specific format was specified, it is returned. Otherwise, it is the outermost alias format, if any.
            as_format = as_format if as_format else aliased_node.data_format
            node, _ = self.resolve(aliased_node.references, as_format)
        return node, as_format

    def update_resource(self, uai: tuple, resource: Resource):
            existing_node: UAINode = cast(UAINode, self.get_node(serialize_uai(uai, self.root_name)))
            existing_node.data['resource'] = existing_node.data['resource'].model_copy(update=resource.model_dump())
