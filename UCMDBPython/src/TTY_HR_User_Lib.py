#coding=utf-8
import modeling
import re
import logger

from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from java.lang import Long
from hostresource_win_wmi import UserDiscoverer
from hostresource import HostResourceDiscoveryException
from wmiutils import WmicProvider

def makeUserOSH(hostCmdbId, userName, desc, uid, gid, homeDir):
    'host OSH, str, str, str, str, str -> OSH vector'
    iuid = -1
    igid = -1
    try:
        iuid = Long(uid)
    except:
        iuid = -1

    try:
        igid = Long(gid)
    except:
        igid = -1

    myVec = ObjectStateHolderVector()

    u_obj = ObjectStateHolder('osuser')
    host_objSH = modeling.createOshByCmdbIdString('host', hostCmdbId)
    u_obj.setContainer(host_objSH)

    u_obj.setAttribute('data_name', userName)
    if(len(uid) > 0):
        u_obj.setAttribute('user_id', Long(iuid))
    if(len(gid) > 0):
        u_obj.setAttribute('group_id', Long(igid))
    if(len(desc) > 0):
        u_obj.setAttribute('data_note', desc)
    if(len(homeDir) > 0):
        u_obj.setAttribute('homedir', homeDir)
    myVec.add(u_obj)

    return(myVec)


def disGenericUNIX(hostCmdbId, shell):
    'str, UnixShell -> OSH vector'
    logger.debug('Discover users')
    myVec = ObjectStateHolderVector()

    r = shell.safecat('/etc/passwd')
    if r == None:
        return myVec

    lines = ''
    if(re.search('\r\n',r)):
        lines = r.split('\r\n')
    elif (re.search('\n',r)):
        lines = r.split('\n')
    else:
        return myVec
    for line in lines:
        if(re.match('#',line)):
            continue
        token=line.split(':')
        if(len(token) == 7):
            myVec.addAll(makeUserOSH(hostCmdbId, token[0], token[4], token[2], token[3], token[5]))
    return myVec

def _getDomainName(wmiProvider):
    ''' wmiProvider -> str or None
    @command: select Name from Win32_ComputerSystem
    @return: domain name in upper case or None
    @raise Exception: if WMI query failed
    TODO: move to appropriate discoverer (by WMI)
    '''
    queryBuilder = wmiProvider.getBuilder('Win32_ComputerSystem').addWmiObjectProperties('Name')
    systems = wmiProvider.getAgent().getWmiData(queryBuilder, timeout = 60000)
    if systems:
        return systems[0].Name.upper()

def disWinOs(hostOsh, shell):
    ''' ObjectStateHolder, ShellUtils -> ObjectStateHolderVector
    @raise HostResourceDiscoveryException if discovery failed
    @deprecated: use hostresources_win_wmi instead
    '''
    wmiProvider = WmicProvider(shell)
    try:
        domainName = _getDomainName(wmiProvider)
    except Exception, e:
        logger.debug(str(e))
        raise HostResourceDiscoveryException, "Failed to get host domain name. %s" % e
    else:
        userResources = UserDiscoverer(wmiProvider).discoverByDomain(domainName)
        userResources.build(hostOsh)
        return userResources.report()
