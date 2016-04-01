# coding=utf-8
'''
Created on Apr 25, 2014

@author: ekondrashev

Module provides abstraction layer for the VPD(Vital Product Data) discovery
'''
from collections import namedtuple
import post_import_hooks
import logger
from service_loader import load_service_providers_by_file_pattern
import re
from fptools import findFirst, identity, safeFunc as Sfn
from itertools import ifilter
import service_loader
import os_platform_discoverer


class Discoverer(object):
    '''
    The class defines interface methods for VPD discovery for different devices
    and different platforms. They are:
    *is_applicable
    *find_impl
    *get_fc_vpd_by_devicename
    *parse_fc_vpd

    The class also defines OS_PLATFORM static attribute containing platform
    instance which current discovery implementation is applicable for
    '''
    OS_PLATFORM = None

    def is_applicable(self, osplatform, executor, **kwargs):
        '''Returns bool value indicating whether current discoverer
        is applicable for target destination

        @param osplatform: object representing target destination
                            os platform information
        @type osplatform: os_platform_discoverer.Platform
        @param executor: a command executor instance
        @type executor: command.Executor
        @return: True if command is applicable for target destination,
            False otherwise
        @rtype: bool
        '''
        return osplatform == self.OS_PLATFORM

    @staticmethod
    def _get_fc_vpd_cmd(devicename, executor):
        raise NotImplementedError('_get_fc_vpd_cmd')

    def get_fc_vpd_by_devicename(self, devicename, executor):
        '''Returns vital product data descriptor for all available
        fibre channel adapters

        @param devicename: device name of a fibre channel adapter to
                            get information for
        @type devicename: str
        @param executor: a command executor instance
        @type executor: command.Executor
        @return: vpd descriptor for provided device name
        @rtype: vital_product_data.FcDescriptor
        @raise command.ExecuteException: in case on fibre channel vpd discovery
                                        failure
        '''
        result = executor.process(self._get_fc_vpd_cmd(devicename, executor))
        lines = result.handler(result)
        return self.parse_fc_vpd(lines)

    @staticmethod
    def parse_fc_vpd(lines):
        '''Parses fibre channel vpd data to a FcDescriptor instance

        @param lines: fibre channel vpd output splitted in lines
        @type lines: seq[str]
        @return: parsed fc hba descriptor
        @rtype: vital_product_data.FcDescriptor
        '''
        devicename = None
        location = None
        description = None
        driverid = None
        m = re.search('(fcs\d+)\s+(.*?)\s\s(.+\(([0-9a-fA-F]+)\))', lines[0])
        if m:
            devicename, location, description, driverid = m.groups()

        tag = 'PLATFORM SPECIFIC'
        tag_index = findFirst(identity,
                              (i for i, line in enumerate(lines) if tag in line))

        base_attrs = {}
        device_specific_attrs = {}
        for line in lines[1: tag_index]:
            m = re.match('(.+?)\.\.+(.+)', line)
            if m:
                name, value = m.groups()
                name = name.strip()
                value = value.strip()
                if name.startswith('Device Specific.'):
                    _, name = re.split('\.', name, maxsplit=1)
                    device_specific_attrs[name.strip('()')] = value
                else:
                    base_attrs[name] = value

        platform_specific_attrs = {}
        for line in ifilter(identity, lines[tag_index + 1:]):
            name, value = re.split('\:', line, maxsplit=1)
            platform_specific_attrs[name.strip()] = value.strip()

        name = platform_specific_attrs['Name']
        model = platform_specific_attrs['Model']
        node = platform_specific_attrs['Node']
        device_type = platform_specific_attrs['Device Type']
        physical_location = platform_specific_attrs['Physical Location']

        platform_specific = FcPlatfromSpecificDescriptor(name, model,
                                                         node, device_type,
                                                         physical_location)
        part_number = base_attrs.get('Part Number')
        serial_number = base_attrs.get('Serial Number')
        manufacturer = base_attrs.get('Manufacturer')
        ec_level = base_attrs.get('EC Level')
        customer_card_id_number = base_attrs.get('Customer Card ID Number')
        fru_number = base_attrs.get('FRU Number')
        network_address = base_attrs.get('Network Address')
        ros_level_and_id = base_attrs.get('ROS Level and ID')
        hardware_location_code = base_attrs.get('Hardware Location Code')
        return FcDescriptor(devicename, location, driverid,
                            description, part_number, serial_number,
                            manufacturer, ec_level, customer_card_id_number,
                            fru_number, network_address, ros_level_and_id,
                            hardware_location_code, device_specific_attrs,
                            platform_specific)

    @classmethod
    def find_impl(cls, executor):
        '''Finds implementation of vital_product_data.Discoverer for current
        destination

        @param param: a command executor instance
        @type executor: command.Executor
        @return: implementation of vpd discoverer applicable for current
                destination
        @rtype: vital_product_data.Discoverer
        @raise service_loader.NoImplementationException: if no implementation
                found
        '''
        p = os_platform_discoverer.discover_platform_by_shell(executor.shell)
        vpd_impls = service_loader.global_lookup[Discoverer]
        for vpd_impl in vpd_impls:
            if Sfn(vpd_impl.is_applicable)(p, executor):
                return vpd_impl
        raise service_loader.NoImplementationException('No lsdev impl found')


FcDescriptor = namedtuple('FcDescriptor',
                            ('name', 'location',
                             'driverid',
                             'description',
                             'part_number', 'serial_number',
                             'manufacturer', 'ec_level',
                             'customer_card_id_number',
                             'fru_number', 'network_address',
                             'ros_level_and_id',
                             'hardware_location_code',
                             'device_specific',
                             'platform_specific', ))

FcPlatfromSpecificDescriptor = namedtuple('FcPlatfromSpecificDescriptor',
                                          ('name model node device_type '
                                           'physical_location'))


@post_import_hooks.invoke_when_loaded(__name__)
def __load_plugins(module):
    logger.debug('Loading vital product data discoverers')
    load_service_providers_by_file_pattern('vital_product_data_*_impl.py')
