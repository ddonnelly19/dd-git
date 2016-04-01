#coding=utf-8
'''
Created on Nov 19, 2012

@author: vvitvitskiy
'''
import types
from itertools import imap
from collections import namedtuple

import sap
import ip_addr
import modeling
import fptools
from fptools import partiallyApply as Fn

from java.util import Date

from appilog.common.system.types.vectors import ObjectStateHolderVector


class InstanceBuilder:
    INSTANCE_CIT = 'sap_r3_server'
    PRODUCT_NAME = 'sap_abap_application_server'
    DISCOVERED_PRODUCT_NAME = 'SAP ABAP Application Server'
    SERVER_TYPES = (sap.InstanceBuilder.SAP_APP_SERVER_TYPE,)

    def __init__(self, reportName=True, reportInstName=True):
        self._baseBuilder = sap.InstanceBuilder(reportName, reportInstName)

    _Pdo = namedtuple('Pdo', ('instance', 'sapSystem',
                        'homeDirPath', 'dbLibraryInfo',
                        'codePage', 'numberOfProcesses',
                        'versionInfo', 'startDate',
                        'machineType', 'osInfo',
                        'applicationIp', 'credId', 'connectionClientNr',
                        'isCentral'))

    @staticmethod
    def createPdo(instance, system, homeDirPath=None, dbLibraryInfo=None,
                  codePage=None, numberOfProcesses=None, versionInfo=None,
                  startDate=None, applicationIp=None, machineType=None,
                  osInfo=None, credId=None, connectionClientNr=None,
                  isCentral=None):
        r'''Method take care of PDO input date validation
        @type instance: sap.Instance
        @type system: sap.System
        @type numberOfProcesses: int
        @type versionInfo: sap.VersionInfo
        @type startDate: java.util.Date
        @type applicationIp: ip_addr._BaseIP
        @type isCentral: bool
        '''
        if not instance:
            raise ValueError("Instance is not specified")
        if not system:
            raise ValueError("System is not specified")
        if startDate and not isinstance(startDate, Date):
            raise ValueError("Start date is not of type java.util.Date")
        if (numberOfProcesses is not None
            and not (isinstance(numberOfProcesses, types.IntType)
                     and numberOfProcesses > 0)):
            raise ValueError("Number of processes is not valid")
        if applicationIp and not isinstance(applicationIp, ip_addr._BaseIP):
            raise ValueError("Application IP is of invalid type")
        return InstanceBuilder._Pdo(instance, system, homeDirPath,
                     dbLibraryInfo, codePage, numberOfProcesses,
                     versionInfo, startDate,
                     machineType, osInfo, applicationIp,
                     credId, connectionClientNr, isCentral)

    def updateInstanceNr(self, osh, nr):
        r'@types: osh, str -> osh'
        osh = self._baseBuilder.updateInstanceNr(osh, nr)
        osh.setStringAttribute('instance_number', nr)
        osh.setStringAttribute('instance_nr', nr)
        return osh

    def buildNoNameInstance(self, number, hostname, system, applicationIp=None,
                            codePage=None, versionInfo=None, homeDirPath=None,
                            credId=None):
        r'''
        Build instance without instance name
        @param hostname: is not used if reportName = False
        '''
        osh = self._baseBuilder._buildServer(self.INSTANCE_CIT,
                        number, hostname, system, self.SERVER_TYPES,
                        self.DISCOVERED_PRODUCT_NAME, self.PRODUCT_NAME,
                        applicationIp, codePage, versionInfo,
                        homeDirPath, credId)
        self.updateInstanceNr(osh, number)
        return osh

    def buildInstance(self, pdo):
        r'@types: Pdo -> ObjectStateHolder[sap_r3_server]'
        if not pdo:
            raise ValueError("PDO is not specified")
        osh = self._baseBuilder._buildInstanceBase(self.INSTANCE_CIT,
                        pdo.instance, pdo.sapSystem,
                        serverTypes=self.SERVER_TYPES,
                        discoveredProductName=self.DISCOVERED_PRODUCT_NAME,
                        productName=self.PRODUCT_NAME,
                        applicationIp=pdo.applicationIp,
                        codePage=pdo.codePage,
                        versionInfo=pdo.versionInfo,
                        homeDirPath=pdo.homeDirPath,
                        credId=pdo.credId)
        instance_ = pdo.instance
        osh = self.updateInstanceNr(osh, instance_.getNumber())
        if pdo.osInfo:
            osh.setStringAttribute("os", pdo.osInfo)
        if pdo.machineType:
            osh.setStringAttribute("machine_type", pdo.machineType)
        if pdo.versionInfo:
            versionInfo = pdo.versionInfo
            osh.setStringAttribute('release', versionInfo.release)
            if versionInfo.patchLevel.value():
                osh.setStringAttribute('patch_level', str(versionInfo.patchLevel))
        if pdo.startDate:
            osh.setDateAttribute("start_date", pdo.startDate)
        if pdo.dbLibraryInfo:
            osh.setStringAttribute("db_library", pdo.dbLibraryInfo)
        if pdo.numberOfProcesses is not None:
            osh.setIntegerAttribute("number_processes", pdo.numberOfProcesses)
        if instance_.startPfPath:
            osh.setStringAttribute("start_profile", instance_.startPfPath)
        if pdo.isCentral is not None:
            osh.setBoolAttribute('is_central', pdo.isCentral)
        if pdo.connectionClientNr:
            osh.setStringAttribute('connection_client', pdo.connectionClientNr)
        return osh


