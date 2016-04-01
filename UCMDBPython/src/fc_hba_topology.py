# coding=utf-8
'''
Created on Dec 26, 2013

@author: ekondrashev
'''
import collections
from itertools import imap
from appilog.common.system.types import ObjectStateHolder
from pyargs_validator import not_none, validate
import host_topology
from iteratortools import first
import logger


class Pdo(collections.namedtuple('Pdo',
                                 ('name', 'wwn', 'model',
                                  'vendor', 'type', 'serial_number',
                                  'driver_version', 'firmware'))):
    def __new__(cls, name, wwn=None, model=None, vendor=None, type=None,
            serial_number=None, driver_version=None, firmware=None):
        return super(Pdo, cls).__new__(cls, name, wwn, model, vendor,
                                       type, serial_number, driver_version,
                                       firmware)


class PortPdo(collections.namedtuple('PortPdo', 'wwn name porttype portindex '
                                                'type trunkedstate '
                                                'symbolicname status state '
                                                'speed scsiport id maxspeed '
                                                'fibertype domainid '
                                                'connectedtowwn')):
    def __new__(cls, wwn, name=None, porttype=None, portindex=None,
                type=None, trunkedstate=None, symbolicname=None,
                status=None, state=None, speed=None, scsiport=None, id=None,
                maxspeed=None, fibertype=None, domainid=None,
                connectedtowwn=None):
        return super(PortPdo, cls).__new__(cls, wwn, name=name, porttype=porttype,
                                       portindex=portindex,
                                       type=type, trunkedstate=trunkedstate,
                                       symbolicname=symbolicname, status=status,
                                       state=state, speed=speed, scsiport=scsiport,
                                       id=id, maxspeed=maxspeed, fibertype=fibertype,
                                       domainid=domainid, connectedtowwn=connectedtowwn)


class LinkReporter:
    def _reportlink(self, citName, end1, end2):
        r""" Creates an C{ObjectStateHolder} class that represents a link.
        The link must be a valid link according to the class model.
        @types: str, ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder
          @param citName: the name of the link to create
          @param end1: the I{from} of the link
          @param end2: the I{to} of the link
          @return: a link from end1 to end2 of type className
        """
        assert citName and end1 and end2
        osh = ObjectStateHolder(citName)
        osh.setAttribute("link_end1", end1)
        osh.setAttribute("link_end2", end2)
        return osh

    @validate(not_none, not_none)
    def containment(self, who, whom):
        return self._reportlink('containment', who, whom)

    @validate(not_none, not_none)
    def fcconnect(self, end1, end2):
        return self._reportlink('fcconnect', end1, end2)


class Builder(object):
    CIT = 'fchba'

    def build(self, fchba_pdo):
        osh = ObjectStateHolder(self.CIT)
        osh.setAttribute('name', fchba_pdo.name)
        osh.setAttribute('fchba_wwn', fchba_pdo.wwn)
        if fchba_pdo.model:
            osh.setAttribute('fchba_model', fchba_pdo.model)
        if fchba_pdo.vendor:
            osh.setAttribute('fchba_vendor', fchba_pdo.vendor)
        if fchba_pdo.type:
            osh.setAttribute('fchba_type', fchba_pdo.type)
        if fchba_pdo.serial_number:
            osh.setAttribute('serial_number', fchba_pdo.serial_number)
        if fchba_pdo.driver_version:
            osh.setAttribute('fchba_driverversion', fchba_pdo.driver_version)
        if fchba_pdo.firmware:
            osh.setAttribute('fchba_firmware', fchba_pdo.firmware)
        return osh

PORT_TYPES = {
    "active": 1,
    "inactive": 2,
    "backbone": 3,
    "enduser": 4,
    "unknown": 5
}

