# __author__ = 'gengt'
import operator
import ntpath
import posixpath


class ApacheConfigParserException(Exception):
    """Main Exception of ApacheConfigParser"""
    pass


def filterConfigItems(items, item_type, **kwargs):
    """filter config item in item list according to item type and item attributes"""
    def is_matched_config_item(item, **kwargs):
        for k, v in kwargs.items():
            # split function argument key to item attribute name and compare operator
            klist = k.rsplit('__', 1)
            if len(klist) == 2:
                key, op = klist
            else:
                key, op = k, 'eq'
            if not getattr(operator, op)(v, getattr(item, key)):
                return False
        return True

    if item_type:
        return [item for item in items if isinstance(item, item_type) and is_matched_config_item(item, **kwargs)]
    else:
        return [item for item in items if is_matched_config_item(item, **kwargs)]


def getConfigItemValue(items, item_type, **kwargs):
    """
    filter config item in item list according to item type and item attributes
    return the first matched config item's value
    """
    items = filterConfigItems(items, item_type, **kwargs)
    if items:
        return items[0].value
    return None


def getConfigItemValueList(items, item_type, **kwargs):
    """
    filter config item in item list according to item type and item attributes
    return the matched config item's value as list
    """
    items = filterConfigItems(items, item_type, **kwargs)
    return [item.value for item in items]


class ConfigItems(object):
    """The data structure of list of config items"""
    def __init__(self, items=None):
        self.__items = items or []

    def __getitem__(self, item):
        return self.__items[item]

    def __len__(self):
        return len(self.__items)

    @property
    def items(self):
        return self.__items

    def append(self, item):
        self.__items.append(item)

    def filter(self, **kwargs):
        """
        filter config items in the item list according to item type
        (called cls in function arguments) and item attributes
        return a new ConfigItems included the matched config items.
        """
        cls_str = 'cls'
        cls = kwargs.get(cls_str)
        if cls:
            del kwargs[cls_str]
        return ConfigItems(filterConfigItems(self.__items, cls, **kwargs))

    def get(self, **kwargs):
        """
        filter config items in the item list according to item type
        (called cls in function arguments) and item attributes
        if only one config item matched, return that config item
        else raise ApacheConfigParserException
        """
        cis = self.filter(**kwargs)
        if cis:
            if len(cis) == 1:
                return cis[0]
            else:
                raise ApacheConfigParserException('got more than one config items')
        else:
            raise ApacheConfigParserException('no config items got')

    def getValueOrNone(self, **kwargs):
        """return ConfigItems.get; return None if ApacheConfigParserException raised"""
        try:
            item = self.get(**kwargs)
            return item.value
        except ApacheConfigParserException:
            return None

    def values(self, *args, **kwargs):
        """
        filter config items in the item list according to item type
        (called cls in function arguments) and item attributes
        return the list of the matched item attributes
        if function argument flat is True, return the list of item's first specified attribute
        """
        flat = kwargs.get('flat', False)
        if flat and len(args) == 1:
            arg = args[0]
            return [getattr(item, arg) for item in self.__items]
        else:
            return [[getattr(item, arg) for arg in args] for item in self.__items]

    def first_value(self, *args, **kwargs):
        """
        filter config items in the item list according to item type
        (called cls in function arguments) and item attributes
        return the list of the first matched item attributes
        if function argument flat is True, return the first item's first specified attribute
        """
        l = self.values(*args, **kwargs)
        if l:
            return l[0]
        else:
            return None

    def __eq__(self, other):
        if isinstance(other, ConfigItems):
            return self.__items == other.items
        elif isinstance(other, list):
            return self.__items == other
        else:
            return False

    def __repr__(self):
        return "ConfigItems: %s" % self.__items


def getPathOperation(shell):
    return ntpath if shell.isWinOs() else posixpath
