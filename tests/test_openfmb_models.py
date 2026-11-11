"""The OpenFMB field universe the service scores chains against comes from the icm-lib-models-openfmb classes."""
from interoperability import field_universe

def test_openfmb_field_universe_comes_from_the_profiles():
    universe = field_universe.models_provider('openfmb')
    assert ('essReading', 'readingMMXU', 'W', 'net', 'cVal', 'mag') in universe
    assert ('essControl', 'essControlFSCC', 'essControlScheduleFSCH', 'ValDCSG', 'crvPts', '*', 'control',
            'voltVarOperation', 'crvPts', '*', 'voltVal') in universe
    assert ('essStatus', 'essStatusZBAT', 'Soc', 'mag') in universe
    assert not any(path[-1].endswith('_') for path in universe)       # wire names, not python attribute names
