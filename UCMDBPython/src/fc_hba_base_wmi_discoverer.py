# coding=utf-8
'''
Created on Apr 1, 2014

@author: ekondrashev
'''

import fc_hba_discoverer
import logger

from fc_hba_descriptors_by_windows_wmi import (get_fc_hba_descriptors,
                                                parse_wwn,
                                                parse_port_type)
import fc_hba_model

from fptools import safeFunc as Sfn
import fc_hba_topology


class Discoverer(fc_hba_discoverer.Discoverer):

    def is_applicable(self, os_platform, executor=None, protocol_name=None, **kwargs):
        return False

    def get_executor(self, shell):
        raise NotImplementedError('get_executor')

    def get_fc_hbas(self, shell):
        result = []
        executor = self.get_executor(shell)
        pairs = get_fc_hba_descriptors(executor)
        parse_wwn_ = Sfn(parse_wwn)
        for adapter_descriptor, port_descriptors in pairs:
            hba_id = adapter_descriptor.UniqueAdapterId
            name = adapter_descriptor.InstanceName
            node_wwn = adapter_descriptor.NodeWWN
            node_wwn = node_wwn and parse_wwn_(node_wwn)
            vendor = adapter_descriptor.Manufacturer
            model = adapter_descriptor.Model
            serial_number = adapter_descriptor.SerialNumber
            driver_version = adapter_descriptor.DriverVersion
            firmware_version = adapter_descriptor.FirmwareVersion
            fchba = fc_hba_model.FcHba(hba_id, name, wwn=node_wwn,
                                       vendor=vendor, model=model,
                                       serial_number=serial_number,
                                       driver_version=driver_version,
                                       firmware_version=firmware_version)
            ports = []
            for port_descriptor in port_descriptors:
                try:
                    port_id = port_descriptor.UniquePortId
                    portname = port_descriptor.InstanceName
                    port_wwn = parse_wwn_(port_descriptor.Attributes.PortWWN)
                    type_ = Sfn(parse_port_type)(port_descriptor.Attributes.PortType)
                    port_speed = float(port_descriptor.Attributes.PortSpeed)
                    ports.append((fc_hba_model.FcPort(port_id, port_wwn, type_, portname, speed = port_speed),
                                  ()))
                except (TypeError, ValueError), ex:
                    logger.debugException('Failed to create fchba data object')

            result.append((fchba, tuple(ports)))
        return tuple(result)

    def _build_fcportpdo(self, fcport):
        return fc_hba_topology.PortPdo(str(fcport.wwn),
                                      name=fcport.name,
                                      porttype=None,
                                      portindex=None,
                                      type=fcport.type,
                                      trunkedstate=None,
                                      symbolicname=None,
                                      status=None,
                                      state=None,
                                      speed=fcport.speed,
                                      scsiport=None,
                                      #fcport.id contains BigInteger value
                                      #which cannot be reported as integer
                                      #which is fcport_portid field type
                                      id=None,
                                      maxspeed=None,
                                      fibertype=fcport.type,
                                      domainid=None,
                                      connectedtowwn=None)
