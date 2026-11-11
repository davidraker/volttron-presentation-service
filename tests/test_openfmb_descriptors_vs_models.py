"""The service's generated OpenFMB pydantic models against the descriptors icm-lib-resources ships: same message names,
same fields for the newest edition, and a decoded wire message validates as the model."""
import pytest

pytest.importorskip('google.protobuf')
from icm.resources.codecs import openfmb as codec  # noqa: E402

from interoperability.field_universe import models_provider, openfmb_fields  # noqa: E402
from icm.models.openfmb import PROFILES  # noqa: E402

READING = {'readingMessageInfo': {'messageInfo': {'identifiedObject': {'mRID': 'msg-1'},
                                                  'messageTimeStamp': {'seconds': 1700000000, 'nanoseconds': 5}}},
           'ess': {'conductingEquipment': {'mRID': 'dev-1', 'namedObject': {'name': 'ESS 1'}}},
           'essReading': {'readingMMXU': {'W': {'net': {'cVal': {'mag': 9800.0}}}, 'Hz': {'mag': 60.01}}}}


def test_decoded_wire_message_validates_as_the_generated_model():
    decoded = codec.decode('essmodule.ESSReadingProfile', codec.encode('essmodule.ESSReadingProfile', READING))
    PROFILES['ESSReadingProfile'].model_validate(decoded)       # 64 bit integers arrive as strings; the models accept both


def test_models_and_bindings_agree_on_the_message_names():
    for name in ('ESSReadingProfile', 'SolarStatusProfile', 'ESSControlProfile'):
        assert codec.message_class(PROFILES[name].PROTO).DESCRIPTOR.full_name == PROFILES[name].PROTO


def test_descriptor_universe_matches_the_generated_models_for_the_newest_edition():
    assert openfmb_fields(edition=codec.latest_edition()) == openfmb_fields()
    assert openfmb_fields('ESS', 'ReadingProfile', edition='2.1') < openfmb_fields('ESS', 'ReadingProfile')
    assert models_provider('openfmb.ess.reading-2.1') == openfmb_fields('ESS', 'ReadingProfile', edition='2.1')
    assert models_provider('openfmb.ess.capability-2.0') == set()          # no capability profile in 2.0
    assert models_provider('openfmb-1.0')
