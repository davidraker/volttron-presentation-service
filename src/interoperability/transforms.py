from convtools import conversion as c


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

def scale(multiplier):
    pass

def scale_int(multiplier):
    conv = (c.this * multiplier).as_type(int)
    conv.inverse = c.try_((c.this / c.naive(multiplier).as_type(float)).as_type(int)).except_(ZeroDivisionError, None)
    return conv

def scale_reg(register_name):
    pass

def scale_reg_pow_10(register_name):
    pass

def no_op():
    pass

def mod10k(reverse):
    pass

def mod10k64(reverse):
    pass

def mod10k48(reverse):
    pass

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