class AscsInstanceBuilder:
    INSTANCE_CIT = 'abap_sap_central_services'
    PRODUCT_NAME = 'abap_sap_central_services'
    DISCOVERED_PRODUCT_NAME = 'SAP ABAP Central Services'
    SERVER_TYPES = (sap.InstanceBuilder.SAP_APP_SERVER_TYPE,)

    def __init__(self, reportName=True, reportInstName=True):
        self._baseBuilder = sap.InstanceBuilder(reportName, reportInstName)

    _Pdo = namedtuple('Pdo', ('instance', 'sapSystem',
                        'homeDirPath', 'codePage', 'versionInfo', 'startDate',
                        'applicationIp', 'credId', 'connectionClientNr'))

    @staticmethod
    def createPdo(instance, system, homeDirPath=None, codePage=None,
                  versionInfo=None, startDate=None, applicationIp=None,
                  credId=None, connectionClientNr=None):
        r'''Method take care of PDO input date validation
        @type instance: sap.Instance
        @type system: sap.System
        @type versionInfo: sap.VersionInfo2
        @type startDate: java.util.Date
        @type applicationIp: ip_addr._BaseIP
        '''
        if not instance:
            raise ValueError("Instance is not specified")
        if not system:
            raise ValueError("System is not specified")
        if startDate and not isinstance(startDate, Date):
            raise ValueError("Start date is not of type java.util.Date")
        if applicationIp and not isinstance(applicationIp, ip_addr._BaseIP):
            raise ValueError("Application IP is of invalid type")
        return AscsInstanceBuilder._Pdo(instance, system, homeDirPath,
                     codePage, versionInfo, startDate,
                     applicationIp, credId, connectionClientNr)

    def buildInstance(self, pdo):
        r'@types: Pdo, str, str -> ObjectStateHolder[sap_r3_server]'
        if not pdo:
            raise ValueError("PDO is not specified")
        osh = self._baseBuilder._buildInstanceBase(self.INSTANCE_CIT,
                        pdo.instance, pdo.sapSystem,
                        serverTypes=self.SERVER_TYPES,
                        discoveredProductName=self.DISCOVERED_PRODUCT_NAME,
                        productName=self.PRODUCT_NAME,
                        applicationIp=pdo.applicationIp,
                        codePage=pdo.codePage,
                        versionInfo=pdo.versionInfo,
                        homeDirPath=pdo.homeDirPath,
                        credId=pdo.credId)
        instance_ = pdo.instance
        osh.setStringAttribute('instance_number', instance_.getNumber())
        if pdo.versionInfo:
            versionInfo = pdo.versionInfo
            osh.setStringAttribute('release', versionInfo.release)
            if versionInfo.patchLevel.value():
                osh.setStringAttribute('patch_level', str(versionInfo.patchLevel))
        if pdo.startDate:
            osh.setDateAttribute("start_date", pdo.startDate)
        if instance_.startPfPath:
            osh.setStringAttribute("start_profile", instance_.startPfPath)
        if pdo.connectionClientNr:
            osh.setStringAttribute('connection_client', pdo.connectionClientNr)
        return osh


class InstanceReporter:
    def __init__(self, builder):
        r'@types: InstanceBuilder'
        if not builder:
            raise ValueError("Instance builder is not specified")
        self._builder = builder

    def reportNoNameInst(self, number, hostname, system, containerOsh):
        r'@types: str, str, System, osh -> osh'
        osh = self._builder.buildNoNameInstance(number, hostname, system)
        osh.setContainer(containerOsh)
        return osh

    def reportInstance(self, pdo, containerOsh):
        r'@types: InstanceBuilder._Pdo, ObjectStateHolder -> ObjectStateHolder'
        if not pdo:
            raise ValueError("Instance information is not specified")
        if not containerOsh:
            raise ValueError("Container OSH is not specified")
        osh = self._builder.buildInstance(pdo)
        osh.setContainer(containerOsh)
        return osh