class PortBuilder(object):
    CIT = 'fcport'

    def build(self, fcportpdo):
        osh = ObjectStateHolder(self.CIT)
        osh.setAttribute('fcport_wwn', fcportpdo.wwn)
        if fcportpdo.name is not None:
            osh.setAttribute('name', unicode(fcportpdo.name))

        if fcportpdo.porttype:
            if isinstance(fcportpdo.porttype, int):
                osh.setEnumAttribute('port_type', fcportpdo.porttype)
            else:
                osh.setEnumAttribute('port_type', PORT_TYPES.get(fcportpdo.porttype, 5))

        if fcportpdo.portindex is not None:
            osh.setAttribute('port_index', fcportpdo.portindex)
        if fcportpdo.type:
            osh.setAttribute('fcport_type', fcportpdo.type)
        if fcportpdo.trunkedstate:
            osh.setAttribute('fcport_trunkedstate', fcportpdo.trunkedstate)
        if fcportpdo.symbolicname:
            osh.setAttribute('fcport_symbolicname', fcportpdo.symbolicname)
        if fcportpdo.status:
            osh.setAttribute('fcport_status', fcportpdo.status)
        if fcportpdo.state:
            osh.setAttribute('fcport_state', fcportpdo.state)
        if fcportpdo.speed is not None:
            osh.setAttribute('fcport_speed', fcportpdo.speed)
        if fcportpdo.scsiport:
            osh.setAttribute('fcport_scsiport', fcportpdo.scsiport)
        if fcportpdo.id is not None:
            osh.setAttribute('fcport_portid', fcportpdo.id)
        if fcportpdo.maxspeed:
            osh.setAttribute('fcport_maxspeed', fcportpdo.maxspeed)
        if fcportpdo.fibertype:
            osh.setAttribute('fcport_fibertype', fcportpdo.fibertype)
        if fcportpdo.domainid:
            osh.setAttribute('fcport_domainid', fcportpdo.domainid)
        if fcportpdo.connectedtowwn:
            osh.setAttribute('fcport_connectedtowwn', fcportpdo.connectedtowwn)

        return osh


class PortReporter(object):

    def __init__(self, builder=PortBuilder()):
        self.hbabuilder = builder


class Reporter(object):

    def __init__(self, hbabuilder=Builder(), portbuilder=PortBuilder(),
                 hostreporter=host_topology.Reporter(),
                 linkreporter=LinkReporter()):
        self.hbabuilder = hbabuilder
        self.portbuilder = portbuilder
        self.hostreporter = hostreporter
        self.linkreporter = linkreporter

    def report_fchba_to_fchba(self, fchba_ports_pair, containerosh=None):
        fchbapdo, fcportpdos = fchba_ports_pair
        fcportoshs = []
        oshs = []
        for fcportpdo, target_details in fcportpdos:
            fcportosh, oshs_ = self.report_fcport(fcportpdo, containerosh)
            oshs.extend(oshs_)

            target_fcdetails = []
            for target_fchba_pdo, target_fcport_pdo, target_container_pdo in target_details:
                target_fcportosh = None
                target_fchbaosh = None
                target_containerosh = None
                if target_container_pdo:
                    target_containerosh, _, oshs_ = self.hostreporter.report_host(target_container_pdo)
                    oshs.extend(oshs_)

                if target_fcport_pdo:
                    target_fcportosh, oshs_ = self.report_fcport(target_fcport_pdo,
                                                                 target_containerosh)
                    oshs.extend(oshs_)
                    linkosh = self.linkreporter.fcconnect(fcportosh, target_fcportosh)
                    oshs.append(linkosh)

                if target_fchba_pdo:
                    target_fcportoshs = []
                    if target_fcportosh:
                        target_fcportoshs.append(target_fcportosh)
                    target_fchbaosh, oshs_ = self.report_fc_hba(target_fchba_pdo, target_fcportoshs, target_containerosh)
                    oshs.extend(oshs_)
                target_fcdetails.append((target_fchbaosh, target_fcportosh, target_containerosh))
            fcportoshs.append((fcportosh, tuple(target_fcdetails)))

        fchbaosh, oshs_ = self.report_fc_hba(fchbapdo, imap(first, fcportoshs),
                                             containerosh)
        oshs.extend(oshs_)
        return fchbaosh, fcportoshs, oshs

    def report(self, fchba_ports_pair, containerosh=None):
        fchbapdo, fcportpdos = fchba_ports_pair
        fcportoshs = []
        oshs = []
        for fcportpdo in fcportpdos:
            fcportosh, oshs_ = self.report_fcport(fcportpdo, containerosh)
            fcportoshs.append(fcportosh)
            oshs.extend(oshs_)

        fchbaosh, oshs_ = self.report_fc_hba(fchbapdo, fcportoshs, containerosh)
        oshs.extend(oshs_)
        return fchbaosh, fcportoshs, oshs

    def report_fcport(self, fcportpdo, containerosh=None):
        osh = self.portbuilder.build(fcportpdo)
        if containerosh:
            osh.setContainer(containerosh)

        return osh, (osh, )

    def report_fc_hba(self, fc_hba_pdo, fcportoshs=None, containerosh=None):
        osh = self.hbabuilder.build(fc_hba_pdo)
        oshs = [osh, ]

        if fcportoshs:
            for fcportosh in fcportoshs:
                linkosh = self.linkreporter.containment(osh, fcportosh)
                oshs.append(linkosh)
        if containerosh:
            osh.setContainer(containerosh)

        return osh, oshs
