#coding=utf-8
import sys

import logger
import errormessages
import errorcodes
import errorobject
import modeling

import process
import process_discoverer

from java.lang import Boolean


import applications
import Dis_TCP
import snmp_dis_user_lib
import snmp_dis_software_lib
import snmp_dis_service_lib
import snmp_dis_process_lib
import snmp_dis_disk_lib

from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.library.execution import ExecutionFramework
import flow

class StatisticsFramework(ExecutionFramework):
    r''''Used to monitor actions of Framework object
    For instance, track statistics how many CIs were sent to the uCMDB using
    methods sendObject and sendObjects.
    '''
    def __init__(self, framework):
        self.__framework = framework
        self.__sentObjectStatistic = {}

    def __getattr__(self, name):
        return getattr(self.__framework, name)

    def __count(self, osh):
        cit = osh.getObjectClass()
        count = self.__sentObjectStatistic.get(cit) or 0
        self.__sentObjectStatistic[cit] = count + 1

    def sendObject(self, osh):
        self.__count(osh)
        self.__framework.sendObject(osh)

    def sendObjects(self, vector):
        it = vector.iterator()
        while it.hasNext():
            self.__count(it.next())
        self.__framework.sendObjects(vector)

    def getParameter(self, name, defaultValue = None):
        r'@types: str, any -> str or any'
        return self.__framework.getParameter(name) or defaultValue

    def getSentObjectsCount(self):
        return len(self.__sentObjectStatistic)

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    client = None
    framework = StatisticsFramework(Framework)
    try:
        try:
            client = framework.createClient()
        except:
