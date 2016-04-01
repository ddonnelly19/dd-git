'''
Created on 25-07-2006

@author: Ralf Schulz, Asi Garty, Ivan Yani, Vladimir Vitvitskiy
'''
# coding=utf-8
import logger
import modeling
import errormessages
import re
# Java imports
from java.util import Properties
from java.lang import Exception as JavaException

# MAM specific imports
from com.hp.ucmdb.discovery.library.clients.agents import AgentConstants
from hostresource_win_wmi import Win2008SoftwareDiscoverer, Win8_2012SoftwareDiscoverer, SoftwareDiscoverer
from wmiutils import WmiAgentProvider
from host_win_wmi import WmiHostDiscoverer
import hostresource


def getRegValues(wmiClient, keyPath, subKeyName):
    '''
    This function queries the registry by a defined filter, using the given credentials
    '''
    result = {}
    table = wmiClient.getRegistryKeyValues(keyPath, 1, subKeyName)
    keys = table.get(0)
    values = table.get(1)
    for i in range(keys.size()):
        key = keys.get(i)
        end = key.find('\\' + subKeyName)
        key = key[0:end]
        #result.put(key,values.get(i))
        result.update({key: values.get(i)})
    return result


def parseProductCode(key):
    try:
        m = re.match(r".*\\Uninstall\\[\{\[\( ]*([\dabcdefABCDEF]{8}(\-[\dabcdefABCDEF]{4}){3}-[\dabcdefABCDEF]{12}).*", key)
        if (m):
            return m.group(1).strip()
    except:
        logger.warn('Error parsing Software Product Code')


# This function creates the software objects
def _createSoftware(names, paths, displayVersions, publishers, productIds,
                   installDates,
                   hostOSH, OSHVResult, softNameToInstSoftOSH=None):
    nameKeys = names.keys()
    for name in nameKeys:
        path = paths.get(name)
        displayVersion = displayVersions.get(name)
        publisher = publishers.get(name)
        productId = productIds.get(name)
        productCode = parseProductCode(name)
        installDate = installDates.get(name)
        softName = names.get(name)
        if softName:
            softwareOSH = hostresource.createSoftwareOSH(
                    hostOSH, softName, path=path,
                    displayVersion=displayVersion, publisher=publisher,
                    productId=productId, productCode=productCode,
                    installDate=installDate)
            OSHVResult.add(softwareOSH)
            if softNameToInstSoftOSH != None:
                softNameToInstSoftOSH[softName.strip()] = softwareOSH
        else:
            logger.debug('software: ', softName, ' already reported or has no Name')


def getRegistrySubkeys(wmiClient, keypath, subkeyNames):
    results = {}
    for fieldName in subkeyNames:
        results[fieldName] = getRegValues(wmiClient, keypath, fieldName)
    return results


def _mergeDictionaries(toDictionary, fromDictionary):
    for key in fromDictionary.keys():
        toDictionary[key].update(fromDictionary[key])


def mainFunction(Framework, OSHVResult, softNameToInstSoftOSH=None):
    '''
    This function uses registry to provide information
    about installed software.

    '''

    props = Properties()
    props.setProperty(AgentConstants.PROP_WMI_NAMESPACE, 'root\\DEFAULT')
    wmiClient = None
    try:
        try:
            wmiClient = Framework.createClient(props)
            hostOSH = createHostOSH(Framework, wmiClient)
            OSHVResult.add(hostOSH)

            registryColumns = {'DisplayName': {}, 'InstallLocation': {},
                       'DisplayVersion': {}, 'Publisher': {}, 'ProductID': {},
                       'InstallDate': {}}
            keyNames = registryColumns.keys()
            # These are the Registry sections, where the Software Uninstall information is stored
            keyPaths = ['SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
                        'SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall']
            for keyPath in keyPaths:
                try:
                    result = getRegistrySubkeys(wmiClient, keyPath, keyNames)
                    _mergeDictionaries(registryColumns, result)
                except JavaException, e:
                    logger.info('Not a 64bit OS: ' + str(e))

            # do the work
            _createSoftware(registryColumns['DisplayName'], registryColumns['InstallLocation'],
                           registryColumns['DisplayVersion'], registryColumns['Publisher'],
                           registryColumns['ProductID'], registryColumns['InstallDate'],
                           hostOSH, OSHVResult,
                           softNameToInstSoftOSH)

            try:
                props = Properties()
                props.setProperty(AgentConstants.PROP_WMI_NAMESPACE, 'root\\cimv2')
                client = Framework.createClient(props)
                wmiProvider = WmiAgentProvider(client)
                hostDiscoverer = WmiHostDiscoverer(wmiProvider)
                if hostDiscoverer.isWin2008():
                    logger.debug('win2008 detected')
                    discoverWin2008HotFixes(wmiProvider, hostOSH, OSHVResult)
                elif hostDiscoverer.isWindows8_2012():
                    logger.debug('win 8 or win 2012 detected')
                    discoverWin8_2012HotFixes(wmiProvider, hostOSH, OSHVResult)
                else:
                    logger.debug('Non-win2008/8/2012 detected')
            finally:
                client.close()
        except JavaException, ex:
            exInfo = ex.getMessage()
            errormessages.resolveAndReport(exInfo, 'WMI', Framework)
        except:
            exInfo = logger.prepareJythonStackTrace('')
            errormessages.resolveAndReport(exInfo, 'WMI', Framework)
    finally:
        if wmiClient != None:
            wmiClient.close()


