'''
Created on Dec 30, 2013

@author: ekondrashev
'''
import command
from command import ChainedCmdlet
import hba_wmi_command
from pyargs_validator import not_none, validate, not_empty
import fptools
import operator
import wwn


@validate(not_none)
def get_fc_hba_descriptors(executor):
    r'''
    Discovers fibre channel info using wmi `MSFC_FCAdapterHBAAttributes` and
    `MSFC_FibrePortHBAAttributes` classes

    @param executor: an executor instance to run WMI commands
    @type executor: command.ExecutorCmdlet
    @return: collection of FC HBA descriptor and its ports pairs
    @rtype: tuple[MSFC_FCAdapterHBAAttributesCmd.WMI_CLASS, tuple[MSFC_FibrePortHBAAttributesCmd.WMI_CLASS]]
    @raise ValueError: if no executor passed
    @raise command.ExecutionException: on command execution failure
    @raise com.hp.ucmdb.discovery.library.clients.protocols.command.TimeoutException: on command timeout
    '''
    executor = ChainedCmdlet(executor, command.cmdlet.produceResult)
    adapters = hba_wmi_command.MSFC_FCAdapterHBAAttributesCmd() | executor
    ports = hba_wmi_command.MSFC_FibrePortHBAAttributesCmd() | executor
    fn = operator.attrgetter('InstanceName')
    ports_by_instancename = fptools.groupby(fn, ports)
    result = []
    for adapter in adapters:
        result.append((adapter, ports_by_instancename.get(adapter.InstanceName) or ()))
    return tuple(result)


@validate(not_empty)
def parse_wwn(wwn_as_uchar_list):
    '''
    Converts list of uchar to WWN object.
    @types: list[str] or list[int] -> wwn.WWN
    @raise: ValueError if passed list represents invalid hex octets
    '''
    wwn_as_int_list = map(int, wwn_as_uchar_list)
    octets = []
    for hex_ in map(hex, wwn_as_int_list):
        hex_ = hex_[2:].rjust(2, '0')
        octets.append(hex_)
    return wwn.WWN(int(''.join(octets), 16))


def parse_port_type(number):
    '''
    Dereferences port type represented by number to sting value
    @types: str or int -> str
    @raise ValueError: if passed number is not convertible to int
    '''
    port_types = hba_wmi_command.MSFC_FibrePortHBAAttributesCmd.PORT_TYPES
    port_type = port_types.value_by_number(number)
    return port_type and str(port_type)