#            No need to report twice, exception msg is sufficient
#            errobj = errorobject.createError(errorcodes.CONNECTION_FAILED_NO_PROTOCOL, None, 'Connection failed')
#            logger.reportErrorObject(errobj)
            errMsg ='Exception while creating %s client: %s' % (ClientsConsts.SNMP_PROTOCOL_NAME, sys.exc_info()[1])
            errormessages.resolveAndReport(str(sys.exc_info()[1]), ClientsConsts.SNMP_PROTOCOL_NAME, framework)
            logger.debugException(errMsg)
        else:

            config = (flow.DiscoveryConfigBuilder(framework)
                      .dest_data_required_params_as_str('ip_address')
                      .dest_data_params_as_list('host_ips')
                      ).build()
            ipaddress = config.ip_address
            host_ips = filter(None, config.host_ips)

            ips = set(host_ips)
            ips.add(ipaddress)

            hostId = framework.getDestinationAttribute('hostId')
            hostOsh = modeling.createOshByCmdbIdString('host', hostId)

            discoverUsers = Boolean.parseBoolean(framework.getParameter('discoverUsers'))
            if discoverUsers:
                logger.debug('Starting to discover users')
                try:
                    snmp_dis_user_lib.doQueryOSUsers(client, OSHVResult)
                except:
                    errobj = errorobject.createError(errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['users', 'snmp'], 'Failed to discover users by snmp')
                    logger.reportWarningObject(errobj)
                    logger.errorException('Failed to discover users by snmp')


            discoverDisks = Boolean.parseBoolean(framework.getParameter('discoverDisks'))
            if discoverDisks:
                logger.debug('Starting to discover disks')
                try:
                    snmp_dis_disk_lib.doQueryDisks(client, OSHVResult)
                except:
                    errobj = errorobject.createError(errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['disks', 'snmp'], 'Failed to discover disks by snmp')
                    logger.reportWarningObject(errobj)
                    logger.errorException('Failed to discover disks by snmp')


            discoverProcesses = Boolean.parseBoolean(framework.getParameter('discoverProcesses'))
            processes = []

            logger.debug('Starting to discover processes')
            try:

                processDiscoverer = process_discoverer.getDiscovererBySnmp(client)
                processes = processDiscoverer.discoverAllProcesses()
                if not processes:
                    raise ValueError()
            except:
                errobj = errorobject.createError(errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['processes', 'snmp'], 'Failed to discover processes by snmp')
                logger.reportWarningObject(errobj)
                logger.errorException('Failed to discover processes by snmp')

            if processes:

                # save processes to DB
                process_discoverer.saveProcessesToProbeDb(processes, hostId, framework)

                # report processes
                if discoverProcesses:
                    processReporter = process.Reporter()
                    for processObject in processes:
                        processesVector = processReporter.reportProcess(hostOsh, processObject)
                        OSHVResult.addAll(processesVector)


            discoverServices = Boolean.parseBoolean(framework.getParameter('discoverServices'))
            if discoverServices:
                logger.debug('Starting to discover services')
                try:
                    snmp_dis_service_lib.doQuerySNMPService(client, OSHVResult)
                except:
                    errobj = errorobject.createError(errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['services', 'snmp'], 'Failed to discover services by snmp')
                    logger.reportWarningObject(errobj)
                    logger.errorException('Failed to discover services by snmp')


            discoverSoftware = Boolean.parseBoolean(framework.getParameter('discoverInstalledSoftware'))
            if discoverSoftware:
                logger.debug('Starting to discover software')
                try:
                    snmp_dis_software_lib.doQuerySoftware(client, OSHVResult)
                except:
                    errobj = errorobject.createError(errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['software', 'snmp'], 'Failed to discover software by snmp')
                    logger.reportWarningObject(errobj)
                    logger.errorException('Failed to discover software by snmp')

            connectivityEndPoints = []
            try:
                tcpDiscoverer = Dis_TCP.TCPDisBySNMP(client, framework, ips=tuple(ips))
                if tcpDiscoverer is not None:
                    tcpDiscoverer.discoverTCP()
                    connectivityEndPoints = tcpDiscoverer.getProcessEndPoints()
            except:
                errorMessage = 'Failed to run tcp discovery by snmp'
                logger.debugException(errorMessage)
                errobj = errorobject.createError(errorcodes.FAILED_RUNNING_DISCOVERY_WITH_CLIENT_TYPE, ['tcp', 'snmp'], errorMessage)
                logger.reportWarningObject(errobj)

            if processes:
                appSign = applications.createApplicationSignature(framework, client)
                appSign.setProcessesManager(applications.ProcessesManager(processes, connectivityEndPoints))
                appSign.getApplicationsTopology(hostId)

            discoverModules = Boolean.parseBoolean(framework.getParameter('discoverModules'))
            if discoverModules:
                logger.debug('Begin discover snmp modules...')
                try:
                    from snmp_model_finder import SnmpStateHolder
                    from snmp_model_finder import SnmpQueryHelper
                    from snmp_model_finder import ModelTypeMatcher
                    import snmp_model_discovery

                    snmpStateHolder = SnmpStateHolder()
                    cacheClient = None
                    # from discovery.client.snmp import SnmpClientCacheProxy

                    # cacheClient = SnmpClientCacheProxy(client, 'cache/'+ipaddress+'.cache')
                    snmpQueryHelper = SnmpQueryHelper(client)
                    mtm = ModelTypeMatcher(snmpStateHolder, snmpQueryHelper)
                    logger.debug('The target is matched:', mtm.match())
                    logger.debug('The type of the target is:', snmpStateHolder.getTypes())
                    vector = snmp_model_discovery.discoverAll(hostOsh, snmpStateHolder, snmpQueryHelper)
                    logger.debug('Discovered CI count:', vector.size())
                    OSHVResult.addAll(vector)
                    if cacheClient:
                        cacheClient.writeCache()
                except:
                    errobj = errorobject.createError(errorcodes.FAILED_DISCOVERING_RESOURCE_WITH_CLIENT_TYPE, ['modules', 'snmp'],
                                                     'Failed to discover modules by snmp')
                    logger.reportWarningObject(errobj)
                    logger.errorException('Failed to discover modules by snmp')
                logger.debug('End discover snmp modules')

    finally:
        if client != None:
            client.close()
    if OSHVResult.size() == 0 and framework.getSentObjectsCount() == 0:
        logger.reportWarning('SNMP: No data collected')
    return OSHVResult
