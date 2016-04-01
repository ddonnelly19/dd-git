#coding=utf-8
from active_directory_utils import AdDomainControllerDiscoverer, \
    LdapEnvironmentBuilder, LdapDaoService
from appilog.common.system.types.vectors import ObjectStateHolderVector
import errorcodes
import errorobject
import logger
import modeling
import errormessages
import active_directory_utils


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    hostIp = Framework.getDestinationAttribute('ip_address')
    hostIdString = Framework.getDestinationAttribute('hostId')
    ports = Framework.getTriggerCIDataAsList('port_number')
    '''
    Retrieving a list of LDAP ports we strive to connect to domain controller in
    member role first. So we have to choose the lowest port number in the list.
    '''
    if ports:
        ports = map(lambda port: int(port), ports)
        ports.sort()
    else:
        raise Exception("No LDAP ports provided to connect")

    protocol = "ldap"
    credentialIds = Framework.getAvailableProtocols(hostIp, protocol)
    client = None
    warningList = []

    defiscoveryPassed = 0
    connectedOnce = 0

    if not len(credentialIds):
        msg = 'Protocol not defined or IP out of protocol network range'
        Framework.reportError(msg)
    else:#go over all protocols and for each protocol try all available ports
        for credentialsId in credentialIds:
            portsToIterate = None
            protocolPort = Framework.getProtocolProperty(credentialsId, "protocol_port")
            if str(protocolPort).isdigit():
                portsToIterate =[protocolPort]
            else:
                portsToIterate = ports
            for port in portsToIterate:
                try:# build environment and connect
                    try:
                        envBuilder = LdapEnvironmentBuilder(port)
                        client = Framework.createClient(credentialsId, envBuilder.build())
                        connectedOnce = 1
                        baseDn = active_directory_utils.getBaseDnFromJobsParameters(Framework)
                        daoService = LdapDaoService(client, baseDn)
                        # discover domain controller
                        warningList = []
                        hostOsh = modeling.createOshByCmdbIdString('host', hostIdString)
                        discoverer = AdDomainControllerDiscoverer(daoService, hostOsh)
                        OSHVResult = discoverer.discover()
                        #add container hosts for domain controllers to the result vector
                        containerOshs = discoverer.getResult().getContainerOshMap().values()
                        for osh in containerOshs:
                            OSHVResult.add(osh)
                        #skip other ports
                        defiscoveryPassed = 1
                        break
                    except:
                        msg = logger.prepareFullStackTrace('')
                        warning = errormessages.resolveError(msg, protocol)
                        warningList.append(warning)
                finally:
                    client and client.close()
            #skip other protocols in case when discovery passed for current one
            if defiscoveryPassed:
                break

    if not connectedOnce:
        warning = errorobject.createError(errorcodes.CONNECTION_FAILED_NO_PROTOCOL_WITH_DETAILS,
                                         ['Tried all protocols']*2,
                                          'Failed to connect using all protocols')
        warningList = [warning]

    #print collected warning message
    for warning in warningList:
        logger.reportWarningObject(warning)

    return OSHVResult
