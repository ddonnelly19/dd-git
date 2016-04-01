# coding=utf-8
import re
import os
import logger
import modeling
import errormessages
import InventoryUtils
import netutils

from java.util import Properties
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.probe.agents.probemgr.udastatus import UdaState
from com.hp.ucmdb.discovery.probe.agents.probemgr.udastatus import UdaStatusService
from java.util import UUID
from java.util import HashMap

def DiscoveryMain(Framework):
    properties = Properties()
    vector = ObjectStateHolderVector()
    properties.setProperty('timeoutDiscover', Framework.getParameter('timeoutDiscover'))
    properties.setProperty('retryDiscover', Framework.getParameter('retryDiscover'))
    properties.setProperty('pingProtocol', Framework.getParameter('pingProtocol'))
    properties.setProperty('threadPoolSize', Framework.getParameter('threadPoolSize'))
    ip =  Framework.getDestinationAttribute('ip_address')
    domainName = Framework.getDestinationAttribute('domain_name')
    id =  Framework.getTriggerCIData('id')
    ports = getUDAAvailablePorts(Framework)

    try:
        client = Framework.createClient(ClientsConsts.ICMP_PROTOCOL_NAME, properties)
        try:
            range_uda_status = {}
            range_result = pingIPsInRange(Framework, client, ip, ports)
            range_uda_status.update(range_result)

            for x in range_uda_status.values():
                logger.debug(x)
                #build the udaStatus
                context = UdaState.Builder(x.ip).computerName(x.computerName).alive(x.alive).portAlive(x.portAlive).isDDMI( x.isDDMI).isNative(x.isNative).isWin(x.isWin).osType(x.osType).agentVersion( str(x.agentVersion) + ('-fips' if x.isFIPSEnabled else '') ).UDUniqueId(x.UDUniqueId).build()
                #save
                UdaStatusService.getInstance().saveUdaStatus(context)
                if Framework.getParameter('isCreateUDA') == 'true':
                    if x.UDUniqueId:
                        hostOsh = modeling.createHostOSH(x.ip)
                        hostOsh.setStringAttribute(InventoryUtils.ATTR_UD_UNIQUE_ID, x.UDUniqueId)
                        uda = ObjectStateHolder('uda')
                        uda.setStringAttribute('application_ip', x.ip)
                        uda.setStringAttribute('application_ip_domain', domainName)
                        uda.setStringAttribute('discovered_product_name', 'uda')
                        uda.setStringAttribute('version', str(x.agentVersion))
                        uda.setContainer(hostOsh)
                        vector.add(hostOsh)
                        vector.add(uda)
        finally:
            client.close()
    except:
        msg = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(msg, ClientsConsts.ICMP_PROTOCOL_NAME, Framework)
    return vector


def pingIPsInRange(Framework, client, ip, ports):
    logger.debug("=====Start working on ip ", ip)

    result_for_range = {}
    batch = [ip]
    batch.append(ip)
    aliveIPs = client.executePing(batch)

    # logger.debug("Alive IPs:", aliveIPs)
    if ip in aliveIPs:
        logger.debug("Begin working on alive IP:%s" % ip)
        us = workOnIP(Framework, ip, ports)
        result_for_range[ip] = us
    else:
        result_for_range[ip] = UDAStatus(ip)
    return result_for_range


class UDAStatus:
    def __init__(self, ip):
        self.ip = ip
        self.alive = False
        self.portAlive = False
        self.udaAlive = False
        self.isNative = False
        self.isDDMI = False
        self.isWin = False
        self.agentVersion = False
        self.osType = None
        self.UDUniqueId = None
        self.computerName = None
        self.mac = None
        self.user = None
        self.isFIPSEnabled = False

def __repr__(self):
    return '{ip:%s, alive:%s, portAlive:%s, udaConnected:%s, isDDMI:%s, isNative:%s, osType:%s, agentVersion:%s, computerName:%s,ud unique id:%s,mac:%s}' % (
        self.ip, self.alive, self.portAlive, self.udaAlive, self.isDDMI, self.isNative, self.osType,
        self.agentVersion, self.computerName, self.UDUniqueId, self.mac)

#detect the hostname with ping command
def detectHostnameWithPing(ip):
    indexStr = '['+ ip +']'
    tmp = os.popen('ping -a ' + ip + ' -n 1').readlines()
    if tmp:
        ret = tmp[1].split(' ')
        if (indexStr == ret[2]):
            return ret[1]
    return None


def detectFIPSMode(client):
    logger.debug('Start detect FIPS mode...')
    fips = client.getOptionsMap().get('FIPS')
    result = bool(fips and fips.strip().lower() == 'on')
    logger.debug('UDA FIPS enabled:', result)
    return result


def getUDAAvailablePorts(Framework):
    '''
    Get all available ports of UD protocol
    :param Framework:
    :return: array of available ports, if it's not configured, just return [2738, 7738]
    '''

    logger.debug("Start to get all ports of UD protocol")
    credentialIds = netutils.getAvailableProtocols(Framework, ClientsConsts.DDM_AGENT_PROTOCOL_NAME, None)
    ports = set([2738, 7738])
    for credentialId in credentialIds:
        protocolPort = Framework.getProtocolProperty(credentialId, CollectorsConstants.PROTOCOL_ATTRIBUTE_PORT, 'NA')
        if protocolPort is not None:
            ports.add( int(protocolPort) )

    logger.debug("All ports of UD protocol: ", ports)

    return ports


