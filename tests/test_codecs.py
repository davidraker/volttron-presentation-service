"""Tests for the wire codecs: protobuf encoding of OpenFMB profiles from the transform output shape."""
import pytest

from interoperability.codecs import decoder_for, encoder_for

pytest.importorskip('google.protobuf')
from interoperability.codecs import openfmb as codec  # noqa: E402

READING = {'readingMessageInfo': {'messageInfo': {'identifiedObject': {'mRID': 'msg-1'},
                                                  'messageTimeStamp': {'seconds': 1700000000, 'nanoseconds': 5}}},
           'ess': {'conductingEquipment': {'mRID': 'dev-1', 'namedObject': {'name': 'ESS 1'}}},
           'essReading': {'readingMMXU': {'W': {'net': {'cVal': {'mag': 9800.0}}}, 'Hz': {'mag': 60.01}}}}


def test_encode_and_decode_round_trip_the_transform_shape():
    data = codec.encode('essmodule.ESSReadingProfile', READING)
    assert isinstance(data, bytes) and 0 < len(data) < 200
    decoded = codec.decode('essmodule.ESSReadingProfile', data)
    assert decoded['essReading'] == READING['essReading'] and decoded['ess'] == READING['ess']
    # 64 bit integers come back as strings in protobuf's JSON mapping; the pydantic models accept both.
    assert decoded['readingMessageInfo']['messageInfo']['messageTimeStamp'] == {'seconds': '1700000000', 'nanoseconds': 5}
    from interoperability.models.openfmb import PROFILES
    PROFILES['ESSReadingProfile'].model_validate(decoded)


def test_models_and_bindings_agree_on_the_message_names():
    from interoperability.models.openfmb import PROFILES
    for name in ('ESSReadingProfile', 'SolarStatusProfile', 'ESSControlProfile'):
        assert codec.message_class(PROFILES[name].PROTO).DESCRIPTOR.full_name == PROFILES[name].PROTO


def test_unknown_fields_and_messages_are_errors():
    from google.protobuf.json_format import ParseError
    with pytest.raises(ParseError):
        codec.encode('essmodule.ESSReadingProfile', {'essReading': {'nope': 1}})
    with pytest.raises(LookupError):
        codec.message_class('essmodule.NoSuchProfile')
    with pytest.raises(LookupError):
        codec.message_class('nosuchmodule.X')


def test_codec_selection():
    assert encoder_for(None)({'a': 1}) == {'a': 1} and decoder_for({'encoding': 'json'})(b'x') == b'x'
    encode = encoder_for({'encoding': 'protobuf', 'proto': 'essmodule.ESSReadingProfile'})
    decode = decoder_for({'encoding': 'protobuf', 'proto': 'essmodule.ESSReadingProfile'})
    assert decode(encode(READING))['essReading'] == READING['essReading']
    assert decode({'already': 'a dict'}) == {'already': 'a dict'}        # JSON text arrives parsed; only bytes are decoded
    with pytest.raises(ValueError):
        encoder_for({'encoding': 'protobuf'})
    with pytest.raises(ValueError):
        encoder_for({'encoding': 'xml'})


# ---- editions -------------------------------------------------------------------------------------------------------
def test_every_edition_has_descriptors_and_its_own_pool():
    assert codec.editions() == ('1.0', '2.0', '2.1', '2.2') and codec.latest_edition() == '2.2'
    for edition in codec.editions():
        assert codec.message_class('commonmodule.MessageInfo', edition).DESCRIPTOR.full_name == 'commonmodule.MessageInfo'
    # The same message name resolves to a differently shaped class per edition, in one process.
    reading = {e: codec.message_class('essmodule.ESSReadingProfile', e).DESCRIPTOR.fields_by_name['essReading'].message_type
               for e in ('2.1', '2.2')}
    assert 'readingMMDC' in reading['2.2'].fields_by_name and 'readingMMDC' not in reading['2.1'].fields_by_name
    with pytest.raises(LookupError):
        codec.message_class('essmodule.ESSCapabilityProfile', '2.0')          # capability profiles arrived in 2.1
    with pytest.raises(LookupError):
        codec.message_class('essmodule.ESSReadingProfile', '9.9')


def test_editions_encode_and_decode_each_other_where_fields_are_shared():
    # (64-bit integers decode as strings, so the comparison is on the reading subtree.)
    old = codec.encode('essmodule.ESSReadingProfile', READING, edition='2.1')
    assert codec.decode('essmodule.ESSReadingProfile', old, edition='2.2')['essReading'] == READING['essReading']
    new = codec.encode('essmodule.ESSReadingProfile', READING)
    assert codec.decode('essmodule.ESSReadingProfile', new, edition='2.1')['essReading'] == READING['essReading']
    with pytest.raises(Exception):
        codec.encode('essmodule.ESSReadingProfile', {'essReading': {'readingMMDC': {}}}, edition='2.1')
    assert codec.encode('essmodule.ESSReadingProfile', {'essReading': {'readingMMDC': {}}}, edition='2.2')


def test_codec_block_edition_selects_the_pool():
    block = {'encoding': 'protobuf', 'proto': 'essmodule.ESSReadingProfile', 'edition': '2.1'}
    data = encoder_for(block)(READING)
    assert decoder_for(block)(data)['essReading'] == READING['essReading']
    with pytest.raises(Exception):
        encoder_for(block)({'essReading': {'readingMMDC': {}}})


def test_descriptor_universe_matches_the_generated_models_for_the_newest_edition():
    from interoperability.field_universe import models_provider, openfmb_fields
    assert openfmb_fields(edition=codec.latest_edition()) == openfmb_fields()
    assert openfmb_fields('ESS', 'ReadingProfile', edition='2.1') < openfmb_fields('ESS', 'ReadingProfile')
    assert models_provider('openfmb.ess.reading-2.1') == openfmb_fields('ESS', 'ReadingProfile', edition='2.1')
    assert models_provider('openfmb.ess.capability-2.0') == set()          # no capability profile in 2.0
    assert models_provider('openfmb-1.0')