def discoverWin2008HotFixes(wmiProvider, hostOsh, OSHVResult):
    """
    Discovering win 2008 hot fix information by executing
    @types: WmiAgentProvider, ObjectStateHolder, ObjectStateHolderVector
    @command: select HotFixID, InstallDate from Win32_QuickFixEngineering
    """
    swDiscoverer = Win2008SoftwareDiscoverer(wmiProvider)
    softwareItems = swDiscoverer.getInstalledHotFixes()
    for sw in softwareItems:
        softwareOSH = hostresource.createSoftwareOSH(hostOsh, sw.name,
                             installDate=sw.installDate, publisher=sw.vendor, description=sw.description)
        OSHVResult.add(softwareOSH)

def discoverWin8_2012HotFixes(wmiProvider, hostOsh, OSHVResult):
    """
    Discovering win 8 or win 2012 hot fix information by executing
    @types: WmiAgentProvider, ObjectStateHolder, ObjectStateHolderVector
    @command: select HotFixID, InstallDate from Win32_QuickFixEngineering
    """
    swDiscoverer = Win8_2012SoftwareDiscoverer(wmiProvider)
    softwareItems = swDiscoverer.getInstalledHotFixes()
    for sw in softwareItems:
        softwareOSH = hostresource.createSoftwareOSH(hostOsh, sw.name,
                             installDate=sw.installDate, publisher=sw.vendor, description=sw.description)
        OSHVResult.add(softwareOSH)


def createHostOSH(framework, wmiClient):
    return (modeling.createOshByCmdbIdString('nt', framework.getDestinationAttribute('hostId'))
            or modeling.createHostOSH(wmiClient.getIpAddress()))


def mainFunctionWithWbem(Framework, wmiClient, OSHVResult,
                         softNameToInstSoftOSH=None):
    '''
    Discovers installed software and, for Windows 2008, hotfixes

    This function uses Win32_Product class
    http://msdn.microsoft.com/en-us/library/windows/desktop/aa394378(v=vs.85).aspx
    It's available since Windows 2000

    In Windows 2003 Server,
    Win32_Product is not enabled by default, and must be enabled as follows:

    1.In Add or Remove Programs, click Add/Remove Windows Components.
    2. In the Windows Components Wizard, select Management and Monitoring Tools and then click Details.
    3. In the Management and Monitoring Tools dialog box, select WMI Windows Installer Provider and then click OK.
    4. Click Next.

    Cons:
    It is terribly slow (querying might take up to 10 seconds)
    It represents information only about software installed using MSI (Microsoft Installer)
    '''
    try:
        hostOSH = createHostOSH(Framework, wmiClient)
        OSHVResult.add(hostOSH)
        wmiProvider = WmiAgentProvider(wmiClient)
        softwareDiscoverer = SoftwareDiscoverer(wmiProvider)
        softwareItems = softwareDiscoverer.getInstalledSoftware()

        for software in softwareItems:
            softwareOSH = hostresource.createSoftwareOSH(
                    hostOSH, software.name, path=software.path,
                    displayVersion=software.version,
                    publisher=software.vendor,
                    productId=software.productId,
                    installDate=software.installDate)
            OSHVResult.add(softwareOSH)
            if softNameToInstSoftOSH != None:
                softNameToInstSoftOSH[software.name.strip()] = softwareOSH
        hostDiscoverer = WmiHostDiscoverer(wmiProvider)
        if hostDiscoverer.isWin2008():
            discoverWin2008HotFixes(wmiProvider, hostOSH, OSHVResult)
        if hostDiscoverer.isWindows8_2012():
            discoverWin8_2012HotFixes(wmiProvider, hostOSH, OSHVResult)

    except JavaException, ex:
        exInfo = ex.getMessage()
        pattern = "(Invalid class.?)|(Could not connect to WMI.?)"
        if (re.match(pattern, exInfo) is not None):
            logger.debug("Cannot perform regular software discovery (seems that remote 2003 Win server doesn't have appropriate WMI object installed).")
            logger.debug("Trying to discover installed software from Windows registry")
            # try to retrieve information by using old (not efficient) method using remote registry
            wmiClient.close()
            mainFunction(Framework, OSHVResult, softNameToInstSoftOSH)
            wmiClient = Framework.createClient()
        else:
            errormessages.resolveAndReport(exInfo, 'WMI', Framework)
    except:
        exInfo = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(exInfo, 'WMI', Framework)
