# coding=utf-8
'''
Created on May 5, 2014

@author: ekondrashev
'''
import service_loader
from collections import defaultdict
import fc_hba_discoverer
from os_platform_discoverer import enum as os_platforms
from fptools import safeFunc as Sfn, comp, methodcaller
from esxcli import (find as find_esxcli_impl,
                    Storage as EsxcliStorageNamespace,
                    Software as EsxcliSoftwareNamespace)
import command
import fc_hba_model
import wwn
import logger
import vendors
import fc_hba_descriptors_by_vmkmgmt_keyval
import fptools
import re
from fc_hba_model import _parse_port_speed



@service_loader.service_provider(fc_hba_discoverer.Discoverer)
class Discoverer(fc_hba_discoverer.Discoverer):
    '''The class provides implementation of fchba discovery for ESX 5.x
    overriding is_applicable and get_fc_hbas methods and introducing additional
    public methods:
        *get_vendor
    '''
    OS_PLATFORM = os_platforms.VMKERNEL

    def is_applicable(self, os_platform, executor=None, protocol_name=None, **kwargs):
        is_applicable_platform_fn = fc_hba_discoverer.Discoverer.is_applicable
        is_applicable_platform = is_applicable_platform_fn(self, os_platform)
        if is_applicable_platform:
            esxcli_impl = find_esxcli_impl(executor)
            if esxcli_impl:
                esxcli_impl = esxcli_impl()
                exec_ = command.get_exec_fn(executor)
                return (exec_(esxcli_impl.iscorrectsyntax('storage san fc list')) and
                        exec_(esxcli_impl.iscorrectsyntax('software vib get -n driver')) and
                        exec_(esxcli_impl.iscorrectsyntax('storage core adapter list'))
                        )

    def get_vendor(self, vmhba, executor):
        handler = comp(*reversed((command.cmdlet.raiseOnNonZeroReturnCode,
                                 command.cmdlet.raiseWhenOutputIsNone,
                                 command.cmdlet.stripOutput,
                                 _parse_vmkchdev_l)))
        lspci = command.UnixBaseCmd("vmkchdev -l | grep %s" % vmhba,
                                    handler=handler)
        result = executor.process(lspci)
        result = result.handler(result)
        return vendors.find_name_by_id_in_hex(result)

    def _get_fchba_descriptor(self, driver, vmhbaname, executor):
        impl = fc_hba_descriptors_by_vmkmgmt_keyval.find_impl(drivername=driver, executor=executor)
        return impl(vmhbaname, executor)

    def _compose_adapter_identifier(self, wwnn, wwpn):
        return 'fc.%s:%s' % (wwnn.tostr(separator=''),
                             wwpn.tostr(separator=''))

    def _decompose_adapter_identifier(self, identifier):
        m = re.match('fc\.(.+):(.+)', identifier)
        if m:
            return [wwn.parse_from_str(wwn_, 16) for wwn_ in m.groups()]

    def get_fc_hbas(self, shell):
        result = defaultdict(list)
        executor = command.cmdlet.executeCommand(shell)
        esxcli = find_esxcli_impl(executor)()
        esxcli = esxcli.formatter('csv')
        esxcli_exec = command.get_exec_fn(esxcli, executor)
        storage = EsxcliStorageNamespace(esxcli)
        software = EsxcliSoftwareNamespace(esxcli)

        scsi_path_by_adapter_identifier = fptools.groupby(methodcaller('get', 'AdapterIdentifier'), esxcli_exec(storage.core.path.list()))

        adapters = esxcli_exec(storage.core.adapter.list())
        grouped_adapters = dict((adapter.get('HBAName'), adapter)
                                    for adapter in adapters)

        grouped = defaultdict(list)
        for descriptor in esxcli_exec(storage.san.fc.list()):
            grouped[(descriptor.get('Adapter'),
                     descriptor.get('NodeName'))].append(descriptor)

        get_vendor = Sfn(self.get_vendor)
        get_fchba_descriptor = Sfn(self._get_fchba_descriptor)
        for key, descriptors in grouped.iteritems():
            try:
                vmhba, nodewwn = key
                nodewwn = wwn.parse_from_str(nodewwn)
                name = vmhba
                id_ = vmhba
                adapter_descriptor = grouped_adapters.get(vmhba)
                driverversion = None
                vendor = get_vendor(vmhba, executor)
                model = None
                fwversion = None
                serialnum = None
                if adapter_descriptor:
                    id_ = adapter_descriptor.get('UID')
                    driver = adapter_descriptor.get('Driver')
                    vib_descriptor = esxcli_exec(software.vib.get(vibname=driver))
                    driverversion = vib_descriptor.get('Version')
                    fchabdescriptor = get_fchba_descriptor(driver, vmhba, executor)
                    if fchabdescriptor:
                        model = fchabdescriptor.model
                        fwversion = fchabdescriptor.firmwareversion
                        serialnum = fchabdescriptor.serialnumber
                        driverversion = fchabdescriptor.driverversion

                fchba = fc_hba_model.FcHba(id_, name,
                                           wwn=nodewwn,
                                           vendor=vendor, model=model,
                                           serial_number=serialnum,
                                           driver_version=driverversion,
                                           firmware_version=fwversion)

                ports = []
                for fcdescriptor in descriptors:
                    try:
                        portwwn = fcdescriptor.get('PortName')
                        porttype = fcdescriptor.get('PortType')
                        portwwn = wwn.parse_from_str(portwwn)
                        portid = fcdescriptor.get('PortID')
                        port_speed = _parse_port_speed(fcdescriptor.get('Speed'))
                        portid = Sfn(int)(portid, 16)

                        adapter_identifier = self._compose_adapter_identifier(nodewwn, portwwn)
                        scsi_paths = scsi_path_by_adapter_identifier.get(adapter_identifier)
                        target_fcdescriptors = self._create_target_fchba_details(scsi_paths)
                        ports.append((fc_hba_model.FcPort(portid, portwwn,
                                                          porttype, None, port_speed),
                                      target_fcdescriptors))
                    except (command.ExecuteException, TypeError, ValueError), ex:
                        logger.debugException('Failed to create fcport data object')
                result[fchba].extend(ports)
            except (command.ExecuteException, TypeError, ValueError), ex:
                logger.debugException('Failed to create fchba data object')
        return result.items()

    def _create_target_fchba_details(self, scsi_paths):
        result = []
        if scsi_paths:
            for path in scsi_paths:
                try:
                    identifier = path.get('TargetIdentifier')
                    wwnn, wwpn = self._decompose_adapter_identifier(identifier)
                    fchba = fc_hba_model.FcHba('', '', wwn=wwnn)
                    fcport = fc_hba_model.FcPort(None, wwpn)
                    result.append((fchba, fcport, None))
                except (TypeError, ValueError):
                    logger.debugException('Failed to create target fchba/fcport data object')
        return tuple(result)


def _parse_vmkchdev_l(text):
    _, vid_did, _, _, _ = text.split(' ')
    vendorid, _ = vid_did.split(':')
    return vendorid
