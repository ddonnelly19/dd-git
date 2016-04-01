import logger
import modeling
import errormessages
from ivm import TopologyReporter
from ivm_discoverer import isIvmSystem, VirtualServerDiscoverer, IvmHypervisorDiscoverer
from shellutils import ShellUtils

from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.lang import Exception as JavaException

##########################################################
## Function to discover IVM topology
##########################################################
def discoverIvmTopology(shell, hostId, reportHostName):
    vector = ObjectStateHolderVector()
    hypervisor = IvmHypervisorDiscoverer(shell).discover()
    virtual_servers = VirtualServerDiscoverer(shell).discover()
    
    ivmHostOsh = modeling.createOshByCmdbId("host_node", hostId)
    vector.add(ivmHostOsh)
    
    vector.addAll(TopologyReporter().report(ivmHostOsh, hypervisor, virtual_servers, reportHostName))
    
    return vector

##########################################################
## Main function block
##########################################################
def DiscoveryMain(Framework):
    protocol = Framework.getDestinationAttribute('Protocol')
    protocolName = errormessages.protocolNames.get(protocol) or protocol
    hostId = Framework.getDestinationAttribute('hostId')
    reportHostName = Framework.getParameter('reportHostNameAsVmName')
    
    vector = ObjectStateHolderVector()
    try:
        client = Framework.createClient()
        try:
            shell = ShellUtils(client)

            if isIvmSystem(shell):
                vector.addAll(discoverIvmTopology(shell, hostId, reportHostName))
            else:
                Framework.reportWarning("The destination host is not a part of HP IVM system")
        finally:
            client.close()
    except JavaException, ex:
        strException = ex.getMessage()
        logger.debugException('')
        errormessages.resolveAndReport(strException, protocolName, Framework)
    except Exception, ex:
        logger.debugException('')
        errormessages.resolveAndReport(str(ex), protocolName, Framework)

    return vector