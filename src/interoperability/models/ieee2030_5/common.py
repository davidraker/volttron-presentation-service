"""Shared base class for the generated IEEE 2030.5 (Smart Energy Profile 2.0) models."""
from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

#: XML namespace of the IEEE 2030.5 schema.
NAMESPACE = 'urn:ieee:std:2030.5:ns'


class SepBase(BaseModel):
    """Base for every IEEE 2030.5 resource and type.

    Fields keep the schema's element and attribute names. Each field records in
    ``json_schema_extra`` whether it is an XML ``element`` or ``attribute`` (``xml`` key),
    whether the schema marks it ``required``, and for hex-binary values ``format: base16``.
    Every field is optional here so partially populated payloads can be represented; use
    :meth:`missing_required` to check a message against the schema's requirements.
    """

    model_config = ConfigDict(protected_namespaces=(), validate_assignment=True, populate_by_name=True)

    #: Element name in the schema when it differs from the class name (e.g. ``List``).
    XML_NAME: ClassVar[str | None] = None

    @classmethod
    def xml_name(cls) -> str:
        return cls.XML_NAME or cls.__name__

    @classmethod
    def field_metadata(cls, name: str) -> dict[str, Any]:
        extra = cls.model_fields[name].json_schema_extra
        return dict(extra) if isinstance(extra, dict) else {}

    def missing_required(self) -> list[str]:
        """Names of fields the schema requires that are ``None`` on this instance."""
        return [
            name for name in type(self).model_fields
            if self.field_metadata(name).get('required') and getattr(self, name) is None
        ]
