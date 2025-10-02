import json
import logging

from pydantic import BaseModel, ConfigDict
from treelib import Tree, Node
from treelib.exceptions import DuplicatedNodeIdError

_log = logging.getLogger(__name__)


def serialize_uai(uai, root_name):
    return ','.join(json.dumps(u) for u in (root_name,) + uai)


def deserialize_uai(identifier, remove_prefix=False):
    uai = tuple(json.loads(identifier))
    return uai[:-1] if remove_prefix else uai

class UAR(BaseModel):
    model_config = ConfigDict(validate_assignment=True, populate_by_name=True)
    data_format: str
    owner: str
    publication_topic: str | None = None
    rpc_topic: str | None = None


class UAINode(Node):
    """A Node representing a Uniquely Addressable Identifier."""
    def __init__(self, uai: tuple, data=None, root_name='uai', segment_type='UAI_SEGMENT', *args, **kwargs):
        identifier = serialize_uai(uai, root_name)
        super(UAINode, self).__init__(identifier=identifier, tag=uai[-1], *args, **kwargs)
        self.data = data if data else {}
        self.data['segment_type'] = segment_type
        self.root_name = root_name

    @property
    def segment_type(self):
        return self.data['segment_type']

    @property
    def is_segment(self):
        return True if self.segment_type == 'UAI_SEGMENT' else False

    @property
    def is_uar(self):
        return True if self.segment_type == 'UAR' else False

    @property
    def uai(self):
        return deserialize_uai(self.identifier, remove_prefix=True)


class UARNode(UAINode):
    """A Node representing a Uniquely Addressed Resource."""
    def __init__(self, uai: tuple, uar: UAR, segment_type='UAR', *args, **kwargs):
        super(UARNode, self).__init__(segment_type=segment_type, uai=uai, *args, **kwargs)
        self.data['uar'] =  uar

    @property
    def data_format(self):
        return self.data['uar'].data_format

    @data_format.setter
    def data_format(self, value):
        self.data['uar'].data_format = value

    @property
    def owner(self):
        return self.data['uar'].owner
    
    @owner.setter
    def owner(self, value):
        self.data['uar'].owner = value

    @property
    def publication_topic(self):
        return self.data['uar'].publication_topic

    @publication_topic.setter
    def publication_topic(self, value):
        self.data['uar'].publication_topic = value

    @property
    def rpc_topic(self):
        return self.data['uar'].rpc_topic

    @rpc_topic.setter
    def rpc_topic(self, value):
        self.data['uar'].rpc_topic = value


class UAITree(Tree):
    default_root_name = 'uai'

    def __init__(self, uai_list=None, node_class=UAINode, root_name=None, *args, **kwargs):
        node_class = node_class if node_class else UAINode
        self.root_name = root_name if root_name else self.default_root_name
        super(UAITree, self).__init__(node_class=node_class, *args, **kwargs)
        if uai_list:
            self._from_uai_list(uai_list)
        else:
            self.create_node(root_name, root_name).data['segment_type'] = 'UAI_ROOT'

    # TODO: This or another method should load a full set of UAI/UAR pairs.
    def _from_uai_list(self, uai_list):
        [uai.pop(0) for uai in uai_list if uai[0] == self.root_name]
        self.create_node(self.root_name, self.root_name).data['segment_type'] = 'UAI_ROOT'
        for uai in uai_list:
            parent = (self.root_name,)
            for segment in uai:
                nid = parent + (segment,)
                try:
                    self.create_node(nid, parent=parent)
                except DuplicatedNodeIdError:
                    pass
                parent = nid

    def add_resource(self, uai: tuple, uar: UAR, *args, **kwargs):
        parent_uai = uai[:-1]
        self._from_uai_list(parent_uai)
        uar_node = UARNode(uai, uar, *args, **kwargs)
        try:
            self.add_node(uar_node, serialize_uai(parent_uai, self.root_name))
        except DuplicatedNodeIdError:
            existing = self.get_node(serialize_uai(uai, self.root_name))
            _log.warning(f'Attempted to add already existing resource node -- existing: {existing.data['uar']}, new: {uar}')

    def update_resource(self, uai: tuple, uar: UAR):
            existing_uar_node = self.get_node(serialize_uai(uai, self.root_name))
            existing_uar_node.data['uar'] = existing_uar_node['uar'].model_copy(update=uar.model_dump())

    def get_node_by_uai(self,uai: tuple):
        return self.get_node(serialize_uai(uai, self.root_name))
