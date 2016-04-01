import command
import wmiutils
from itertools import imap, ifilter
from functools import partial
import re
import fptools
from fptools import identity, each, comp


class WmicExecuteException(command.ExecuteException):
    '''Base class for WMIC exceptions'''
    pass


class NoWmicInstacesException(WmicExecuteException):
    '''An exception indicating that WMI query execution finished
    with 'No Instance(s) Available' message'''
    pass


def raise_when_no_instances(result):
    '''Checks whether result output contains no 'No Instance(s) Available.'
    substring

    @param result: target result object to check
    @type result: command.Result
    @return: same result object
    @rtype: command.Result
    @raise NoWmicInstancesException: if result output
        contains 'No Instance(s) Available.' substring
    '''
    if re.match('No Instance(s) Available.', result):
        raise NoWmicInstacesException("No instances found")
    return result


def raise_when_empty(result):
    '''Checks whether result is not empty

    @param result: target result object to check
    @type result: command.Result
    @return: same result object
    @rtype: command.Result
    @raise WmicExecuteException: if result object is empty
    '''
    if not result:
        raise WmicExecuteException("No items parsed")
    return result


def parse_items(fields, wmi_class, output, separator='='):
    """Parses wmic command output

    @param fields: originally requested list of fileds
    @type fields: seq[basestring]
    @param wmi_class: a WMI class descriptor
    @type wmi_class: namedtuple class enhanced with parse
       and get_type_by_name methods. See build_wmi_class_descriptor for details
    @param output: a command execution output result
    @type output: basestring
    @param separator: key-value separator substring
    @type separator: basestring
    @return: iterable of dictionaries
    @rtype: tuple[dict]
    """
    sep_pattern = re.compile('\s*%s\s*' % separator)
    split_by_sep = fptools.comp(sep_pattern.split, unicode.strip)

    lines = ifilter(identity, output.strip().splitlines())

    grouped = []
    _kwargs = {}
    for key, value in imap(split_by_sep, lines):
        if key in _kwargs:
            grouped.append(_kwargs)
            _kwargs = {}
        _kwargs[key] = value
    grouped.append(_kwargs)

    result = [parse_item(fields, wmi_class, item)
              for item in grouped]
    return tuple(result)


def parse_item(fields, wmi_class, item):
    '''Parses one particular WMI object grouping its fields according
    to WMI class descriptor. If one of the fields happen to be of an embedded
    type, parse_item function is called recursively for this field.

    @param fields: requested fields to parse
    @type fields: seq[basestring]
    @param wmi_class: a WMI class descriptor
    @type wmi_class: namedtuple class enhanced with parse
       and get_type_by_name methods. See build_wmi_class_descriptor for details
    @param item: name/values pairs representing WMI object
    @param item: dict
    @return: WMI object name/value pairs according to wmi_class descriptor
    @rtype: dict[basestring, basestring or dict]
    '''
    filtered_item = {}
    for field in fields:
        wmitype = wmi_class.get_type_by_name(field)
        if wmitype.is_embedded:
            filtered_item[field] = parse_item(wmitype.embedded_type._fields,
                                              wmitype.embedded_type, item)
        else:
            filtered_item[field] = item[field]
    return filtered_item


class __WmicQueryBuilder(wmiutils.WmicQueryBuilder):

    def __init__(self, objectName, wmicpath=None):
        wmiutils.WmicQueryBuilder.__init__(self, objectName)
        self.__wmicpath = wmicpath
        WMIC_QUERY_TEMPLATE = wmiutils.WmicQueryBuilder.WMIC_QUERY_TEMPLATE
        if wmicpath:
            self.WMIC_QUERY_TEMPLATE = WMIC_QUERY_TEMPLATE.replace('wmic', wmicpath)


class Cmd(command.BaseCmd):
    '''
    Command class for `wmic` executable overriding command.Cmdlet.process
    method and extending
    command.BaseCmd.DEFAULT_HANDLERS static attribute with additional
    handlers specific to wmic command.
    Path to wmic binary is used as a cmdline for command.BaseCmd

    The class defines additional public methods:
     * get_cmdline
     * create_wmic_command
    '''
    DEFAULT_HANDLERS = (command.BaseCmd.DEFAULT_HANDLERS +
                        (command.cmdlet.raiseOnNonZeroReturnCode,
                         command.cmdlet.raiseWhenOutputIsNone,
                         command.cmdlet.stripOutput,
                         raise_when_no_instances,
                         ))

    def __init__(self, wmicpath=None, handler=None):
        '''
        @param wmicpath: path to `wmic` executable
        @type wmicpath: basestring or file_system.Path
        '''
        wmicpath = wmicpath and str(wmicpath) or 'wmic'
        command.BaseCmd.__init__(self, wmicpath, handler=handler)

    def get_cmdline(self, wmicmd):
        '''Builds wmic command line for passed WMI command

        @param wmicmd: a WMI command to build command line for
        @type wmicmd: wmi_base_command.Cmd
        @return: wmic command line for passed WMI command
        @rtype: basestring
        '''
        wmi_clsname = wmicmd.get_wmi_class_name()
        query_builder = __WmicQueryBuilder(wmi_clsname, self.cmdline)

        each(query_builder.addQueryElement, wmicmd.fields)
        query_builder.usePathCommand(1)
        query_builder.useSplitListOutput(1)
        query_builder.setNamespace('\\\\%s' % wmicmd.NAMESPACE)
        return query_builder.buildQuery()

    def create_wmic_command(self, wmicmd):
        '''Creates wmic command with a WMI query built basing on passed wmicmd

        @param wmicmd: a WMI command to create wmic command for
        @type wmicmd: wmi_base_command.Cmd
        @return: new command object with wmic cmdline
        @rtype: command.Cmd
        '''
        handler = comp(wmicmd.handler,
                       partial(parse_items, wmicmd.fields, wmicmd.WMI_CLASS),
                       raise_when_empty,
                       self.handler)
        return command.Cmd(self.get_cmdline(wmicmd), handler)

    def process(self, other):
        return self.create_wmic_command(other)
