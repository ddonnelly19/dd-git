def mandatory(value):
    return value is not None


def notEmpty(value):
    return bool(value)


def isValidWWN(value):
    return value != '000000000000'