#coding=utf-8
import re
import sys

import logger
import modeling
import shellutils
import errormessages
import layer2
import layer2_shell_discoverer

from TTY_Connection_Utils import NexusDiscoverer

from java.lang import Exception as JException
from appilog.common.system.types.vectors import ObjectStateHolderVector


def parsePorts(interfaces):
    results = {}
    if not interfaces:
        return results
    for interface in interfaces:
        try:
            port_name= interface.getName()
            logger.debug(port_name)
            port_index = int( ''.join(re.findall('(\d+)', port_name)) )
            m = re.search('(\d+)/(\d+)', port_name)
            port_slot = m and m.group(1)
            results[port_name] = layer2.Port(port_index, port_name, port_slot)
        except:
            logger.debugException('')
    return results


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    shell = None
    protocol = Framework.getDestinationAttribute('Protocol')
    switchId = Framework.getDestinationAttribute('hostId')
    print "Switch id %s" % switchId
    errorMessage = None
    try:
        client = Framework.createClient()
        try:
            shellFactory = shellutils.ShellFactory()
            shell = shellFactory.createShell(client)
            switchOsh = modeling.createOshByCmdbId('switch', switchId)
            discoverer = NexusDiscoverer(Framework, shell, '', '', '', '')
            discoverer.discoverInterfacesAndIps()
            interfaces_dict = discoverer.hostDataObject.interfaces
            ports_map = parsePorts(interfaces_dict.values())
            vlan_discoverer = layer2_shell_discoverer.VlanDiscoverer(shell)
            vlans = vlan_discoverer.discoverVlans()

            layer2_discoverer = layer2_shell_discoverer.Layer2Discoverer(shell)
            remote_peers_map = layer2_discoverer.discover()

            OSHVResult.addAll(layer2.reportTopology(switchOsh, interfaces_dict, vlans, remote_peers_map, ports_map))
            
        finally:
            try:
                shell and shell.closeClient()
            except:
                logger.debugException('')
                logger.error('Unable to close shell')
    except JException, ex:
        errorMessage = ex.getMessage()
    except:
        errorObject = sys.exc_info()[1]
        if errorObject:
            errorMessage = str(errorObject)
        else:
            errorMessage = logger.prepareFullStackTrace('')

    if errorMessage:
        logger.debugException(errorMessage)
        errormessages.resolveAndReport(errorMessage, protocol, Framework)
        
    return OSHVResult
