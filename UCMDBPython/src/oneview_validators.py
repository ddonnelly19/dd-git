def mandatory(value):
    return value is not None


def notEmpty(value):
    return bool(value)


def excludeIPDUCore(value):
    return value != 'HPIpduCore'