#coding=utf-8
import re
import os
import sys
import traceback

import logger
import modeling

import file_mon_utils
import shellutils

from java.lang import String
from java.io import ByteArrayInputStream

from org.jdom.input import SAXBuilder
from org.xml.sax.ext import EntityResolver2
from org.xml.sax import InputSource

from java.io import File
from java.util import HashMap
import jdbc as jdbcModule

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile
from com.hp.ucmdb.discovery.library.common import CollectorsParameters

import netutils

class XMLExternalEntityResolver(EntityResolver2):
    SEPARATOR_WIN = "\\"
    SEPARATOR_UNIX = "/"

    def __init__(self, xmlFileMonitor, remotePath, shellUtils ):
        logger.debug("XMLExternalEntityResolver created." )
        self.fileMonitor = xmlFileMonitor
        self.shellUtils = shellUtils
        self.remotePath = os.path.dirname(remotePath)

        if self.shellUtils.isWinOs():
            self.fsSeparator = self.SEPARATOR_WIN
        else:
            self.fsSeparator = self.SEPARATOR_UNIX

    def getExternalSubset(self, name, baseURI):
        return None

    def resolveEntity(self, name, publicId, baseURI, systemId):
        logger.debug("XMLExternalEntityResolver resolveEntity, name : ",
                     name, ", publicId: ", publicId, ", baseURI: ", baseURI, ", systemId: ", systemId )

        try:
            filename = systemId
            logger.debug('resolveEntity, file name: ', filename, ", path: ", self.remotePath)
            strContent = String( self.fileMonitor.getFileContent(self.remotePath + self.fsSeparator + filename ) )
            return InputSource( ByteArrayInputStream( strContent.getBytes() ) )
        except Exception, ex:
            logger.debug("XMLExternalEntityResolver Exception: ", ex )
        except:
            pass

        logger.debug("XMLExternalEntityResolver, uses default DTD resolver")
        return None

class JdbcResource:
    def __init__(self, name, type, driverClass, url, maxActive):
        self.name = name
        self.type = type
        self.driverClass = driverClass
        self.url = url
        self.maxActive = maxActive
        self.tomcatOsh = None