class SoftwareComponentRegistryBuilder:
    r'''Serves to build registry file for all software components installed
    on SAP system.
    Created to provided backward-compatible way of reporting
    '''
    class Registry:
        def __init__(self, components):
            r'@types: list[sap.SoftwareComponent]'
            self.__components = []
            self.__components.extend(filter(None, components))

        def getComponents(self):
            r'@types: -> list[sap.SoftwareComponent]'
            return self.__components[:]

        def __repr__(self):
            return 'Registry(%s)' % len(self.__components)

    def _serializeComponent(self, component):
        r''' Reflects component to ini-like string
        @types: sap.SoftwareComponent -> str'''
        return '\n'.join((
            "name=%s" % component.name or '',
            "type=%s" % component.type or '',
            "description=%s" % component.description or '',
            "version=%s" % (component.versionInfo
                           and component.versionInfo.composeDescription()
                           or '')))

    def _serializeComponents(self, components):
        separator = '-' * 10
        serializedCmps = imap(self._serializeComponent, components)
        return ('\n%s\n' % separator).join(serializedCmps)

    def buildRegistry(self, checkConnectionRegistry):
        r'@types: Registry -> ObjectStateHolder[configfile]'
        configurationContent = self._serializeComponents(checkConnectionRegistry.getComponents())
        return modeling.createConfigurationDocumentOSH(
                    'software_components.txt',
                    '<sap database>',
                    configurationContent,
                    contentType=modeling.MIME_TEXT_PLAIN,
                    description='List of software components')


def reportSoftwareCmps(cmps, containerOsh, reportAsConfigFileEnabled=False):
    r'@types: list[sap.SoftwareComponent], osh, bool -> oshv'
    reportFn = (reportAsConfigFileEnabled
                and reportSoftwareCmpsAsConfigFile
                or  reportSoftwareCmpsAsCis)
    return reportFn(cmps, containerOsh)


def reportSoftwareCmpsAsConfigFile(cmps, containerOsh):
    r'@types: list[sap.SoftwareComponent], osh -> oshv'
    registryBuilder = SoftwareComponentRegistryBuilder()
    registry = SoftwareComponentRegistryBuilder.Registry(cmps)
    fileOsh = registryBuilder.buildRegistry(registry)
    fileOsh.setContainer(containerOsh)
    vector = ObjectStateHolderVector()
    vector.add(fileOsh)
    return vector


def reportSoftwareCmpsAsCis(cmps, containerOsh):
    r'@types: list[sap.SoftwareComponent], osh -> oshv'
    builder = sap.SoftwareComponentBuilder()
    reporter = sap.SoftwareComponentReporter(builder)
    report = Fn(reporter.reportSoftwareComponent, fptools._, containerOsh)
    vector = ObjectStateHolderVector()
    fptools.each(vector.add, imap(report, cmps))
    return vector


def isCentralInstance(instance):
    r'''Check whether instance is central based on naming conventions
    @types: sap.Instance -> bool
    @deprecated: It is not enough only to check for 'DVEBMGS' substring.
    The making decision algorithm is much more complicated and yet to be
    implemented'''
    return instance.name.startswith('DVEBMGS')


def isCentralServicesInstance(instance):
    r'''Check whether instance is central services instance based on naming
    conventions
    @types: sap.Instance -> bool'''
    return instance.name.startswith('ASCS')


def report_system(system_name, instance_number, ip_address,
                  application_ip=None, cred_id=None):
    oshs = []
    system = sap.System(system_name)
    system_osh = sap.Builder().buildSapSystem(system)
    instance_osh = InstanceBuilder(
                     reportName=False,
                     reportInstName=False
                ).buildNoNameInstance(
                     instance_number,
                     None,
                     system,
                     applicationIp=application_ip,
                     credId=cred_id
                )
    host_osh = modeling.createHostOSH(ip_address)
    instance_osh.setContainer(host_osh)
    oshs.append(system_osh)
    oshs.append(instance_osh)
    linkReporter = sap.LinkReporter(sap.LinkBuilder())
    oshs.append(linkReporter.reportMembership(system_osh, instance_osh))
    return system_osh, oshs

