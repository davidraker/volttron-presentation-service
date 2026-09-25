"""Library of functions usable inside transform expressions, e.g. ``transform[x](multiple(7), add(9))``.

Each public function is called at parse time with the literal arguments written in the expression
(integers, or bare/quoted words as strings) and returns a convtools conversion that is applied to
the value found at the expression's source path.
"""
import contextvars

from convtools import conversion as c


class _Missing:
    """Sentinel for a source field that is absent from the input message."""
    __slots__ = ()

    def __repr__(self):
        return '<MISSING>'


MISSING = _Missing()

# Label under which the transform parser stores the element enclosing the expression currently being
# parsed: the message root at top level, or the current element inside a repeated ("name[#]") group.
# The parser sets it while parsing each expression, so library functions may capture scope() at build time.
scope_label = contextvars.ContextVar('scope_label', default='each0')


def scope():
    """Conversion yielding the element that encloses the expression being built (see ``scope_label``)."""
    return c.label(scope_label.get())


def _resolve_path(value, path: str):
    """Follow a dotted path through dicts and lists; digits index lists. Returns None if absent."""
    for segment in path.split('.'):
        try:
            if isinstance(value, (list, tuple)):
                value = value[int(segment)]
            else:
                value = value[segment]
        except (KeyError, IndexError, TypeError, ValueError):
            return None
    return value


def multiple(multiplier: float | int):
    """Builds a conversion and its inverse."""
    conv = c.this * multiplier
    conv.inverse = c.this / multiplier
    return conv

def add(addend: float | int):
    """Builds a conversion and its inverse."""
    conv = (c.this + addend)
    conv.inverse = c.this - addend
    return conv

def scale_decimal_int_signed(multiplier):
    """
        Scale float value that is stored as a decimal number, not using standard signing rollover,
         as the PM800 Power Factor Registers.
    """
    conv = c.if_(c.this < 0, multiplier * (0 - (c.this +32768)), multiplier * c.this)
    conv.inverse = c.if_(c.this < 0, (0 - (c.this / float(multiplier))) - 0xFFFF, (c.this / float(multiplier)))
    return conv

def _numeric(arg):
    """Accept a number written as an int, float or string (the modbus_tk register maps pass strings)."""
    if isinstance(arg, (int, float)) and not isinstance(arg, bool):
        return arg
    try:
        return int(str(arg), 10)
    except ValueError:
        return float(arg)


def _decimal_places(*values) -> int:
    """Total number of decimal digits written in the given factors (integers contribute none)."""
    digits = 0
    for value in values:
        if isinstance(value, float):
            text = repr(value)
            if '.' in text and 'e' not in text:
                digits += len(text.split('.')[1])
    return digits


def _fix_decimals(product, *factors):
    """Round a product to the decimal places of its factors, as modbus_tk's ``transform_func_helper`` does,
    so 0.001 * 12345 gives 12.345 rather than 12.345000000000001."""
    try:
        return round(product, _decimal_places(*factors))
    except TypeError:
        return product


def scale(multiplier: float | int | str):
    """
        Scale a register value by a constant multiplier, fixing floating point noise to the decimal
         places of the operands (modbus_tk ``scale``). The inverse divides; division by zero gives None
         and a non-numeric value is passed through.
    """
    multiplier = _numeric(multiplier)
    conv = c.call_func(_fix_decimals, c.this * multiplier, c.this, multiplier)
    conv.inverse = (c.try_(c.this / float(multiplier))
                    .except_(ZeroDivisionError, None)
                    .except_(TypeError, c.this))
    return conv


def scale_int(multiplier):
    multiplier = _numeric(multiplier)
    conv = (c.this * multiplier).as_type(int)
    conv.inverse = c.try_((c.this / c.naive(multiplier).as_type(float)).as_type(int)).except_(ZeroDivisionError, None)
    return conv


def _register(path: str):
    """Conversion reading a scaling register by quoted dotted path from the element enclosing the expression."""
    return c.call_func(_resolve_path, scope(), path)