def workOnIP(Framework, ip, ports):
    OPTION_UD_UNIQUE_ID = "UD_UNIQUE_ID"
    us = UDAStatus(ip)
    us.alive = True
    alivePort = None
    logger.debug("IP %s alive:%s" % (ip, us.alive))
    if us.alive:
        for port in ports:
            us.portAlive = detectPortAvailable(ip, port)
            if us.portAlive:
                alivePort = port
                break

        logger.debug("Port alive %s on IP:Port %s:%s" % (us.portAlive, us.ip, str(alivePort) ))
        #set computerName by ping -a
        us.computerName = detectHostnameWithPing(ip)
        if us.portAlive:
            client = detectUDAAvailable(Framework, ip)
            if client:
                us.udaAlive = True
                logger.debug("UDA alive %s on IP %s" % (us.udaAlive, us.ip))
                try:
                    us.isDDMI = detectDDMIAgent(Framework, client, us)
                    logger.debug("UDA is DDMI %s on IP %s" % (us.isDDMI, us.ip))
                    if not us.isDDMI:
                        us.isNative = True #detectUDANative(Framework, client, us)
                        logger.debug("UDA is native %s on IP %s" % (us.isNative, us.ip))
                        us.isFIPSEnabled = detectFIPSMode(client)

                        if isDupUDUniqueId(us.UDUniqueId):
                            logger.debug("old uuid ", us.UDUniqueId)
                            uduid = UUID.randomUUID()
                            logger.debug("generate new uuid ", uduid)
                            options = HashMap()
                            options.put(OPTION_UD_UNIQUE_ID, str(uduid))
                            client.setOptionsMap(options)
                            clientOptions = client.getOptionsMap()
                            uduid = clientOptions.get(OPTION_UD_UNIQUE_ID)
                            logger.debug("get new uuid ", uduid)
                            us.UDUniqueId = uduid


                except:
                    msg = logger.prepareJythonStackTrace('')
                    errormessages.resolveAndReport(msg, ClientsConsts.ICMP_PROTOCOL_NAME, Framework)
                    pass
                finally:
                    try:
                        client.close()
                    except:
                        pass
    return us


def detectPortAvailable(ip, port=2738, timeout=3000):
    import netutils

    return bool(netutils.checkTcpConnectivity(ip, port, timeout))


def detectUDAAvailable(Framework, ip, credentialId=None):

    logger.debug("Start to detect UDA availability")
    if credentialId:
        credentialIds = [credentialId]
    else:
        import netutils

        credentialIds = netutils.getAvailableProtocols(Framework, ClientsConsts.DDM_AGENT_PROTOCOL_NAME, ip)

    props = Properties()
    props.setProperty('permitDDMi', 'true')
    props.setProperty(CollectorsConstants.DESTINATION_DATA_IP_ADDRESS, ip)
    for credentialId in credentialIds:
        props.setProperty(CollectorsConstants.ATTR_CREDENTIALS_ID, credentialId)
        try:
            logger.debug("Start to connect UDA")
            client = Framework.createClient(props)
            if client:
                return client
        except:
            pass
    return None

def detectDDMIAgent(Framework, client, us):
    '''
    @param Framework:
    @param client:
    @param us:
    @type us UDAStatus
    @return:
    '''
    agentVersion = client.getVersion()
    sysInfo = client.getSysInfo()
    from distutils.version import LooseVersion
    logger.debug("sysinfo ----", sysInfo)
    us.agentVersion = agentVersion
    us.osType = sysInfo.get('osType')
    #check computerName
    if (us.computerName == None):
        us.computerName = sysInfo.get('computerName')
    us.mac = sysInfo.get('macAddress')
    us.isWin = us.osType == 'WinNT'
    us.UDUniqueId = client.getOptionsMap().get('UD_UNIQUE_ID')
    return LooseVersion(agentVersion) < LooseVersion("v10.0")


def detectUDANative(Framework, client, us):
    if us.isWin:
        logger.debug("The host is Windows.")
        return True
    us.user = client.executeCmd('whoami')
    localPath = getIsNativeCmdLocalFilePath()
    basedir = '$HOME/.discagnt/'
    output = client.executeCmd('echo %s' % basedir)
    output = output and output.strip()
    if output:
        basedir = output
    else:
        logger.debug("Cannot get base dir for %s" % basedir)
        return False
    remotePath = '%sagentinstall.sh' % basedir
    isNativeCmd = '%s --isnative 2>/dev/null' % remotePath
    if client.uploadFile(localPath, remotePath, 1) == 0:
        isNative = client.executeCmd(isNativeCmd)
        isNative = isNative and isNative.strip()
        return isNative == 'true'
    return False


def getIsNativeCmdLocalFilePath():
    import os

    fileName = 'agentinstall.sh '
    return os.path.join(CollectorsParameters.PROBE_MGR_RESOURCES_DIR, 'ud_agents', fileName)


def isDupUDUniqueId(uuid):
    uuid_list = []

    if uuid in uuid_list:
        logger.debug("found duplicated uuid")
        return True
    else:
        logger.debug("didn't find duplicated uuid")
        return False

