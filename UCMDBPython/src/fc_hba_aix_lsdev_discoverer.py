# coding=utf-8
'''
Created on Apr 17, 2014

@author: ekondrashev

The module introduces fchba discoverer implementation for AIX platform
'''
import re
from fptools import methodcaller
from operator import attrgetter

import vendors
import fptools
import logger
import wwn
from fptools import safeFunc as Sfn

import service_loader
from os_platform_discoverer import enum as os_platforms
import fc_hba_discoverer
import command
import fc_hba_model
import lsdev_aix
import fcstat_aix
import vital_product_data


def _parse_driver_version(lines):
    for line in lines:
        m = re.search('(\d+\.\d+\.\d+\.\d+)\s\s.+?\s\s.+', line)
        if m:
            return m.group(1)


@service_loader.service_provider(fc_hba_discoverer.Discoverer)
class Discoverer(fc_hba_discoverer.Discoverer):
    '''The class provides implementation of fchba discovery for AIX
    overriding is_applicable and get_fc_hbas methods and introducing additional
    puplic methods:
        *get_driver_version
        *list_fc_adapter_names
        *parse_vendor_from_driverid
    '''
    OS_PLATFORM = os_platforms.AIX

    def is_applicable(self, os_platform, executor=None, protocol_name=None, **kwargs):
        is_applicable_platform_fn = fc_hba_discoverer.Discoverer.is_applicable
        is_applicable_platform = is_applicable_platform_fn(self, os_platform)
        if is_applicable_platform:
            lsdev = Sfn(lsdev_aix.find)(executor)
            vpd_impl = Sfn(vital_product_data.Discoverer.find_impl)(executor)
            return lsdev and vpd_impl

    def __get_produce_result_executor(self, shell):
        return command.ChainedCmdlet(command.cmdlet.executeCommand(shell),
                                         command.cmdlet.produceResult)

    def get_driver_version(self, driverid, exec_):
        '''Discovers driver version string by provided device id
        with `lslpp` command

        @param driverid: driver id string returned either by `fcstat fcx`,
            `lsdev -vpd -dev fcx` or `lscfg -vpl fcx` commands
        @type driverid: str
        @param exec_: callable to execute commands and produce result
        @type exec_: callable[command.Cmd]->object
        @return: driver version string
        @rtype: str
        '''
        cmdline = 'lslpp -l "*%s.rte"' % driverid
        handlers = (command.UnixBaseCmd.DEFAULT_HANDLERS +
                         (command.raise_on_non_zero_return_code,
                          command.raise_when_output_is_empty,
                          attrgetter('output'),
                          methodcaller('strip'),
                          methodcaller('splitlines'),
                          _parse_driver_version
                         ))
        handler = command.UnixBaseCmd.compose_handler(handlers)
        c = command.UnixBaseCmd(cmdline, handler=handler)
        return exec_(c)

    def list_fc_adapter_names(self, lsdev, exec_):
        '''Lists all available fc adapater names using provided lsdev wrapper
        implementation

        @param lsdev: lsdev command implementation
        @type lsdev: lsdev_aix.Cmd
        @param exec_: callable to execute commands and produce result
        @type exec_: callable[command.Cmd]->object
        @return: list of fc adapter names
        @rtype: list[str]
        '''
        lsdev = lsdev()
        cmd = lsdev.list_device_names(lsdev.classes.adapter)
        devices = exec_(cmd)
        fn = fptools.methodcaller('startswith', 'fcs')
        return filter(fn, devices)

    @staticmethod
    def parse_vendor_from_driverid(driverid):
        '''Parses vendor by extracting vendor id from provided driver id

        @param driverid: driver id string returned either by `fcstat fcx`,
            `lsdev -vpd -dev fcx` or `lscfg -vpl fcx` commands
        @type driverid: str
        @return: vendor string
        @rtype: basestring
        @raise KeyError: if no vendor available for passed id
        @raise ValueError: if produced vendor id is not convertible to int
        '''
        #The 1st 4 chars represent PCI vendor ID (in big-endian order)
        vendor = driverid[0:4]
        #conver to little-endian
        vendor = vendor[2:] + vendor[:2]
        return vendors.find_name_by_id_in_hex(vendor)

    def get_fc_hbas(self, shell):
        result = []
        executor = command.cmdlet.executeCommand(shell)
        lsdev = lsdev_aix.find(executor)
        vpd_discoverer = vital_product_data.Discoverer.find_impl(executor)

        exec_ = Sfn(self.__get_produce_result_executor(shell).process)
        fcadapters = self.list_fc_adapter_names(lsdev, exec_)
        for fcs in fcadapters:
            try:
                descriptor = vpd_discoverer.get_fc_vpd_by_devicename(fcs, executor)
                id_ = descriptor.hardware_location_code
                nodewwn = descriptor.device_specific.get('Z8')
                fw_version = None
                if 'Z9' in descriptor.device_specific:
                    fw_version = descriptor.device_specific.get('Z9')
                    _, fw_version = fw_version.split('.')
                nodewwn = wwn.parse_from_str(nodewwn)

                portwwn = descriptor.network_address
                serialnum = descriptor.serial_number
                model = descriptor.platform_specific.model

                driverid = descriptor.driverid
                vendor = Sfn(self.parse_vendor_from_driverid)(driverid)

                driver_version = self.get_driver_version(driverid, exec_)
                fchba = fc_hba_model.FcHba(id_, fcs,
                                            wwn=nodewwn,
                                            vendor=vendor, model=model,
                                            serial_number=serialnum,
                                            driver_version=driver_version,
                                            firmware_version=fw_version)
                ports = []
                try:
                    port_wwn = wwn.parse_from_str(portwwn)
                    fcstat = Sfn(fcstat_aix.find)(executor)
                    port_id = None
                    type_ = None
                    if fcstat:
                        fcstat_descriptor = exec_(fcstat(fcs))
                        if fcstat_descriptor:
                            port_id = Sfn(int)(fcstat_descriptor.port_fc_id, 16)
                            type_ = fcstat_descriptor.port_type
                            port_speed = fcstat_descriptor.running_port_speed
                    ports.append((fc_hba_model.FcPort(port_id, port_wwn, type_, None, port_speed),
                                  ()))
                except (command.ExecuteException, TypeError, ValueError), ex:
                    logger.debugException('Failed to create fcport data object')

                result.append((fchba, ports))

            except (command.ExecuteException, TypeError, ValueError), ex:
                logger.debugException('Failed to create fchba data object')

        return tuple(result)
