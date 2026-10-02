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
