def abstract_method(func):
    def wrapper(*args, **kwargs):
        raise NotImplementedError(func.__name__)

    return wrapper


def mandatory_attribute(func):
    def get_and_validate(*args, **kwargs):
        value = func(*args, **kwargs)
        if not value:
            raise ValueError('mandatory attribute missed %s' % func.__name__)
        return value

    return get_and_validate