# coding=utf-8
'''
Created on Dec 26, 2013

@author: ekondrashev
'''
import service_loader
import fc_hba_discoverer
from os_platform_discoverer import enum as os_platforms
import fc_hba_descriptors_by_hpux_fcmsutil
import fc_hba_topology
import logger
import fc_hba_model
import wwn
import vendors
import re
from fc_hba_model import _parse_port_speed

from fptools import safeFunc as Sfn

@service_loader.service_provider(fc_hba_discoverer.Discoverer)
class Discoverer(fc_hba_discoverer.Discoverer):
    OS_PLATFORM = os_platforms.HPUX

    def get_fc_hbas(self, shell):
        result = []
        descriptors = fc_hba_descriptors_by_hpux_fcmsutil.get_fc_hba_descriptors(shell)
        find_name_by_id_in_hex = Sfn(vendors.find_name_by_id_in_hex)
        for ioscan_dscriptor, fc_descriptor, fc_vpd_descriptor in descriptors:
            try:
                hba_id = ioscan_dscriptor.device_filename
                name = ioscan_dscriptor.device_filename
                node_wwn = fc_descriptor.n_port_node_world_wide_name
                node_wwn = wwn.normalize(node_wwn)
                vendor = find_name_by_id_in_hex(fc_descriptor.vendor_id)
                model = fc_vpd_descriptor.part_number
                serial_number = fc_vpd_descriptor.part_serial_number
                driver_version = fc_descriptor.driver_version
                firmware_version = fc_vpd_descriptor.rom_firmware_version
                port_speed = fc_descriptor.link_speed
                fchba = fc_hba_model.FcHba(hba_id, name, wwn=node_wwn,
                                           vendor=vendor, model=model,
                                           serial_number=serial_number,
                                           driver_version=driver_version,
                                           firmware_version=firmware_version)
                port_id = fc_descriptor.local_n_port_id
                port_wwn = wwn.normalize(fc_descriptor.n_port_port_world_wide_name)
                type_ = fc_descriptor.topology
                ports = []

                port_id = Sfn(int)(port_id, 16)
                speed = _parse_port_speed(port_speed)

                remote_descriptors = Sfn(fc_hba_descriptors_by_hpux_fcmsutil.get_remote_fc_hba_descriptors)(shell, ioscan_dscriptor.device_filename)
                target_fchbas = self._create_target_fchba_details(remote_descriptors)
                ports.append((fc_hba_model.FcPort(port_id, port_wwn, type_, None, speed),
                                  target_fchbas))
                result.append((fchba, tuple(ports)))
            except (TypeError, ValueError), ex:
                logger.debugException('Failed to create fchba data object')
        return result

    def _create_target_fchba_details(self, remote_descriptors):
        result = []
        if remote_descriptors:
            for remote_descriptor in remote_descriptors:
                try:
                    port_id = Sfn(int)(remote_descriptor.target_n_port_id, 16)
                    wwpn = wwn.normalize(remote_descriptor.target_port_wwn)
                    wwnn = wwn.normalize(remote_descriptor.target_node_wwn)
                    port_type = remote_descriptor.port_type
                    port_name = ''
                    node_name = ''
                    if remote_descriptor.symbolic_port_name and remote_descriptor.symbolic_port_name.lower() != 'none':
                        port_name = remote_descriptor.symbolic_port_name
                    if remote_descriptor.symbolic_node_name and remote_descriptor.symbolic_node_name.lower() != 'none':
                        node_name = remote_descriptor.symbolic_node_name

                    fchba = fc_hba_model.FcHba('', node_name, wwn=wwnn)
                    fcport = fc_hba_model.FcPort(port_id, wwpn, type=port_type, name = port_name)
                    result.append((fchba, fcport, None))
                except (TypeError, ValueError):
                    logger.debugException('Failed to create target fchba/fcport data object')
        return tuple(result)