class TomcatDiscoverer(file_mon_utils.FileMonitorEx):
    def __init__(self, Framework, OSHVResult, shellUtils=None):
        file_mon_utils.FileMonitorEx.__init__(self, Framework, OSHVResult, shellUtils)
        self.jdbcUrlparser = None
        self.serverInstallDir = None
        self.destinationIp = Framework.getDestinationAttribute('ip_address')

    def _addWebApp(self, appName, resourcePath, parentOsh, vHostDir, vHostJdbcOshMap, globalJdbcOshMap):
        webAppOsh = ObjectStateHolder('webapplication')
        webAppOsh.setAttribute('data_name', appName)
        webAppOsh.setAttribute('resource_path', resourcePath)
        webAppOsh.setContainer(parentOsh)
        self.OSHVResult.add(webAppOsh)

        appJdbcOshMap = HashMap(vHostJdbcOshMap)

        #report context and web config files
        logger.debug("report context and web config file for web application:", appName)

        for configFileName in ['context.xml', 'web.xml']:
            configFileToReport = self.createCF(webAppOsh, resourcePath + self.FileSeparator + "WEB-INF"+ self.FileSeparator + configFileName)
            if configFileToReport:
                logger.debug("found config file:", resourcePath + self.FileSeparator + "WEB-INF"+ self.FileSeparator + configFileName)
                self.OSHVResult.add(configFileToReport)

        appContextPath = vHostDir + appName + '.xml'
        if len(self.fileMonitor.getFilesInPath(vHostDir, appName + '.xml')) == 1:
            self.getContextJdbcResouces(appContextPath, appJdbcOshMap, globalJdbcOshMap)
        for appJdbcOsh in appJdbcOshMap.values():
            link = modeling.createLinkOSH('usage', webAppOsh, appJdbcOsh)
            self.OSHVResult.add(link)

    def discoverTomcat(self, configFile):
        '''
        @types: str ->
        @raise Failed to parse config file
         '''
        if self.fileMonitor is None:
            self.Framework.reportError("Failed to connect to the remote host. Tomcat discovery can't be completed")
            return
        logger.debug('Discovering Apache Tomcat by configuration file :', configFile)
        self.tomcatOsh = modeling.createApplicationOSH('tomcat', 'Apache Tomcat', self.hostOSH)
        self.tomcatOsh.setAttribute('webserver_configfile', configFile)
        configDoc = self.loadXmlFile(configFile, self.tomcatOsh)
        if configDoc is None:
            logger.warn('cannot parse configuration file, or it does not exist, skip the discovery')
            raise Exception ("Failed to parse configuration file: %s" % configFile)
        self.OSHVResult.add(self.tomcatOsh)
        tomcatHomeDir = self.getParentDir(self.getParentDir(configFile))

        configDir = self.getParentDir(configFile)

        logger.info('Loading Catalina.properties file...')
        props = self.fileMonitor.loadPropertiesFile(tomcatHomeDir + 'conf' + self.FileSeparator + 'catalina.properties')

        globalJdbcOshMap = HashMap()
        self.getJdbcResources(configDoc.getRootElement().getChild('GlobalNamingResources'), globalJdbcOshMap)
        serviceJdbcOshMap = HashMap()
        self.getContextJdbcResouces(configDir + 'context.xml', serviceJdbcOshMap, globalJdbcOshMap)
        #report context and web config files
        logger.debug("report context and web config file for server:", tomcatHomeDir)

        for configFileName in ['context.xml', 'web.xml']:
            configFileToReport = self.createCF(self.tomcatOsh, configDir + configFileName)
            if configFileToReport:
                logger.debug("found config file:", configDir + configFileName)
                self.OSHVResult.add(configFileToReport)

        tomcatServices = configDoc.getRootElement().getChildren('Service')
        for tomcatService in tomcatServices:
            engineEl = tomcatService.getChild('Engine')
            engineName = engineEl.getAttributeValue('name')
            vHostElList = engineEl.getChildren('Host')
            serviceDefaultVirtualHost = self.handleVirtualHostName(engineEl.getAttributeValue('defaultHost'))

            tomcatServiceName = tomcatService.getAttributeValue('name')
            logger.debug('Found service ', tomcatServiceName)
            tomcatServiceOsh = ObjectStateHolder('tomcatservice')
            tomcatServiceOsh.setAttribute('data_name', tomcatServiceName)
            tomcatServiceOsh.setAttribute('default_vhost', serviceDefaultVirtualHost)
            tomcatServiceOsh.setContainer(self.tomcatOsh)
            self.OSHVResult.add(tomcatServiceOsh)

            connectors = tomcatService.getChildren('Connector')
            for connector in connectors:
                port = connector.getAttributeValue('port')
                isHttps = connector.getAttributeValue('SSLEnabled')
                protocol = connector.getAttributeValue('protocol')
                scheme = connector.getAttributeValue('scheme')
                portName = None
                # check for newer Tomcat
                if protocol and protocol.lower().startswith("http"):
                    if isHttps and isHttps.lower() == "true":
                        portName = "https"
                    else:
                        portName = "http"
                # check for older Tomcat
                elif scheme and scheme.lower().startswith("http"):
                    if scheme.lower() == "https":
                        portName = scheme
                    else:
                        portName = "http"

                # In case port is predefined as parameter in catalina properties file, so for others
                matcher = re.search(r"\$\{(\w+(\.(\w+))*)\}", port)
                portKey = matcher and matcher.group(1) or None
                if not str(port).isdigit() and portKey is not None:
                    port = props.getProperty(portKey)

                # Port has to be a number
                if not str(port).isdigit():
                    logger.warn("Port [%s] is not a number. PortOsh is not to be reported!" % port)
                    continue
                else:
                    portOsh = modeling.createServiceAddressOsh(self.hostOSH, self.ipaddress, port, modeling.SERVICEADDRESS_TYPE_TCP, portName)
                    linkService = modeling.createLinkOSH('usage', tomcatServiceOsh, portOsh)
                    linkServer = modeling.createLinkOSH('usage', self.tomcatOsh, portOsh)
                    self.OSHVResult.add(portOsh)
                    self.OSHVResult.add(linkService)
                    self.OSHVResult.add(linkServer)

            engineDir = configDir + engineName + self.FileSeparator

            #report context and web config files
            logger.debug("report context and web config file for tomcat service:", engineName)

            for configFileName in ['context.xml', 'web.xml']:
                configFileToReport = self.createCF(tomcatServiceOsh, engineDir + configFileName)
                if configFileToReport:
                    logger.debug("found config file:", engineDir + configFileName)
                    self.OSHVResult.add(configFileToReport)
            serviceClusters = self.getClusters(tomcatService)
            for vHostEl in vHostElList:
                vHostName = vHostEl.getAttributeValue('name')
                logger.debug('Found virtual host ', vHostName, ' on service ',
                             tomcatServiceName)
                appBase = vHostEl.getAttributeValue('appBase')
                vHostOsh = ObjectStateHolder('webvirtualhost')
                vHostOsh.setAttribute('data_name', vHostName)
                vHostOsh.setContainer(tomcatServiceOsh)
                self.OSHVResult.add(vHostOsh)

                vHostDir = engineDir + vHostName + self.FileSeparator
                vHostJdbcOshMap = HashMap(serviceJdbcOshMap)
                vHostContextPath = vHostDir + 'context.xml'
                self.getContextJdbcResouces(vHostContextPath, vHostJdbcOshMap, globalJdbcOshMap)

                #report context and web config files
                logger.debug("report context and web config file for virtual host:", vHostName)

                for configFileName in ['context.xml', 'web.xml']:
                    configFileToReport = self.createCF(vHostOsh, vHostDir + configFileName)
                    if configFileToReport:
                        logger.debug("found config file:", vHostDir + configFileName)
                        self.OSHVResult.add(configFileToReport)

                vHostClusters = self.getClusters(vHostEl)
                for serviceClusterOsh in serviceClusters:
                    link = modeling.createLinkOSH('member', serviceClusterOsh, vHostOsh)
                    self.OSHVResult.add(link)
                for vHostClusterOsh in vHostClusters:
                    link = modeling.createLinkOSH('member', vHostClusterOsh, vHostOsh)
                    self.OSHVResult.add(link)

                if not ((appBase[1] == ':') or (appBase[0] == self.FileSeparator)):
                    appBase = self.normalizeDir(tomcatHomeDir + appBase)
                allFiles = self.fileMonitor.listFiles(appBase)
                for file in allFiles:
                    #remove file separator
                    appFolderName = file[:len(file) - 1]
                    #Create new mapping of JDBC resource to particular application only
                    #so this map prevent from modification of more general data stored in vHostJdbcOshMap
                    vHostAndServerContextJdbcOshMap = HashMap(vHostJdbcOshMap)

                    #Add all relevant datasources found at server.xml if any
                    for contextEl in vHostEl.getChildren('Context'):
                        if contextEl.getAttributeValue('docBase') == appFolderName:
                            self.getJdbcResources(contextEl, vHostAndServerContextJdbcOshMap)
                            break

                    if self.isDir(file):
                        if self.isValidWebApplicationFolder(file):
                            applicationFolderPath = self.normalizeDir(appBase + file)

                            self._addWebApp(appFolderName, applicationFolderPath, vHostOsh, vHostDir, vHostAndServerContextJdbcOshMap, globalJdbcOshMap)
                    else:
                        if file.rfind('.war') != -1:
                            appName = file[:len(file) - 4]
                            if self.isValidWebApplicationFolder(appName) and not self.normalizeDir(appName) in allFiles:
                                logger.debug("Found not unpacked application \"%s\"" % appName)
                                self._addWebApp(appName, self.normalizeDir(appBase) + file, vHostOsh, vHostDir, vHostAndServerContextJdbcOshMap, globalJdbcOshMap)

    def getChildText(self, el, childName):
        namespace = el.getNamespace()
        childs = None
        if namespace is None:
            childs = el.getChildren(childName)
        else:
            childs = el.getChildren(childName, namespace)
        if len(childs) == 1:
            return childs.get(0).getText().strip()
        return None

    def getApplicationName(self, applicationFolderPath):
        applicationDoc = self.loadXmlFile(applicationFolderPath + 'WEB-INF' + self.FileSeparator + 'web.xml')
        if applicationDoc is not None:
            return self.getChildText(applicationDoc.getRootElement(), 'display-name')
        return None

    def getClusters(self, clustersParentElement):
        clusterElList = clustersParentElement.getChildren('Cluster')
        clusters = []
        for clusterEl in clusterElList:
            tomcatClusterOsh = ObjectStateHolder('tomcatcluster')
            tomcatClusterOsh.setAttribute('data_name', 'Apache Tomcat Cluster')
            modeling.setAppSystemVendor(tomcatClusterOsh)
            mcastAddress = '228.0.0.4'
            mcastPort = '45564'
            membership = clusterEl.getChild('Membership')
            if membership is not None:
                try:
                    address = membership.getAttributeValue('mcastAddr')
                    mcastAddress = address
                except:
                    logger.debug('Failed to fetch mcast address, using default ', mcastAddress)
                try:
                    port = membership.getAttributeValue('mcastPort')
                    mcastPort = port
                except:
                    logger.debug('Failed to fetch mcast port, using default ', mcastPort)
            tomcatClusterOsh.setAttribute('tomcatcluster_multicastaddress', mcastAddress)
            tomcatClusterOsh.setIntegerAttribute('tomcatcluster_multicastport', mcastPort)
            self.OSHVResult.add(tomcatClusterOsh)
            clusters.append(tomcatClusterOsh)
        return clusters

    def getContextJdbcResouces(self, contextPath, jdbcOshMap, globalJdbcOshMap=None):
        logger.debug('Loading Jdbc resources from ', contextPath)
        contextEl = None
        doc = self.loadXmlFile(contextPath)
        if doc is not None:
            contextEl = doc.getRootElement()
            self.getJdbcResources(contextEl, jdbcOshMap, globalJdbcOshMap)

    def getJdbcResources(self, env, jdbcOshMap, globalJdbcResources=None):
        if env is None:
            return
        jdbcResources = HashMap()

        resources = env.getChildren('Resource')
        for resource in resources:
            name = resource.getAttributeValue('name')
            dsType = resource.getAttributeValue('type')
            driverClassName = resource.getAttributeValue('driverClassName')
            url = resource.getAttributeValue('url')
            maxActive = resource.getAttributeValue('maxActive')
            logger.debug('Found jdbc datasource ', name, ' driver ', str(driverClassName), ' url ', str(url))
            jdbcResources.put(name, JdbcResource(name, dsType, driverClassName, url, maxActive))

        for resource in resources:
            name = resource.getAttributeValue('name')
            if name is None:
                continue
            # do not read additional parameters for non-existing resource
            jdbcResource = jdbcResources.get(name)
            if jdbcResource is None:
                continue

            # update existing JDBC resource with absent parameters data
            for resourceParamsEl in env.getChildren('ResourceParams'):
                if resourceParamsEl.getAttributeValue('name') == name:

                    resourceParams = self.getResourceParamsValues(resourceParamsEl)
                    dsType = resourceParams.get('type')
                    if (dsType is not None) and (jdbcResource.type is None):
                        jdbcResource.type = dsType

                    driverClassName = resourceParams.get('driverClassName')
                    if (driverClassName is not None) and (jdbcResource.driverClass is None):
                        jdbcResource.driverClass = driverClassName

                    url = resourceParams.get('url')
                    if (url is not None) and (jdbcResource.url is None):
                        jdbcResource.url = url

                    maxActive = resourceParams.get('maxActive')
                    if (maxActive is not None) and (jdbcResource.maxActive is None):
                        jdbcResource.maxActive = maxActive

                    if jdbcResource.type != 'javax.sql.DataSource':
                        jdbcResources.remove(name)

        resources = env.getChildren('ResourceLink')
        for resource in resources:
            name = resource.getAttributeValue('name')
            globalName = resource.getAttributeValue('global')
            dsType = resource.getAttributeValue('type')
            logger.debug('Found resource link ', name, ' for global name ', globalName, ' of type ', dsType)
            if dsType != 'javax.sql.DataSource':
                continue
            if globalJdbcResources is not None:
                jdbcResource = globalJdbcResources.get(globalName)
            if jdbcResource is None:
                continue
            logger.debug('Found jdbc datastore with global name ', globalName)
            jdbcOshMap.put(name, jdbcResource)

        dnsResolver = _DnsResolverDecorator(netutils.JavaDnsResolver(), self.destinationIp)
        reporter = jdbcModule.DnsEnabledJdbcTopologyReporter(
            jdbcModule.DataSourceBuilder(), dnsResolver)

        class Container:
            def __init__(self, osh):
                self.osh = osh

            def getOsh(self):
                return self.osh

        container = Container(self.tomcatOsh)
        for jdbc in jdbcResources.values():
            datasource = jdbcModule.Datasource(jdbc.name,
                                               jdbc.url,
                                               driverClass=jdbc.driverClass)
            self.OSHVResult.addAll(reporter.reportDatasources(container, datasource))
            jdbcOshMap.put(jdbc.name, datasource.getOsh())

    def getResourceParamsValues(self, resourceParams):
        params = HashMap()
        parameters = resourceParams.getChildren('parameter')
        for parameter in parameters:
            try:
                name = parameter.getChild('name').getText()
                value = parameter.getChild('value').getText()
                if (value is not None) and (len(value) > 0):
                    params.put(name, value)
            except:
                pass
        return params

    def handleVirtualHostName(self, virtualHostName):
        return virtualHostName

    __invalidWebAppFolderNamePatterns = [
        r"\.{1,2}(\\)?"
    ]

    def isValidWebApplicationFolder(self, folderName):
        if not folderName:
            return 0
        for pattern in TomcatDiscoverer.__invalidWebAppFolderNamePatterns:
            if re.match(pattern, folderName):
                return 0
        return 1

    def loadXmlFile(self, path, container = None, fileContent = None):
        'str, osh, str -> Document'
        saxBuilder = SAXBuilder()
        globalSettings = GeneralSettingsConfigFile.getInstance()
        #loadExternalDTD = globalSettings.getPropertyBooleanValue('loadExternalDTD', 1)
        loadExternalDTD = 1
        saxBuilder.setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", loadExternalDTD)
        logger.debug("loadXmlFile, loadExternalDTD: ", loadExternalDTD, ", path: ", path )
        if loadExternalDTD :
            saxBuilder.setEntityResolver( XMLExternalEntityResolver( self.fileMonitor, str(path), self.shellUtils ) )
            saxBuilder.setFeature("http://xml.org/sax/features/use-entity-resolver2", 1)

        doc = None
        try:
            fileContent = fileContent or self.fileMonitor.getFileContent(path)
            if fileContent:
                try:
                    strContent = String(fileContent)
                    strContent = String(strContent.substring(0, strContent.lastIndexOf('>') + 1))
                    doc = saxBuilder.build(ByteArrayInputStream(strContent.getBytes()))
                    if container is not None:
                        cfOSH = self.createCF(container, path, fileContent)
                        if cfOSH is not None:
                            self.OSHVResult.add(cfOSH)
                except:
                    logger.debugException('Failed to load xml file:', path)

                    excMsg = traceback.format_exc()
                    logger.debug( excMsg )

        except:
            logger.debugException('Failed to get content of file:', path)

            excMsg = traceback.format_exc()
            logger.debug( excMsg )

        return doc

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    configFileList = Framework.getTriggerCIDataAsList('configfile') or []
    isDiscoverySuccess = 0
    custom_configList = Framework.getParameter('configFiles') or ''
    for x in custom_configList.split(','):
        configFileList.append(x.strip())
    if configFileList:
        try:
            discoverer = TomcatDiscoverer(Framework, OSHVResult)
            for configFile in configFileList:
                if configFile and configFile != 'NA':
                    try:
                        discoverer.discoverTomcat(configFile)
                    except Exception, ex:
                        logger.info('Failed to parse:', configFile)
                        logger.info("Exception: ", ex )
                    else:
                        isDiscoverySuccess = 1
        except:
            logger.debugException('Failed to discover Apache Tomcat')
            Framework.reportError('Failed to discover Apache Tomcat. See logs')

    if not isDiscoverySuccess or OSHVResult.size() == 0:
        Framework.reportError('Failed to discover Apache Tomcat. See logs')

    return OSHVResult


