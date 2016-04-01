# coding=utf-8
'''
Created on Dec 26, 2013

@author: ekondrashev
'''
import logger
import flow
import itertools
import fc_hba_topology
import os_platform_discoverer
import post_import_hooks
import service_loader
from service_loader import load_service_providers_by_file_pattern
import iteratortools
import command
from fptools import safeFunc as Sfn



class Discoverer(object):
    OS_PLATFORM = None

    def is_applicable(self, os_platform, executor=None, protocol_name=None, **kwargs):
        return os_platform == self.OS_PLATFORM

    def get_fc_hbas(self, shell):
        raise NotImplementedError('get_fc_hbas')

    def __eq__(self, other):
        if isinstance(other, Discoverer):
            return self.OS_PLATFORM == other.OS_PLATFORM
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def _build_fcportpdo(self, fcport):
        return fc_hba_topology.PortPdo(str(fcport.wwn),
                                                  name=fcport.id,
                                                  porttype=None,
                                                  portindex=fcport.id,
                                                  type=fcport.type,
                                                  trunkedstate=None,
                                                  symbolicname=None,
                                                  status=None,
                                                  state=None,
                                                  speed=fcport.speed,
                                                  scsiport=None,
                                                  id=fcport.id,
                                                  maxspeed=None,
                                                  fibertype=fcport.type,
                                                  domainid=None,
                                                  connectedtowwn=None)

    def _build_fchbapdo(self, fchba):
        hbatype_ = None
        return fc_hba_topology.Pdo(fchba.name,
                                   str(fchba.wwn),
                                   fchba.model,
                                   fchba.vendor,
                                   hbatype_,
                                   fchba.serial_number,
                                   fchba.driver_version,
                                   fchba.firmware_version)

    def build_fc_hba_pdo(self, fchba_descriptor):
        r'@types: fc_hba_model.FcHba, (fc_hba_model.FcPort, (fc_hba_model.FcHba, fc_hba_model.FcPort, host_base_parser.HostDescriptor)) -> list[fc_hba_topology.Pdo, (fc_hba_topology.PortPdo, (fc_hba_topology.Pdo?, fc_hba_topology.PortPdo?, host_base_parser.HostDescriptor?))]'
        fchba, fcports = fchba_descriptor

        fcport_and_target_details_pdos = []
        fchbapdo = self._build_fchbapdo(fchba)
        for fcport, target_fcdetails in fcports:
            fcportpdo = self._build_fcportpdo(fcport)

            target_fcpdos = []
            for target_fchba, target_fcport, target_container in target_fcdetails:
                target_fchbapdo = None
                target_fcportpdo = None
                if target_fchba:
                    target_fchbapdo = self._build_fchbapdo(target_fchba)
                if target_fcport:
                    target_fcportpdo = self._build_fcportpdo(target_fcport)
                target_fcpdos.append((target_fchbapdo, target_fcportpdo,
                                        target_container))

            fcport_and_target_details_pdos.append((fcportpdo,
                                                   tuple(target_fcpdos)))
        return fchbapdo, tuple(fcport_and_target_details_pdos)


def find_discoverer_by_shell(shell, protocol_name=None):
    os_platform_ = os_platform_discoverer.discover_platform_by_shell(shell)
    executor = command.getExecutor(shell)
    return find_discoverer_by_os_platform(os_platform_, executor=executor, protocol_name=protocol_name)


def find_discoverer_by_os_platform(platform, executor=None, protocol_name=None):
    discoverers = service_loader.global_lookup[Discoverer]
    for discoverer in discoverers:
        if Sfn(discoverer.is_applicable)(platform,
                                         executor=executor,
                                         protocol_name=protocol_name):
            return discoverer
    raise flow.DiscoveryException('No fc hba discoverer found for %s' % platform)


def discover_fc_hba_oshs_by_shell(shell, container_osh, protocol_name=None):
    oshs = []
    discoverer = find_discoverer_by_shell(shell, protocol_name=protocol_name)
    fc_hba_descriptors = discoverer.get_fc_hbas(shell)
    pdos = itertools.imap(discoverer.build_fc_hba_pdo, fc_hba_descriptors)
    reporter = fc_hba_topology.Reporter()
    for pdo in pdos:
        _, _, oshs_ = reporter.report_fchba_to_fchba(pdo, container_osh)
        oshs.extend(oshs_)
    return oshs


@post_import_hooks.invoke_when_loaded(__name__)
def __load_plugins(module):
    logger.debug('Loading fibre channel discoverers')
    load_service_providers_by_file_pattern('fc_hba_*_discoverer.py')