def scale_reg(register: str):
    """
        Divide the value by another register's value, named by a quoted dotted path resolved against the
         element enclosing the expression (modbus_tk ``scale_reg``), e.g. ``scale_reg('701.W_SF')``. The
         value is treated as missing when the scaling register is absent; division by zero gives None.
         The inverse multiplies by the register.
    """
    reg = _register(register)
    conv = c.if_(reg.is_(None), c.naive(MISSING), c.try_(c.this / reg).except_(ZeroDivisionError, None))
    conv.inverse = c.if_(reg.is_(None), c.naive(MISSING), c.this * reg)
    return conv


def scale_reg_pow_10(register: str):
    """
        Multiply the value by 10 to the power of another register's value (modbus_tk ``scale_reg_pow_10``),
         which is how SunSpec scale factor registers work: ``scale_reg_pow_10('701.W_SF')`` with W_SF = -1
         scales by 0.1. The register is a quoted dotted path resolved against the element enclosing the
         expression; the value is treated as missing when it is absent. The inverse divides.
    """
    reg = _register(register)
    factor = c.naive(10.0) ** reg
    conv = c.if_(reg.is_(None), c.naive(MISSING), c.call_func(_fix_decimals, c.this * factor, c.this, factor))
    conv.inverse = c.if_(reg.is_(None), c.naive(MISSING), c.this / factor)
    return conv


def no_op():
    """Copy the value unchanged (modbus_tk ``no_op``); its own inverse."""
    conv = c.this.pipe(c.this)
    conv.inverse = c.this.pipe(c.this)
    return conv


