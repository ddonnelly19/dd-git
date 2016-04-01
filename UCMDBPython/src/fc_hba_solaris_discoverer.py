# coding=utf-8
'''
Created on Dec 26, 2013

@author: ekondrashev
'''
import service_loader
from fcinfo_solaris import find as find_fcinfo_impl
import fc_hba_discoverer
from os_platform_discoverer import enum as os_platforms
import fc_hba_model
import command
import logger
import wwn
import re
from fptools import safeFunc as Sfn
from fc_hba_model import _parse_port_speed

@service_loader.service_provider(fc_hba_discoverer.Discoverer)
class Discoverer(fc_hba_discoverer.Discoverer):
    OS_PLATFORM = os_platforms.SUNOS

    def is_applicable(self, os_platform, executor=None, protocol_name=None, **kwargs):
        is_applicable_platform_fn = fc_hba_discoverer.Discoverer.is_applicable
        is_applicable_platform = is_applicable_platform_fn(self, os_platform)
        if is_applicable_platform:
            fcinfo_impl = find_fcinfo_impl(executor)
            return fcinfo_impl is not None

    def get_fc_hbas(self, shell):
        executor = command.cmdlet.executeCommand(shell)
        fcinfo_impl = find_fcinfo_impl(executor)()
        exec_ = command.get_exec_fn(executor)
        safe_exec_ = command.get_safe_exec_fn(executor)

        descriptors = exec_(fcinfo_impl.hba_port())
        result = []
        for fchba_descriptor in descriptors:
            try:
                name = fchba_descriptor.name
                nodewwn = wwn.parse_from_str(fchba_descriptor.node_wwn)
                portwwn = fchba_descriptor.port_wwn
                model = fchba_descriptor.model
                vendor = fchba_descriptor.vendor
                type_ = fchba_descriptor.type
                serialnum = fchba_descriptor.serial_number
                driver_version = fchba_descriptor.driver_version
                fw_version = fchba_descriptor.firmware_version
                port_speed = fchba_descriptor.port_speed
                fchba = fc_hba_model.FcHba(name, name,
                                           wwn=nodewwn,
                                           vendor=vendor, model=model,
                                           serial_number=serialnum,
                                           driver_version=driver_version,
                                           firmware_version=fw_version)
                ports = []
                try:
                    port_id = None
                    port_wwn = wwn.parse_from_str(portwwn)
                    speed = _parse_port_speed(port_speed)
                    remote_port_descriptors = safe_exec_(fcinfo_impl.remote_port.p(portwwn))
                    target_fchbas = self._create_target_fchba_details(remote_port_descriptors)
                    ports.append((fc_hba_model.FcPort(port_id, port_wwn,
                                                      type_, None, speed),
                                  target_fchbas))
                except (command.ExecuteException, TypeError, ValueError), ex:
                    logger.debugException('Failed to create fcport data object')
                result.append((fchba, ports))
            except (command.ExecuteException, TypeError, ValueError), ex:
                logger.debugException('Failed to create fchba data object')
        return tuple(result)

    def _create_target_fchba_details(self, remote_port_descriptors):
        result = []
        if remote_port_descriptors:
            for descriptor in remote_port_descriptors:
                try:
                    wwpn = wwn.parse_from_str(descriptor.remote_port_wwn)
                    wwnn = wwn.parse_from_str(descriptor.node_wwn)
                    fchba = fc_hba_model.FcHba('', '', wwn=wwnn)
                    fcport = fc_hba_model.FcPort(None, wwpn)
                    result.append((fchba, fcport, None))
                except (TypeError, ValueError):
                    logger.debugException('Failed to create target fchba/fcport data object')
        return tuple(result)