class _DnsResolverDecorator:
    r''' Decorates IP resolving by replacing local IP address with destination
    IP address
    '''
    def __init__(self, dnsResolver, destinationIpAddress):
        r'@types: netutils.BaseDnsResolver, str'
        assert (dnsResolver and destinationIpAddress
                and not netutils.isLocalIp(destinationIpAddress))
        self.__dnsResolver = dnsResolver
        self.__destinationIpAddress = destinationIpAddress

    def resolveIpsByHostname(self, hostname):
        ''' Process cases with loopback address (local IP)
        - when hostname is 'localhost' destination Ip address will be returned
        - resolved local IP address will be replaced by destination IP
        @types: str -> list[str]
        @raise ResolveException: Failed to resolve IP
        '''
        if hostname == 'localhost':
            return [self.__destinationIpAddress]
        ips = self.__dnsResolver.resolveIpsByHostname(hostname)
        isNotLocalIp = lambda ip: not netutils.isLocalIp(ip)
        nonLocalIps = filter(isNotLocalIp, ips)
        if len(nonLocalIps) < len(ips):
            # seems like we have local IPs
            nonLocalIps.append(self.__destinationIpAddress)
            ips = nonLocalIps
        return ips

    def __getattr__(self, name):
        return getattr(self.__dnsResolver, name)