def _word(index: int):
    """The ``index``-th 16 bit register of an unsigned integer packed from several registers (0 is the lowest)."""
    return (c.this // (0x10000 ** index)) % 0x10000


def _decimal_group(index: int):
    """The ``index``-th group of four decimal digits of an integer (0 is the lowest)."""
    return (c.this // (10000 ** index)) % 10000


def _mod10k(order: list[int]):
    """Build a MOD10K conversion: each 16 bit register holds four decimal digits (0 to 9999).

    ``order`` lists the register indexes (0 is the lowest 16 bits of the packed integer) from the most
    significant group of digits to the least. Only valid for non-negative values, as in the modbus_tk
    driver; the inverse packs the digit groups back into registers.
    """
    conv = sum((_word(w) * 10000 ** (len(order) - 1 - i) for i, w in enumerate(order)), c.naive(0))
    conv.inverse = sum((_decimal_group(len(order) - 1 - i) * 0x10000 ** w for i, w in enumerate(order)), c.naive(0))
    return conv


def _flag(arg) -> bool:
    return arg if isinstance(arg, bool) else _convert_to_boolean(arg)


def mod10k(reverse=False):
    """
        Decode the ION INT32-M10K format: two registers, each holding four decimal digits, high register
         first (``mod10k(True)`` for meters that store them reversed). Positive values only.
    """
    return _mod10k([0, 1] if _flag(reverse) else [1, 0])


def mod10k64(reverse=False):
    """Decode the PM800 64 bit M10K format: four registers of four decimal digits, lowest register first."""
    return _mod10k([3, 2, 1, 0] if _flag(reverse) else [0, 1, 2, 3])


def mod10k48(reverse=False):
    """Decode the PM800 INT48-M10K format: three of the four registers of a 64 bit word, as modbus_tk does
    (the second lowest register first; reversed, the lowest register first)."""
    return _mod10k([0, 1, 2] if _flag(reverse) else [1, 2, 3])

def _convert_to_boolean(v):
    v = v.decode('utf8') if isinstance(v, bytes) else v
    v = v.strip().lower() if isinstance(v, str) else v
    match v:
        case True:
            return True
        case False:
            return False
        case x if x in ('t', 'y', 'true', 'yes', '1', 1):
            return True
        case x if x in ('f', 'n', 'false', 'no', '0', 0, ''):
            return False
        case _:
            raise ValueError(f'Unable to convert {v} to Boolean.')

def cast_value(type_name):
    return c.this.dispatch(
        type_name,
        {
            'bool': c.call_func(_convert_to_boolean, c.this),
            'str': c.this.as_type(str),
            'int': c.this.as_type(int),
            'float': c.this.as_type(float),
            'list': c.this.as_type(list),
            'tuple': c.this.as_type(tuple),
            'dict': c.this.as_type(dict)
        }
    )


def mean(*paths):
    """
        Average of several fields of the current value. Each argument is a path to a field, with nested
         keys separated by dots (e.g., "phsA.mag"). Fields that are missing or None are ignored;
         the result is None if no fields have a value.
    """
    fields = [c.item(*path.split('.'), default=None) for path in paths]
    return c(fields).pipe(c.aggregate(c.ReduceFuncs.Average(c.this, where=c.this.is_not(None))))


def _take(sequence, count):
    if count is None or not isinstance(sequence, (list, tuple)):
        return sequence
    return list(sequence)[:int(count)]


def take(count: int | str):
    """
        Keep only the first ``count`` elements of a list. ``count`` is either a number or a quoted dotted
         path to the field holding the number, resolved against the element enclosing the expression
         (the message root at top level), e.g. ``take('705.Crv.0.ActPt')`` for SunSpec active points.
         If the referenced field is absent the list is passed through unchanged.
    """
    if isinstance(count, str):
        n = c.call_func(_resolve_path, scope(), count)
    else:
        n = c.naive(count)
    return c.call_func(_take, c.this, n)


def _pairs(sequence, start, count, x, y):
    points = []
    for i in range(count):
        xv = _resolve_path(sequence, str(start + 2 * i))
        yv = _resolve_path(sequence, str(start + 2 * i + 1))
        if xv is None and yv is None:
            continue
        points.append({x: MISSING if xv is None else xv, y: MISSING if yv is None else yv})
    return points


def pairs(start: int, count: int, x: str = 'x', y: str = 'y'):
    """
        Turn a flat, position-indexed array of alternating X and Y values (e.g., the IEEE 1815.2 curve
         point analog outputs, X1 Y1 X2 Y2 ...) into a list of ``{x: ..., y: ...}`` points. ``start`` is
         the index of the first X value and ``count`` the maximum number of points. Points with neither
         value present are skipped. Combine with ``take`` to honour a "number of points" field.
    """
    return c.call_func(_pairs, c.this, start, count, x, y)


def _count(value):
    return len(value) if isinstance(value, (list, tuple, dict)) else MISSING


def count():
    """Number of elements in a list (or keys in a group), e.g. SunSpec ``ActPt`` from 2030.5 ``CurveData``."""
    return c.call_func(_count, c.this)


def as_list():
    """Wrap a single value in a one-element list, e.g. to emit one curve into a SunSpec ``Crv`` array."""
    return c.call_func(lambda value: [value], c.this)


def const(value):
    """Replace the value with a literal, e.g. ``transform[DERCurve, opModVoltVar](const(2))`` emits 2 only when
    the source is present."""
    return c.naive(value)


def _when(value, actual, expected):
    return value if actual is not None and actual == expected else MISSING


def when(path: str, expected):
    """
        Pass the value through only when the field at ``path`` (a quoted dotted path resolved against the
         element enclosing the expression) equals ``expected``; otherwise the field is treated as missing.
    """
    return c.call_func(_when, c.this, c.call_func(_resolve_path, scope(), path), expected)


def when_equal(path_a: str, path_b: str):
    """
        Pass the value through only when the two fields named by the quoted dotted paths (resolved against
         the element enclosing the expression) are present and equal. Used to accept an IEEE 1815.2 curve
         window only when its selector matches a mode's curve index, e.g. ``when_equal('AI.328', 'AI.297')``.
    """
    return c.call_func(_when, c.this, c.call_func(_resolve_path, scope(), path_a),
                       c.call_func(_resolve_path, scope(), path_b))


def _unpairs(points, start, x, y):
    if not isinstance(points, (list, tuple)):
        return MISSING
    flat = {}
    for i, point in enumerate(points):
        if not isinstance(point, dict):
            continue
        flat[str(start + 2 * i)] = point.get(x, MISSING)
        flat[str(start + 2 * i + 1)] = point.get(y, MISSING)
    return flat


def unpairs(start: int, x: str = 'x', y: str = 'y'):
    """
        Inverse of ``pairs``: lay a list of ``{x: ..., y: ...}`` points out as a flat, position-indexed
         group of alternating X and Y values starting at index ``start`` (keys are strings). Meant for a
         spread entry (``"*points": "transform[...](unpairs(249, xvalue, yvalue))"``) so the values merge
         into the enclosing point group.
    """
    return c.call_func(_unpairs, c.this, start, x, y)
