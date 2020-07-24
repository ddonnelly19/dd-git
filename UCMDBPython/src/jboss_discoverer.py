#coding=utf-8
'''
Created on May 7, 2011

@author: vvitvitskiy
'''
import re
import jee
import jmx
import jboss
import entity
import logger
import file_system
import file_topology
import jee_discoverer
import db
import jms
import netutils
import fptools
import UserDict
import sets
import jee_constants
import asm_jboss_discover

from java.lang import Exception as JException
from java.lang import Object
from java.lang import String
from java.util import Properties
from java.io import ByteArrayInputStream
from java.net import URL, MalformedURLException
from jarray import array
from javax.xml.xpath import XPathConstants

XPATH_NODESET = XPathConstants.NODESET
XPATH_STRING = XPathConstants.STRING
XPATH_NODE = XPathConstants.NODE

FILE_PATH = file_topology.FileAttrs.PATH
FILE_CONTENT = file_topology.FileAttrs.CONTENT

class PlatformTrait(entity.PlatformTrait):

    def __init__(self, majorVersionNumber, minorVersionNumber, microVersionNumber=None, versionQialifier=None, implementationTitle=None):
        ''' Representation of JBoss version: 5.1.0.GA [The Oracle], 4.3.0.GA_CP10 [EAP]
        @param: versionQualifier: Alpha[n], Beta[n], CR[n], Final, GA, GA_CP[nn]
        @param: implementationTitle: EAP or WonderLand, Trinity, Morpheus, The Oracle, etc for community edition
        @types:  '''
        platform = jee.Platform.JBOSS
        self.microVersion = entity.WeakNumeric(int, microVersionNumber)
        self.versionQualifier = versionQialifier
        self.implementationTitle = implementationTitle
        entity.PlatformTrait.__init__(self, platform, majorVersionNumber, minorVersionNumber)

    def isEAP(self):
        return self.implementationTitle == 'EAP'

    def __str__(self):
        version = '.'.join((str(self.majorVersion), str(self.minorVersion)))
        if self.microVersion.value(): version = '.'.join((version, str(self.microVersion)))
        if self.versionQualifier: version = '.'.join((version, self.versionQualifier))
        if self.implementationTitle: version = ''.join((version, ' [', self.implementationTitle,']'))
        return version

def getPlatformTrait(versionInfo):
    '''@types: str, jee.Platform, number -> entity.PlatformTrait
    @param fallbackVersion: Fallback parameter if version in provided info cannot be recognized
    @raise ValueError: Product version cannot be recognized
    '''
    matchObj = re.match('(\d+)\.(\d+)(?:\.(\d+))?(?:\.(\w+))?(?: \[(.+)\])?', str(versionInfo))
    if matchObj:
        major, minor, micro, qualifier, title = matchObj.groups()
        trait = PlatformTrait(major, minor, micro, qualifier, title)
        logger.info("Found JBoss version: %s" % trait)
    else:
        # JBoss application servers 3.0.0-3.2.3 have no approach to detect full
        # version by file-system, so we'll fallback to cover this case
        logger.info('Can not detect JBoss full version. Fallback to 3.0')
        trait = PlatformTrait('3', '0')
    return trait


class VersionLayout(jee_discoverer.Layout):

    def __init__(self, fs, jbossHomePath):
        '@types: file_system.FileSystem, str'
        jee_discoverer.Layout.__init__(self, fs)
        self.__jbossHomePath = self.path().absolutePath(jbossHomePath)

    def getJbossHomePath(self):
        '@types: -> str'
        return self.__jbossHomePath

    def getInstallationReadmeFilePath(self):
        '''@types: -> str'''
        return self.path().join(self.getJbossHomePath(), 'readme.html')

    def getJarVersionsXmlPath(self):
        '''@types: -> str'''
        return self.path().join(self.getJbossHomePath(), 'jar-versions.xml')

    def getLicensesConfigPath(self):
        '''@types: -> str'''
        return self.path().join(self.getJbossHomePath(),'docs', 'licenses', 'licenses.xml')

    def getModuleXmlPath(self):
        '''@types: -> str'''
        return self.path().join(self.getJbossHomePath(), 'modules', 'org', 'jboss', 'as', 'server', 'main', 'module.xml')


class BaseServerLayout(jee_discoverer.Layout, entity.HasPlatformTrait):
    'Describes product layout on FS'

    class DataSourceFileFilter(file_system.FileFilter):

        def __init__(self):
            self.filePattern = 'ds.xml'

        def accept(self, file_):
            '@types: file_topology.File -> bool'
            return file_.name.lower().endswith('-ds.xml')

    def __init__(self, fs, configFilePath, bindingConfigPath, resourcesDirsList):
        ''' @types: file_system.FileSystem, str, str, list(str) '''
        jee_discoverer.Layout.__init__(self, fs)
        path = self.path()
        self.__configFilePath = path.absolutePath( configFilePath )
        # bindingConfig may not exist, then ports are configured by jboss-service.xml
        self.__bindingConfigPath = bindingConfigPath and path.absolutePath( bindingConfigPath )
        self.__resourcesDirsList = []
        self.__resourcesDirsList.extend(map(path.absolutePath, resourcesDirsList))

    def __repr__(self):
        return 'BaseServerLayout("%s", "%s", "%s", %s)' % (self._getFs(),
                                                 self.__configFilePath,
                                                 self.__bindingConfigPath,
                                                 self.__resourcesDirsList)

    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        '''
        raise NotImplementedError()

    def getConfigFilePath(self):
        '''@types: -> str'''
        return self.__configFilePath

    def getBindingConfigPath(self):
        '''@types: -> str'''
        return self.__bindingConfigPath

    def getResourcesDirsList(self):
        '''@types: -> list(str)'''
        return self.__resourcesDirsList

    def listJmsConfigFiles(self):
        ''' @types: -> list(str) '''
        raise NotImplementedError()

    def listDatasourceDescriptorsFiles(self):
        '@types: -> list(File)'
        dsConfigs = []
        for path in self.getResourcesDirsList():
            try:
                files = self._getFs().getFiles(path, recursive=1, filters = [self.DataSourceFileFilter()])
                dsConfigs.extend(files)
            except Exception:
                logger.debugException("Failed to get list of config files")
        return dsConfigs


class BeansLayout(jee_discoverer.Layout):

    class BeansFileFilter(file_system.FileFilter):

        def __init__(self):
            self.filePattern = 'beans.xml'

        def accept(self, file_):
            return file_.name.lower().endswith('-beans.xml')

    def __init__(self, fs, resourcesDirs):
        jee_discoverer.Layout.__init__(self, fs)
        self.__resourcesDirsList = []
        self.__resourcesDirsList.extend(resourcesDirs)

    def getResourcesDirsList(self):
        return self.__resourcesDirsList

    def listBeansConfigFiles(self):
        configs = []
        for path in self.getResourcesDirsList():
            files = self._getFs().getFiles(path, recursive=1, filters=[self.BeansFileFilter()])
            configs.extend(files)
        return configs


#class BeansParser(jee_discoverer.BaseXmlParser):
#
#    def getHAProfileManagerBeanPattern(self):
#        return 'deployment/bean[@class="org.jboss.ha.singleton.HASingletonProfileManager"]'
#
#    def getHASingletonControllerBeanPattern(self):
#        return 'deployment/bean[@class="org.jboss.ha.singleton.HASingletonController"]'
#
#    def hasHAProfileManager(self, content):
#        document = self._buildDocumentForXpath(content, namespaceAware = 0)
#        return self._getXpath().evaluate('|'.join((# JBoss 3-4
#                                                   self.getHASingletonControllerBeanPattern(),
#                                                   # JBoss 5-6
#                                                   self.getHAProfileManagerBeanPattern())),
#                                         document, XPathConstants.NODESET).getLength()
#
#    def parseHAResourcesDirs(self, content):
#        resources = []
#        document = self._buildDocumentForXpath(content, namespaceAware = 0)
#        resourcesURIs = self._getXpath().evaluate('/'.join((self.getHAProfileManagerBeanPattern(), 'property[@name="URIList"]/list/value')), document, XPathConstants.NODESET)
#        if resourcesURIs.getLength(): # JBoss 5-6
#            for uriIndex in range(0, resourcesURIs.getLength()):
#                uri = resourcesURIs.item(uriIndex).getTextContent()
#                if uri:
#                    resources.append(uri)
#        else:
#            pattern = '/'.join((self.getHASingletonControllerBeanPattern(), '*[contains(@name,"argetStartMethodArgument")]/text()'))
#            targetStartMethodArgument = self._getXpath().evaluate(pattern, document, XPathConstants.STRING)
#            if targetStartMethodArgument:
#                resources.append(targetStartMethodArgument)
#        return resources


class ServerLayoutV3(BaseServerLayout):
    ''' layout for JBoss 3.0.5 - 3.0.8 '''

    class DataSourceFileFilter(file_system.FileFilter):
        def __init__(self):
            self.filePattern = '-service.xml'
        def accept(self, file_):
            '@types: file_topology.File -> bool'
            return file_.name.lower() not in ('counter-service.xml',
                                              'jbossmq-destinations-service.xml',
                                              'jbossmq-service.xml',
                                              'jca-service.xml',
                                              'jms-service.xml',
                                              'mail-service.xml',
                                              'properties-service.xml',
                                              'scheduler-service.xml',
                                              'user-service.xml') \
                    and file_.name.lower().endswith('-service.xml')

    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        '''
        return trait.majorVersion.value() == 3 and trait.minorVersion.value() == 0

#    def listDatasourceDescriptorsFiles(self):
#        ''' JBoss 3.0.x has the one file of jdbc configuration: <serverDir>/conf/standardjaws.xml '''
#        return [self._getFs().getFile(self.path().join(
#               self.path().dirName(self.getConfigFilePath()), 'standardjaws.xml'))]

    def listJmsConfigFiles(self):
        ''' @types: -> list(str) '''
        jmsConfigs = []
        for path in self.getResourcesDirsList():
            jmsConfigs.append(self.path().join(path, 'jbossmq-destinations-service.xml'))
        return jmsConfigs

class ServerLayoutV4(BaseServerLayout):
    ''' Layout suitable for JBoss 3.2 - 4.2 '''

    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        '''
        return (trait.majorVersion.value() == 3 and trait.minorVersion.value() == 2) or \
               (trait.majorVersion.value() == 4 and trait.minorVersion.value() <= 2)

    def listJmsConfigFiles(self):
        ''' @types: -> list(str) '''
        jmsConfigs = []
        for path in self.getResourcesDirsList():
            jmsConfigs.append(self.path().join(path, 'jms', 'jbossmq-destinations-service.xml'))
        return jmsConfigs

class ServerLayoutV43EAP(BaseServerLayout):
    ''' Layout suitable for JBoss 4.3 EAP '''

    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        '''
        return trait.majorVersion.value() == 4 and trait.minorVersion.value() == 3

    def listJmsConfigFiles(self):
        ''' @types: -> list(str) '''
        jmsConfigs = []
        for path in self.getResourcesDirsList():
            jmsConfigs.append(self.path().join(path, 'jboss-messaging.sar', 'destinations-service.xml'))
        return jmsConfigs


class ServerLayoutV5(BaseServerLayout):
    ''' Layout for JBoss 5.0 - 5.1 '''

    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        '''
        return trait.majorVersion.value() == 5

    def listJmsConfigFiles(self):
        '@types: -> list(str)'
        jmsConfigs = []
        for path in self.getResourcesDirsList():
            jmsConfigs.append(self.path().join(path, 'messaging', 'destinations-service.xml'))
        return jmsConfigs

class ServerLayoutV6(BaseServerLayout):
    ''' Layout for JBoss 6.0 - 6.1 '''

    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        '''
        return trait.majorVersion.value() == 6

    def listJmsConfigFiles(self):
        '@types: -> list(str)'
        jmsConfigs = []
        for path in self.getResourcesDirsList():
            jmsConfigs.append(self.path().join(path, 'hornetq', 'hornetq-jms.xml'))
        return jmsConfigs

class ServerLayoutV7(jee_discoverer.Layout, entity.HasPlatformTrait):

    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        '''
        return trait.majorVersion.value() == 7

    def __init__(self, fs, installDirPath):
        '''@types: str, str, file_system.FileSystem'''
        jee_discoverer.Layout.__init__(self, fs)
        path = self.path()
        self.__installDirPath = path.absolutePath( installDirPath )
        self.__fs = fs

    def getInstallDirPath(self):
        '@types: -> str'
        return self.__installDirPath

class StandaloneModeLayout(ServerLayoutV7):

    def __init__(self, fs, installDirPath, customStanaloneXmlPath = None):
        ServerLayoutV7.__init__(self, fs, installDirPath)
        path = self.path()
        if customStanaloneXmlPath:
            self.__configPath = path.absolutePath( customStanaloneXmlPath )
        else:
            self.__configPath = path.join(self.getInstallDirPath(), 'standalone', 'configuration', 'standalone.xml')

    def getStandaloneConfigPath(self):
        return self.__configPath

class DomainModeLayout(ServerLayoutV7):

    def __init__(self, fs, installDirPath, customDomainXmlPath = None, customHostXmlPath = None):
        ServerLayoutV7.__init__(self, fs, installDirPath)
        path = self.path()
        if customDomainXmlPath:
            self.__domainConfigPath = path.join(self.getInstallDirPath(), 'domain', 'configuration', customDomainXmlPath)
        else:
            self.__domainConfigPath = path.join(self.getInstallDirPath(), 'domain', 'configuration', 'domain.xml')
        if customHostXmlPath:
            self.__hostConfigPath = path.join(self.getInstallDirPath(), 'domain', 'configuration', customHostXmlPath)
        else:
            self.__hostConfigPath = path.join(self.getInstallDirPath(), 'domain', 'configuration', 'host.xml')

    def getDomainConfigPath(self):
        return self.__domainConfigPath

    def getHostConfigPath(self):
        return self.__hostConfigPath


class BaseApplicationLayout(jee_discoverer.ApplicationLayout, entity.HasPlatformTrait):

    class ExtractedEarFolderFilter(file_system.FileFilter):
        def accept(self, file_):
            r'@types: file_topology.File -> bool'
            raise NotImplementedError()

    class ExtractedWarFolderFilter(file_system.FileFilter):
        def accept(self, file_):
            r'@types: file_topology.File -> bool'
            raise NotImplementedError()

    def __init__(self, fs, serverBaseDir, deployDirsList):
        r'@types: str, str, file_system.FileSystem'
        jee_discoverer.Layout.__init__(self, fs)
        self.__serverBaseDirPath = self.path().absolutePath( serverBaseDir )
        self.__deployDirsList = []
        self.__deployDirsList.extend(deployDirsList)
        self._tmpDeployDirPath = None

    def getServerBaseDirPath(self):
        ''' @types: -> str '''
        return self.__serverBaseDirPath

    def getDeployDirsList(self):
        return self.__deployDirsList

    def findDeployedWarApplicationsPaths(self, recursive = 0):
        r'@types: -> list(str)'
        paths = []
        for file_ in self._getFs().getFiles(self._tmpDeployDirPath,
                                            recursive,
                                            filters = [self.ExtractedWarFolderFilter()],
                                            fileAttrs = [file_topology.FileAttrs.PATH, file_topology.FileAttrs.NAME]):
            paths.append(file_.path)
        return paths

    def findDeployedEarApplicationsPaths(self, recursive = 0):
        r'@types: -> list(str)'
        paths = []
        for file_ in self._getFs().getFiles(self._tmpDeployDirPath,
                                              recursive,
                                              filters = [self.ExtractedEarFolderFilter()],
                                              fileAttrs = [file_topology.FileAttrs.PATH, file_topology.FileAttrs.NAME]):
            paths.append(file_.path)
        return paths

    def extractAppNameFromEarPath(self, path, pattern):
        '@types: str -> str'
        m = re.search(pattern, path)
        if m is not None:
            appName = m.group(1)
        else:
            absPath = self.path().absolutePath(path)
            appName = self.path().baseName(absPath)
        return appName

    def extractAppNameFromWarPath(self, path, pattern):
        '@types: str -> str'
        m = re.search(pattern, path)
        if m is not None:
            appName = "%s.war" % m.group(1)
        else:
            absPath = self.path().absolutePath(path)
            appName = self.path().baseName(absPath)
        return appName

class ApplicationLayoutV30(BaseApplicationLayout):

    def _isApplicablePlatformTrait(self, trait):
        ''' @types: entity.PlatformTrait -> bool '''
        return trait.majorVersion.value() == 3 and trait.minorVersion.value() == 0

    class ExtractedEarFolderFilter(file_system.FileFilter):

        def __init__(self):
            self.filePattern = '.ear-contents'

        def accept(self, file_):
            r'@types: file_topology.File -> bool'
            return file_.path.endswith('.ear-contents')

    class ExtractedWarFolderFilter(file_system.FileFilter):

        def __init__(self):
            self.filePattern = '.war'

        def accept(self, file_):
            r'@types: file_topology.File -> bool'
            return file_.path.endswith('.war') \
                    and not file_.parent.endswith('.war') \
                    and not file_.parent.endswith('.ear-contents')

    def __init__(self, fs, serverBaseDir, deployDirsList):
        r'@types: str, str, file_system.FileSystem'
        BaseApplicationLayout.__init__(self, fs, serverBaseDir, deployDirsList)
        self._tmpDeployDirPath = self.path().join(self.getServerBaseDirPath(),
                                                  'tmp', 'deploy', 'server')

    def extractAppNameFromEarPath(self, path):
        '@types: str -> str'
        return BaseApplicationLayout.extractAppNameFromEarPath(self, path, '\.ear[\\\/]\d+\.(.+)-contents$')

    def extractAppNameFromWarPath(self, path):
        '@types: str -> str'
        absPath = self.path().absolutePath(path)
        return self.path().baseName(absPath)

    def findDeployedWarApplicationsPaths(self):
        r'@types: -> list(str)'
        return BaseApplicationLayout.findDeployedWarApplicationsPaths(self, recursive = 1)

    def findDeployedEarApplicationsPaths(self):
        r'@types: -> list(str)'
        return BaseApplicationLayout.findDeployedEarApplicationsPaths(self, recursive = 1)

class ApplicationLayoutV32(ApplicationLayoutV30):
    ''' There are location, that JBoss 3.2 unpacks deployed application:
    - ear-applications from <SERVER_HOME>/deploy/<APPNAME>.ear to:
        <SERVER_HOME>/tmp/deploy/tmp<digit-hash><APPNAME>.ear-contents
        there are placed unpacked inner war-module jar-modules as is
    - standalone war-applications from <SERVER_HOME>/deploy/<APPNAME>.war to:
        <SERVER_HOME>/tmp/deploy/tmp<digit-hash><APPNAME>.war
        there are placed unpacked files from war-archive '''

    def _isApplicablePlatformTrait(self, trait):
        ''' @types: entity.PlatformTrait -> bool '''
        return trait.majorVersion.value() == 3 and trait.minorVersion.value() == 2

    def __init__(self, fs, serverBaseDir, deployDirsList):
        r'@types: str, str, file_system.FileSystem'
        BaseApplicationLayout.__init__(self, fs, serverBaseDir, deployDirsList)
        self._tmpDeployDirPath = self.path().join(self.getServerBaseDirPath(), 'tmp', 'deploy')

    def extractAppNameFromEarPath(self, path):
        '@types: str -> str'
        return BaseApplicationLayout.extractAppNameFromEarPath(self, path, 'tmp\d+(.+?)-contents$')

    def extractAppNameFromWarPath(self, path):
        '@types: str -> str'
        return BaseApplicationLayout.extractAppNameFromWarPath(self, path, 'tmp\d+(.+?)(-exp)?\.war$')

    def findDeployedWarApplicationsPaths(self):
        r'@types: -> list(str)'
        return BaseApplicationLayout.findDeployedWarApplicationsPaths(self, recursive = 0)

    def findDeployedEarApplicationsPaths(self):
        r'@types: -> list(str)'
        return BaseApplicationLayout.findDeployedEarApplicationsPaths(self, recursive = 0)


class ApplicationLayoutV4(ApplicationLayoutV32):
    ''' JBoss 4.2 and EAP 4.2, 4.3 edition unpack deployed applications to such locations:
    - ear-applications from <SERVER_HOME>/deploy/<APPNAME>.ear to:
            <SERVER_HOME>/tmp/deploy/tmp<digit-hash><APPNAME>.ear-contents
    - war-applications from <SERVER_HOME>/deploy/<APPNAME>.war to:
            <SERVER_HOME>/tmp/deploy/tmp<digit-hash><APPNAME>-exp.war '''

    def _isApplicablePlatformTrait(self, trait):
        ''' @types: entity.PlatformTrait -> bool '''
        return trait.majorVersion.value() == 4

    class ExtractedWarFolderFilter(file_system.FileFilter):
        def accept(self, file_):
            r'@types: file_topology.File -> bool'
            return file_.path.endswith('-exp.war')

    def composeModulePathByEarPath(self, path, name):
        r''' Compose path to unpacked module in the EAR by specified EAR path
        For instance module with name testware_web.war will be unpacked to the
        directory testware_web-exp.war
        @types: str, str -> str
        @overriden
        '''
        extractedModuleName = name
        tokens = name.split('.')
        if len(tokens) > 1:
            tokens[-2] = '%s-exp' % tokens[-2]
            extractedModuleName = '.'.join(tokens)
        else:
            extractedModuleName = '%s-exp' % name
        return self.path().join(path, extractedModuleName)

class ApplicationLayoutV500(BaseApplicationLayout):
    ''' JBoss 5.0.0 community edition:
    ear-applications located only in:
        <SERVER_HOME>/deploy/<APPNAME>.ear
    war-applications unpacked to:
        <SERVER_HOME>/tmp/deploy/<APPNAME><19_DIGIT_HASH_###################>-exp.war '''

    def _isApplicablePlatformTrait(self, trait):
        ''' @types: entity.PlatformTrait -> bool '''
        return (trait.majorVersion.value() == 5 and \
                trait.minorVersion.value() == 0 and \
                trait.microVersion.value() == 0 and \
                not trait.isEAP())

    class ExtractedEarFolderFilter(file_system.FileFilter):
        def accept(self, file_):
            r'@types: file_topology.File -> bool'
            return file_.path.endswith('.ear')

    class ExtractedWarFolderFilter(file_system.FileFilter):
        def accept(self, file_):
            r'@types: file_topology.File -> bool'
            return file_.path.endswith('-exp.war')

    def __init__(self, fs, serverBaseDir, deployDirsList):
        r'@types: str, str, file_system.FileSystem'
        BaseApplicationLayout.__init__(self, fs, serverBaseDir, deployDirsList)
        self._tmpDeployDirPath = self.path().join(self.getServerBaseDirPath(), 'tmp', 'deploy')

    def extractAppNameFromWarPath(self, path):
        '@types: str -> str'
        # cut out application name between parent dir and 19-ditit hash
        return BaseApplicationLayout.extractAppNameFromWarPath(self, path, '([^\\\/]+)\d{19}\-exp\.war$')

    def extractAppNameFromEarPath(self, path):
        '@types: str -> str'
        absPath = self.path().absolutePath(path)
        return self.path().baseName(absPath)

    def findDeployedEarApplicationsPaths(self, recursive = 0):
        paths = []
        for deployDir in self.getDeployDirsList():
            for file_ in self._getFs().getFiles(deployDir,
                                                recursive,
                                                filters = [self.ExtractedEarFolderFilter()],
                                                fileAttrs = [file_topology.FileAttrs.PATH, file_topology.FileAttrs.NAME]):
                    paths.append(file_.path)
        return paths


class ApplicationLayoutV5(BaseApplicationLayout):
    ''' JBoss 5.0-5.1 EAP and JBoss 5.0.1-5.1.x community edition:
    - ear-applications located in:
        <SERVER_HOME>/deploy/<APPNAME>.ear
    - war-applications from <SERVER_HOME>/deploy/<APPNAME>.war unpacking to:
            <SERVER_HOME>/tmp/<alphanum-hash>/<APPNAME>.war (directory)
    Also there is vfs-nested.tmp directory located in the <SERVER_HOME>/tmp,
    depending on -Djboss.vfs.forceNoCopy=true/false it may contain yet another
    copy of all applications:
            <SERVER_HOME>/tmp/vfs-nested.tmp/<alphanum-hash>_<APPNAME>.(war|jar)
    this dir completely excluded from deployer application search '''

    class ExtractedEarFolderFilter(file_system.FileFilter):

        def __init__(self):
            self.filePattern = '.ear'

        def accept(self, file_):
            r'@types: file_topology.File -> bool'
            return file_.path.endswith('.ear') \
                    and not file_.parent.lower().endswith('vfs-nested.tmp')

    class ExtractedWarFolderFilter(file_system.FileFilter):

        def __init__(self):
            self.filePattern = '.war'

        def accept(self, file_):
            r'@types: file_topology.File -> bool'
            return file_.path.endswith('.war') \
                    and not file_.parent.lower().endswith('vfs-nested.tmp')

    def _isApplicablePlatformTrait(self, trait):
        ''' @types: entity.PlatformTrait -> bool '''
        return (trait.majorVersion.value() == 5 and \
                not (trait.minorVersion.value() == 0 and \
                     trait.microVersion.value() == 0 and \
                     not trait.isEAP()))

    def __init__(self, fs, serverBaseDir, deployDirsList):
        r'@types: str, str, file_system.FileSystem'
        BaseApplicationLayout.__init__(self, fs, serverBaseDir, deployDirsList)
        self._tmpDeployDirPath = self.path().join(self.getServerBaseDirPath(), 'tmp')

    def extractAppNameFromEarPath(self, path):
        '@types: str -> str'
        absPath = self.path().absolutePath(path)
        return self.path().baseName(absPath)

    def extractAppNameFromWarPath(self, path):
        '@types: str -> str'
        absPath = self.path().absolutePath(path)
        return self.path().baseName(absPath)

    def findDeployedWarApplicationsPaths(self):
        r'@types: -> list(str)'
        return BaseApplicationLayout.findDeployedWarApplicationsPaths(self, recursive = 1)

    def findDeployedEarApplicationsPaths(self, recursive = 0):
        paths = []
        for deployDir in self.getDeployDirsList():
            for file_ in self._getFs().getFiles(deployDir,
                                                recursive,
                                                filters = [self.ExtractedEarFolderFilter()],
                                                fileAttrs = [file_topology.FileAttrs.PATH, file_topology.FileAttrs.NAME]):
                    paths.append(file_.path)
        return paths


class ApplicationLayoutV6(BaseApplicationLayout):

    class ExtractedEarFolderFilter(file_system.FileFilter):

        def __init__(self):
            self.filePattern = '.ear'

        def accept(self, file_):
            r'@types: file_topology.File -> bool'
            return file_.path.endswith('.ear')

    class ExtractedWarFolderFilter(file_system.FileFilter):

        def __init__(self):
            self.filePattern = '.war-'

        def accept(self, file_):
            r'@types: file_topology.File -> bool'
            return re.search('\-[\da-f]{16}$', file_.path)

    def _isApplicablePlatformTrait(self, trait):
        ''' @types: entity.PlatformTrait -> bool '''
        return (trait.majorVersion.value() == 6 and \
                not trait.isEAP())

    def __init__(self, fs, serverBaseDir, deployDirsList):
        r'@types: str, str, file_system.FileSystem'
        BaseApplicationLayout.__init__(self, fs, serverBaseDir, deployDirsList)
        self._tmpDeployDirPath = self.path().join(self.getServerBaseDirPath(), 'tmp', 'vfs')

    def extractAppNameFromEarPath(self, path):
        '@types: str -> str'
        absPath = self.path().absolutePath(path)
        return self.path().baseName(absPath)

    def extractAppNameFromWarPath(self, path):
        '@types: str -> str'
        # cut out application name between parent dir and 19-ditit hash
        return BaseApplicationLayout.extractAppNameFromWarPath(self, path, '([^\\\/]+)\.war\-[\da-f]{16}')

    def findDeployedWarApplicationsPaths(self):
        r'@types: -> list(str)'
        return BaseApplicationLayout.findDeployedWarApplicationsPaths(self, recursive = 1)

    def findDeployedEarApplicationsPaths(self, recursive = 0):
        paths = []
        for deployDir in self.getDeployDirsList():
            for file_ in self._getFs().getFiles(deployDir,
                                                recursive,
                                                filters = [self.ExtractedEarFolderFilter()],
                                                fileAttrs = [file_topology.FileAttrs.PATH, file_topology.FileAttrs.NAME]):
                    paths.append(file_.path)
        return paths


class ServerRuntime(jee_discoverer.ServerRuntime):

    def findHomeDirPath(self):
        return self._getCommandLineDescriptor().extractProperty(r'jboss.home.dir')

    def extractOptionValue(self, name, optionType = None):
        '''
        @types: str, str -> str or None
        '''
        options = self._getCommandLineDescriptor().parseElements()
        for option in options:
            if optionType and option.getType() == optionType and option.getName() == name:
                return option.getValue()
            elif option.getName() == name:
                return option.getValue()

    def findJbossProperties(self):
        ''' Translate JBoss command line options to jboss system Properties '''
        options = self._getCommandLineDescriptor().parseElements()
        jbossProperties = {}
        for option in options:
            optionName = option.getName()
            if option.getType() == jee.CmdLineElement.Type.JAVA_OPTION:
                jbossProperties[optionName] = option.getValue()
            elif optionName == '-c' or optionName == '--configuration':
                jbossProperties['jboss.server.name'] = option.getValue()
            elif re.match('-b(.*)', optionName) or optionName =='--host':
                interfaceName = None
                if optionName !='--host':
                    interfaceName = re.match('-b(.*)', optionName).group(1)
                    # handle -b=<val> or -bpublic=<val> cases:
                if not interfaceName or interfaceName == 'public':
                    jbossProperties['jboss.bind.address'] = option.getValue()
                # case for -b<interface>=<val>:
                else:
                    jbossProperties['.'.join(['jboss.bind.address', interfaceName])] = option.getValue()
            elif optionName == '-u':
                jbossProperties['jboss.default.multicast.address'] = option.getValue()
        return jbossProperties

class VersionInfoDiscovererByShell(jee_discoverer.DiscovererByShell):

    def __init__(self, shell, layout):
        jee_discoverer.DiscovererByShell.__init__(self, shell, layout)
        self._xmlParser = jee_discoverer.BaseXmlParser()

    def _discoverVersionFromXml(self, path, parser):
        try:
            return parser(self._getShell().getXML(path))
        except (Exception, JException):
            logger.debug('Failed to discover JBoss version from xml: %s' % path)

    def _discoverVersionFromPlain(self, path, parser):
        try:
            return parser(self._getShell().safecat(path))
        except (Exception, JException):
            logger.debug('Failed to discover JBoss version from: %s' % path)

    def discoverVersion(self):
        ''' JBoss full version (like 4.0.0 or 4.2.3.GA, at least 3 digits) can be discovered:
            - by <jbossHomeDir>/docs/licenses/licenses.xml (suitable for versions: 6.0, 6.1)
            - by <jbossHomeDir>/modules/org/jboss/as/server/main/module.xml (suitable for 7.0, 7.1)
            - by <jbossHomeDir>/jar-versions.xml (suitable for 5.1, 5.0, 4.2, 3.2)
            - by <jbossHomeDir>/readme.html (suitable for 4.0) '''
        return (# get version from licenses.xml
                self._discoverVersionFromXml(self.getLayout().getLicensesConfigPath(), self.__parseVersionInLicensesXml)
                # get version from jar-module.xml
                or self._discoverVersionFromXml(self.getLayout().getModuleXmlPath(), self.__parseVersionInModuleXml)
                # get version from jar-versions.xml
                or self._discoverVersionFromXml(self.getLayout().getJarVersionsXmlPath(), self.__parseVersionInJarVersionsXml)
                # get version from readme.html
                or self._discoverVersionFromPlain(self.getLayout().getInstallationReadmeFilePath(), self.__parseVersionInReadme))

    def __parseVersionInLicensesXml(self, content):
        ''' Parse JBoss version from jboss-as-server license version in licenses.xml file
        @resource-file: licenses.xml
        @types: str -> str or None
        '''
        document = self._xmlParser._buildDocumentForXpath(content, namespaceAware = 0)
        xpath = self._xmlParser._getXpath()
        version = xpath.evaluate(r'licenseSummary/dependencies/dependency[artifactId="jboss-as-server"]/version/text()', document, XPathConstants.STRING)
        return version

    def __parseVersionInModuleXml(self, content):
        ''' Parse JBoss version from jboss-as-server-7.x.x.Final.jar version in module.xml
        @resource-file: module.xml
        @types: str -> str or None
        '''
        document = self._xmlParser._buildDocumentForXpath(content, namespaceAware = 0)
        xpath = self._xmlParser._getXpath()
        jarFileName = xpath.evaluate(r'module/resources/resource-root/@path', document, XPathConstants.STRING)
        if jarFileName:
            m = re.search('jboss-as-server-(.*)\.jar', jarFileName)
        return m and m.group(1)

    def __parseVersionInJarVersionsXml(self, content):
        ''' Parse JBoss version by version of JBoss run.jar
        @resource-file: jar-versions.xml
        @types: str -> str
        '''
        document = self._xmlParser._buildDocumentForXpath(content, namespaceAware = 0)
        xpath = self._xmlParser._getXpath()
        version = xpath.evaluate(r'jar-versions/jar[@name="run.jar"]/@specVersion', document, XPathConstants.STRING)
        implementationTitle = xpath.evaluate(r'jar-versions/jar[@name="run.jar"]/@implTitle', document, XPathConstants.STRING)
        title = None
        if implementationTitle:
            m = re.search('JBoss (\[.+\])', implementationTitle)
            title = m and m.group(1)
        return version and (title and ' '.join((version, title)) or version)

    def __parseVersionInReadme(self, content):
        ''' Parse JBoss version from <TITLE> of JBoss readme.html
        @resource-file: readme.html
        @types: str -> str or None
        '''
        m = re.search('<title>.+?\s+(.+?)\s+.+', content)
        return m and m.group(1)


class BindingsConfiguration:
    r'''Object representation of port binding files
    @deprecated: Will be removed
    for jboss 4.x:
    @resource-file: jboss-service.xml
    for jboss 5.x:
    @resource-file: bindings.xml
    for jboss jboss 6.x:
    @resource-file: bindings-jboss-beans.xml
    '''

    class NamingService:
        '''
        represents "org.jboss.naming.NamingService" bean from jboss-service.xml (jboss 4.x)
        '''
        def __init__(self, jnpPort, jnpBindAddress, rmiPort, rmiBindAddress):
            '''
            @types: int, str, int, str
            @raise Exception: bindAddress is not defined
            @raise Exception: rmiBindAddress is not defined
            '''
            self.jnpPort = entity.Numeric(int)
            self.jnpPort.set(jnpPort)
            if not jnpBindAddress: raise Exception('JNP Bind Address is not defined')
            self.jnpBindAddress = jnpBindAddress
            self.rmiPort = entity.Numeric(int)
            self.rmiPort.set(rmiPort)
            if not rmiBindAddress: raise Exception('RMI Bind Address is not defined')
            self.rmiBindAddress = rmiBindAddress

        def __repr__(self):
            return 'NamingService("%s", "%s", "%s", "%s")' % (self.jnpPort.value(), self.jnpBindAddress, self.rmiPort.value(), self.rmiBindAddress)


class ServerSocketDescriptor:
    ''' Represents server socket description in config files
    @types: str, str
    @param port: port value, can be JBoss variable expression or digit
    @param host: overrides jboss.bind.address if defined
    '''
    def __init__(self, port, host = None):
        self.__port = port
        self.__host = host

    def __repr__(self):
        return 'ServerSocketDescriptor("%s", "%s")' % (self.__port, self.__host)

    def getPort(self):
        return self.__port

    def getHost(self):
        return self.__host


class DestinationServiceDescriptor:
    r'''Object representation for descriptor file
    @resource-file: destinations-service.xml
    '''
    def __init__(self):
        # list(jms.Destination)
        self.__jmsDestinations = []

    def addJmsDestinations(self, *destinations):
        self.__jmsDestinations.extend(destinations)

    def getJmsDestinations(self):
        return self.__jmsDestinations[:]

class DatasourceDescriptor:
    def __init__(self):
        self.userName = None
        self.serverName = None
        self.connectionUrl = None
        self.portNumber = None
        self.databaseName = None
        self.description = None
        self.metadata = None
        self.systemNumber = None
        self.driverClass = None
        self.jndiName = None
        self.maxCapacity = None

class BaseConfigParser(entity.HasPlatformTrait, jee_discoverer.BaseXmlParser):
    ''' Common ServerConfigParser '''

    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        '''
        raise NotImplementedError()

    def parseBindingManagerConfigName(self, content):
        ''' Parse name of binding configuration
        @types: str-> str
        '''
        raise NotImplementedError()

    def parseBindingManagerConfigPath(self, content):
        ''' Parse path of binding configuration
        @types: str-> str
        '''
        raise NotImplementedError()

    def parseBindingsFromBindingManagerConfig(self, content, bindingConfigName):
        ''' Parse service bindings from BindingManager configuration
        @types: str, str -> list(ServerSocketDescriptor)
        '''
        raise NotImplementedError()

    def parseBindingsFromJBossServiceXml(self, content):
        ''' Parse bindings from main JBoss config jboss-service.xml
        @types: str -> str
        @resource-file: jboss-service.xml
        '''
        bindings = []
        document = self._buildDocumentForXpath(content, namespaceAware = 0)
        xpath = self._getXpath()
        # at first get all jboss:service MBeans
        serviceNodes = xpath.evaluate(r'server/mbean[starts-with(@name,"jboss:service=")]', document, XPathConstants.NODESET)
        for serviceIndex in range(0, serviceNodes.getLength()):
            ports = []
            hosts = []
            hostNodes = xpath.evaluate(r'attribute[contains(@name,"Address")] | attribute[contains(@name,"Host")]',serviceNodes.item(serviceIndex), XPathConstants.NODESET)
            for hostIndex in range(0, hostNodes.getLength()):
                hosts.append(hostNodes.item(hostIndex).getTextContent())
            portNodes = xpath.evaluate(r'attribute[contains(@name,"Port")]',serviceNodes.item(serviceIndex), XPathConstants.NODESET)
            for portIndex in range(0, portNodes.getLength()):
                ports.append(portNodes.item(portIndex).getTextContent())
            # set default host if host wasn't defined
            not hosts and map(lambda x: hosts.append('${jboss.bind.address}'), ports)
            for port,host in zip(ports, hosts):
                if port != '0':
                    binding = ServerSocketDescriptor(port, host)
                    bindings.append(binding)
        return bindings

    def parseDatasourceConfig(self, content):
        r'''@types: str -> list(jee.Datasource)
        @resource-file: server/default/deploy/*-ds.xml
        @raise ValueError: Not a JDBC datasource configuration
        '''
        xpath = self._getXpath()
        document = self._buildDocumentForXpath(content, namespaceAware=0)
        datasources = []
        # parse connection factories:
        cfNodes = xpath.evaluate(r'connection-factories/*',
                                              document, XPathConstants.NODESET)
        for cfElementIndex in range(0, cfNodes.getLength()):
            cfNode = cfNodes.item(cfElementIndex)
            if not cfNode.getNodeName().lower().endswith('connection-factory'):
                continue
            # check the nature of connection factory: jdbc or jms
            connectionDefinition = xpath.evaluate(r'connection-definition/text()', cfNode, XPathConstants.STRING)
            if (connectionDefinition and connectionDefinition.lower().endswith('jmsconnectionfactory')):
                raise ValueError('Not a JDBC datasource configuration')
            ds = DatasourceDescriptor()
            ds.jndiName = xpath.evaluate(r'jndi-name/text()', cfNode, XPathConstants.STRING)
            ds.userName = xpath.evaluate(r'user-name/text() | config-property[@name="UserName"]/text()', cfNode, XPathConstants.STRING)
            ds.serverName = xpath.evaluate(r'config-property[@name="ServerName"]/text()', cfNode, XPathConstants.STRING)
            ds.connectionUrl = xpath.evaluate(r'config-property[@name="ConnectionURL"]/text()', cfNode, XPathConstants.STRING)
            ds.portNumber = xpath.evaluate(r'config-property[@name="PortNumber"]/text()', cfNode, XPathConstants.STRING)
            ds.databaseName = xpath.evaluate(r'config-property[@name="Database"]/text()', cfNode, XPathConstants.STRING)
        # parse jdbc datasources:
        dsNodes = xpath.evaluate(r'datasources/*', document,
                                 XPathConstants.NODESET)
        for dsElementIndex in range(0, dsNodes.getLength()):
            dsNode = dsNodes.item(dsElementIndex)
            if not dsNode.getNodeName().lower().endswith('datasource'):
                continue
            ds = DatasourceDescriptor()
            ds.jndiName = xpath.evaluate(r'jndi-name/text()', dsNode, XPathConstants.STRING)
            ds.userName = xpath.evaluate(r'user-name/text() | xa-datasource-property[@name="User"]/text()', dsNode, XPathConstants.STRING)
            ds.connectionUrl = xpath.evaluate(r'connection-url/text() | xa-datasource-property[@name="URL"]/text()', dsNode, XPathConstants.STRING)
            ds.driverClass = xpath.evaluate(r'driver-class/text() | xa-datasource-class/text()', dsNode, XPathConstants.STRING)
            ds.description = xpath.evaluate(r'xa-datasource-property[@name="Description"]/text()', dsNode, XPathConstants.STRING)
            ds.portNumber = xpath.evaluate(r'xa-datasource-property[@name="PortNumber"]/text()', dsNode, XPathConstants.STRING)
            ds.databaseName = xpath.evaluate(r'xa-datasource-property[@name="DatabaseName"]/text()', dsNode, XPathConstants.STRING)
            if not ds.databaseName:
                #DB name also can be fetched from depends tag, where ObjectName resides
                dependsNodes = xpath.evaluate(r'depends', dsNode, XPathConstants.NODESET)
                for nodeIndex in range(0, dependsNodes.getLength()):
                    dependsString = dependsNodes.item(nodeIndex).getTextContent()
                    objectName = jmx.restoreObjectName(dependsString)
                    databaseName = objectName.getKeyProperty('database')
                    if databaseName:
                        ds.databaseName = databaseName
            ds.serverName = xpath.evaluate(r'xa-datasource-property[@name="ServerName"]/text()', dsNode, XPathConstants.STRING)
            ds.maxCapacity = xpath.evaluate(r'max-pool-size', dsNode, XPathConstants.STRING)
            if ds.jndiName:
                datasources.append(ds)
        return datasources

    def parseDestinationsService(self, content):
        '''@types: str -> jboss.DestinationServiceDescriptor
        @resource-file: destinations-service.xml
        '''
        root = self._getRootElement(content)
        destinationTypeBySignature = {
            'Queue' : jms.Queue,
            'Topic' : jms.Topic
        }
        descriptor = DestinationServiceDescriptor()
        for dest in root.getChildren('mbean'):
            objectNameStr = dest.getAttributeValue('name')
            objectName = jmx.restoreObjectName(objectNameStr)
            serviceType = objectName.getKeyProperty('service')
            destinationClass = destinationTypeBySignature.get(serviceType)
            if destinationClass:
                destination = jee.createNamedJmxObject(objectNameStr, destinationClass)
                descriptor.addJmsDestinations(destination)
        return descriptor


class ServerConfigParserV30(BaseConfigParser):

    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        '''
        return trait.majorVersion.value() == 3 \
                and trait.minorVersion.value() == 0

    def parseResourcesDirsList(self, content):
        ''' Parse list of resources directories from jboss-service.xml
        Suitable for JBoss 3.x - 4.x
        @types: str -> str
        @resource-file: jboss-service.xml
        '''
        document = self._buildDocumentForXpath(content, namespaceAware = 0)
        xpath = self._getXpath()
        resourcesDirs = xpath.evaluate(r'server/mbean[@code="org.jboss.deployment.scanner.URLDeploymentScanner"]/attribute[@name="URLs"]/text()', document, XPathConstants.STRING)
        trimTabsAndSpaces = lambda x: x.strip(' \t\n\r')
        return resourcesDirs and map(trimTabsAndSpaces, resourcesDirs.split(','))

    def parseBindingManagerConfigName(self, content):
        ''' Parse name of binding configuration from jboss-service.xml
        Separate binding manager configuration appeared since JBoss 3.0.5
        @types: str -> str
        @resource-file: jboss-service.xml
        '''
        document = self._buildDocumentForXpath(content, namespaceAware = 0)
        xpath = self._getXpath()
        return xpath.evaluate(r'server/mbean[@code="org.jboss.services.binding.ServiceBindingManager"]/attribute[@name="ServerName"]/text()', document, XPathConstants.STRING)

    def parseBindingManagerConfigPath(self, content):
        ''' Parse path to binding configuration file from jboss-service.xml
        @types: str -> str
        @resource-file: jboss-service.xml
        '''
        document = self._buildDocumentForXpath(content, namespaceAware = 0)
        xpath = self._getXpath()
        return xpath.evaluate(r'server/mbean[@code="org.jboss.services.binding.ServiceBindingManager"]/attribute[@name="StoreURL"]/text()', document, XPathConstants.STRING)

    def parseBindingsFromBindingManagerConfig(self, content, bindingConfigName):
        ''' Parse service bindings from BindingManager config
        @types: str, str -> list(ServerSocketDescriptor)
        @resource-file: bindings.xml
        '''
        bindings = []
        document = self._buildDocumentForXpath(content, namespaceAware = 0)
        xpath = self._getXpath()
        bindingNodes = xpath.evaluate(''.join(['service-bindings/server[@name="', bindingConfigName, '"]/service-config/binding']), document, XPathConstants.NODESET)
        for bindingIndex in range(0, bindingNodes.getLength()):
            host = bindingNodes.item(bindingIndex).getAttribute('host')
            port = bindingNodes.item(bindingIndex).getAttribute('port')
            if port:
                binding = ServerSocketDescriptor(port, host)
                bindings.append(binding)
        # RmiPort may has special case for port definition:
        #         <delegate-config portName="Port" hostName="BindAddress">
        #            <attribute name="RmiPort">1198</attribute>
        #         </delegate-config>
        rmiPort = xpath.evaluate(''.join(['service-bindings/server[@name="', bindingConfigName, '"]/service-config/delegate-config/attribute[@name="RmiPort"]/text()']), document, XPathConstants.STRING)
        if rmiPort:
            binding = ServerSocketDescriptor(rmiPort)
            bindings.append(binding)
        return bindings

    def parseDatasourceConfig(self, content):
        datasources = []
        document = self._buildDocumentForXpath(content, namespaceAware = 0)
        xpath = self._getXpath()
        dsNodes = xpath.evaluate('server/mbean[contains(@code,"ConnectionManager")]/depends/mbean[contains(@code,"RARDeployment")]', document, XPathConstants.NODESET)
        for dsIndex in range(0, dsNodes.getLength()):
            datasourceNode = dsNodes.item(dsIndex)
            jndiName = xpath.evaluate('attribute[@name="JndiName"]/text()', datasourceNode, XPathConstants.STRING)
            if jndiName:
                datasource = DatasourceDescriptor()
                datasource.jndiName = jndiName
                datasource.connectionUrl = xpath.evaluate('attribute/properties/config-property[@name="ConnectionURL"]', datasourceNode, XPathConstants.STRING)
                datasource.driverClass = xpath.evaluate('attribute/properties/config-property[@name="DriverClass"]', datasourceNode, XPathConstants.STRING)
                datasource.userName = xpath.evaluate('attribute/properties/config-property[@name="UserName"]', datasourceNode, XPathConstants.STRING)
                if datasource.jndiName:
                    datasources.append(datasource)
        return datasources

class ServerConfigParserV34(ServerConfigParserV30):

    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        '''
        return (trait.majorVersion.value() == 3 and trait.minorVersion.value() == 2) \
               or trait.majorVersion.value() == 4

    def parseDatasourceConfig(self, content):
        ''' Using parse method from BaseConfigParser '''
        return BaseConfigParser.parseDatasourceConfig(self, content)

class ServerConfigParserV5(BaseConfigParser):

    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        '''
        return trait.majorVersion.value() == 5

    def parseCustomConfigFileName(self, content):
        ''' Parse path to custom main config file (jboss-service.xml) from profile.xml
        Suitable for JBoss 5.x - 6.x
        @types: str -> str
        @resource-file: profile.xml
        '''
        document = self._buildDocumentForXpath(content, namespaceAware = 0)
        xpath = self._getXpath()
        # request suitable for JBoss 5.0.0 and 5.0.1
        configFile = xpath.evaluate(r'deployment/bean[@class="org.jboss.system.server.profileservice.VFSBootstrapScannerImpl"]/property[@name="URIList"]/list/value/text()', document, XPathConstants.STRING)
        if not configFile:
            # request suitable for JBoss 5.0 EAP, 5.1, 5.1 EAP, 6.0 and 6.1:
            configFile = xpath.evaluate(r'deployment/bean[@class="org.jboss.system.server.profileservice.StaticClusteredProfileFactory"]/property[@name="bootstrapURI"]/text()', document, XPathConstants.STRING) or \
                         xpath.evaluate(r'deployment/bean[@class="org.jboss.system.server.profileservice.repository.StaticProfileFactory"]/property[@name="bootstrapURI"]/text()', document, XPathConstants.STRING)
        return configFile

    def parseResourcesDirsList(self, content):
        ''' Parse list of resources directories from profile.xml
        Suitable for JBoss 5.x - 6.x
        @types: str -> str
        @resource-file: profile.xml
        '''
        document = self._buildDocumentForXpath(content, namespaceAware = 0)
        xpath = self._getXpath()
        resourcesDirs = []
        # request suitable for JBoss 5.0.0 and 5.0.1
        resourcesDirNodes = xpath.evaluate(r'deployment/bean[@class="org.jboss.system.server.profileservice.VFSDeploymentScannerImpl"]/property[@name="URIList"]/list/value', document, XPathConstants.NODESET)
        if not resourcesDirNodes.getLength():
            # request suitable for JBoss 5.0 EAP, 5.1, 5.1 EAP, 6.0 and 6.1:
            resourcesDirNodes = xpath.evaluate(r'deployment/bean[contains(@class,"ProfileFactory")]/property[@name="applicationURIs"]/list/value', document, XPathConstants.NODESET)
        for dirIndex in range(0, resourcesDirNodes.getLength()):
            resourcesDirs.append(resourcesDirNodes.item(dirIndex).getTextContent())
        return resourcesDirs

    def parseActiveMetadataSetName(self, content):
        ''' Parse name of active set of ServiceBindingMetadata
        e.g. <parameter><inject bean="StandardBindings"/></parameter>
        @types: str -> str
        @resource-file: bindings.xml
        '''
        document = self._buildDocumentForXpath(content, namespaceAware = 0)
        xpath = self._getXpath()
        metadataSetName = xpath.evaluate(r'deployment/bean[@class="org.jboss.services.binding.managed.ServiceBindingManagementObject"]/constructor/parameter[3]/inject/@bean', document, XPathConstants.STRING) or \
                          xpath.evaluate(r'deployment/bean[@class="org.jboss.services.binding.ServiceBindingManager"]/constructor/parameter[2]/bean/property[@name="standardBindings"]/inject/@bean', document, XPathConstants.STRING)
        return metadataSetName

    def parseActiveBindingSetName(self, content):
        ''' Parse name of active set of Bindings
        e.g. <parameter>${jboss.service.binding.set:ports-default}</parameter>
        '''
        document = self._buildDocumentForXpath(content, namespaceAware = 0)
        xpath = self._getXpath()
        bindingSetName = xpath.evaluate(r'deployment/bean[@class="org.jboss.services.binding.managed.ServiceBindingManagementObject"]/constructor/parameter[1]/text()', document, XPathConstants.STRING) or \
                         xpath.evaluate(r'deployment/bean[@class="org.jboss.services.binding.ServiceBindingManager"]/constructor/parameter[1]/text()', document, XPathConstants.STRING)
        return bindingSetName

    def parseBindingManagerConfigPath(self, content):
        ''' In JBoss 5.0 EAP, JBoss 5.1 and JBoss 5.1 EAP path to bindingManager config DIR defined in profile.xml
        In JBoss 5.0.0 and 5.0.1 config located in <jbossConfigDir>/bootstrap/bindings.xml
        In JBoss 6.0 and 6.1 - <jbossConfigDir>/bindingservice.beans/META-INF/bindings-jboss-beans.xml
        @types: str -> str
        @resource-file: profile.xml
        '''
        document = self._buildDocumentForXpath(content, namespaceAware = 0)
        xpath = self._getXpath()
        return xpath.evaluate(r'deployment/bean[@class="org.jboss.system.server.profileservice.StaticClusteredProfileFactory"]/property[@name="bindingsURI"]/text()', document, XPathConstants.STRING) or \
               xpath.evaluate(r'deployment/bean[@class="org.jboss.system.server.profileservice.repository.StaticProfileFactory"]/property[@name="bindingsURI"]/text()', document, XPathConstants.STRING)

    def parseBindingSetConfiguration(self, content, bindingSetName):
        ''' ServiceBindingSet beans keeps configuration of defaultHost and portOffset
        @types: str, str -> digit, str
        @resource-file: bindings.xml
        '''
        portOffset= defaultHost = None
        document = self._buildDocumentForXpath(content, namespaceAware = 0)
        xpath = self._getXpath()
        bindingSetNodes = xpath.evaluate(r'deployment/bean[@class="org.jboss.services.binding.impl.ServiceBindingSet"]/constructor', document, XPathConstants.NODESET)
        for bindingSetIndex in range(0, bindingSetNodes.getLength()):
            name = xpath.evaluate(r'parameter[1]', bindingSetNodes.item(bindingSetIndex), XPathConstants.STRING)
            if name == bindingSetName:
                defaultHost = xpath.evaluate(r'parameter[2]', bindingSetNodes.item(bindingSetIndex), XPathConstants.STRING)
                portOffset = xpath.evaluate(r'parameter[3]', bindingSetNodes.item(bindingSetIndex), XPathConstants.STRING)
        return portOffset, defaultHost

    def parseMetadataSetConfiguration(self, content, bindingConfigName):
        ''' Parse service bindings from BindingManager config
        @types: str, str -> list(ServerSocketDescriptor)
        @resource-file: bindings.xml
        '''
        bindings = []
        document = self._buildDocumentForXpath(content, namespaceAware = 0)
        xpath = self._getXpath()
        bindingsNodes = xpath.evaluate(''.join([r'deployment/bean[@name="', bindingConfigName, r'"]/constructor/parameter[1]/set/bean[@class="org.jboss.services.binding.ServiceBindingMetadata"]']), document, XPathConstants.NODESET)
        for bindingsIndex in range(0, bindingsNodes.getLength()):
            host = xpath.evaluate(r'parameter[1]/text()', bindingsNodes.item(bindingsIndex), XPathConstants.STRING)
            port = xpath.evaluate(r'property[@name="port"]/text()', bindingsNodes.item(bindingsIndex), XPathConstants.STRING)
            if port:
                binding = ServerSocketDescriptor(port, host)
                bindings.append(binding)
        return bindings


class ServerConfigParserV6(ServerConfigParserV5):
    ''' Parser for JBoss 6.0 - 6.1 similar to Paser Jboss 5.x,
    also there are changes in JMS config file parsing '''

    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        '''
        return trait.majorVersion.value() == 6

    def parseDestinationsService(self, content):
        '''
        @str -> jboss.DestinationServiceDescriptor
        @resource-file: hornetq-jms.xml
        '''
        destinationTypeBySignature = {
            'queue' : jms.Queue,
            'topic' : jms.Topic
        }
        descriptor = DestinationServiceDescriptor()
        document = self._buildDocumentForXpath(content, namespaceAware = 0)
        xpath = self._getXpath()
        destinationNodes = xpath.evaluate(r'configuration/topic | configuration/queue', document, XPathConstants.NODESET)
        for nodeIndex in range(0, destinationNodes.getLength()):
            destination = destinationNodes.item(nodeIndex)
            destinationType = destination.getNodeName()
#            logger.debug('=== Destination Type: %s' % destinationType)
            destinationName = destination.getAttribute('name')
#            logger.debug('=== Destination Name: %s' % destinationName)
            destinationJndiName = xpath.evaluate(r'entry/@name', destination, XPathConstants.STRING)
#            logger.debug('=== Destination JNDI: %s' % destinationJndiName)
            destinationClass = destinationTypeBySignature.get(destinationType)
            if destinationClass:
                jmsDestination = destinationClass(destinationName)
                jmsDestination.setJndiName(destinationJndiName)
                descriptor.addJmsDestinations(jmsDestination)
        return descriptor


class SystemProperties(UserDict.UserDict):

    def resolveProperty(self, property_):
        if property_:
            propertiesCount = len(re.findall('\$\{', property_))
            if propertiesCount:
                name = value = defaultValue = None
                before = ''
                after = ''
                if re.match('(.+)?\$\{[^\${^/}]+\:.+\}(.+)?', property_): # default value exists:
                    m = re.match('(.+)?\$\{([^\${^/}])+\:(.+)?\}(.+)?', property_)
                    before = m.group(1)
                    name = m.group(2)
                    defaultValue = m.group(3)
                    after = m.group(4)
                elif re.match('(.+)?\$\{([^\${^/}]+)\}(.+)?', property_): # only propertyName exists:
                    m = re.match('(.+)?\$\{([^\${^/}]+)\}(.+)?', property_)
                    before = m.group(1)
                    name = m.group(2)
                    after = m.group(3)
                if name: # get value from serverProperties:
                    #TODO: add exception handling
                    value = self.get(name)
                if defaultValue and not value: # apply default value from property
                    value = defaultValue
                if value:
                    if before: value = ''.join([before, value])
                    if after: value = ''.join([value, after])
                else:#failed to get value for property, returning initial property view
                    value = property_
                unresolvedPropertiesCount = len(re.findall('\$\{', value))
                if unresolvedPropertiesCount == 0 or propertiesCount == unresolvedPropertiesCount:
                    return value
                else:
                    return self.resolveProperty(value)
        return property_

    def getSystemPropertyByCmdLineOption(self, option):
        ''' Transform some JBoss cmd-line params to JBoss system properties,
        e.g. '-b' to 'jboss.bind.address'
        @types: str -> str, str or None '''
        systemPropertyName = None
        systemPropertyValue = None
        optionName = option.getName()
        optionValue = option.getValue()
        # long options definition
        if optionName.startswith('--'):
            if optionName == '--configuration': systemPropertyName = 'jboss.server.name'
            elif optionName == '--partition': systemPropertyName = 'jboss.partition.name'
            elif optionName == '--udp': systemPropertyName = 'jboss.partition.udpGroup'
            elif optionName == '--mcast_port': systemPropertyName = 'jboss.partition.udpPort'
            elif optionName == '--hostname': systemPropertyName = 'jboss.host.name'
            elif optionName == '--nodename': systemPropertyName = 'jboss.node.name'
            elif optionName == '--main-address': systemPropertyName = 'jboss.domain.main.address'
            elif optionName == '--main-port': systemPropertyName = 'jboss.domain.main.port'
            elif optionName == '--host': systemPropertyName = 'jboss.bind.address'
        # short options definition
        elif optionName.startswith('-'):
            # cut possible value from know option names in case it defined without space
            systemPropertyValue = optionName[2:]
            if optionName.startswith('-c') \
                and not optionName.startswith('-classpath') \
                and not optionName.startswith('-cp'):
                    systemPropertyName = 'jboss.server.name'
            elif optionName.startswith('-b'): systemPropertyName = 'jboss.bind.address'
            elif optionName == '-g': systemPropertyName = 'jboss.partition.name'
            elif optionName == '-u': systemPropertyName = 'jboss.partition.udpGroup'
            elif optionName == '-m': systemPropertyName = 'jboss.partition.udpPort'
            elif optionName == '-H': systemPropertyName = 'jboss.host.name'
            elif optionName == '-N': systemPropertyName = 'jboss.node.name'
        return systemPropertyName, systemPropertyValue or optionValue

    def getFilePathFromURLValue(self, value):
        ''' If property value is URL transorm it to path, e.g. 'file:/C:\jboss.properties' to 'C:\jboss.properties'
        @types: str -> str '''
        try:
            path = URL(value).getFile()
            # cut slash from begin of path on Windows:
            if path and path[2] == ':': path = path[1:]
        except MalformedURLException: # take path as is:
            path = value
        return path

class ServerConfigDescriptorV7:
    ''' Dataobjects placeholder for entities of JBoss v7 configuration files:
        standalone.xml, host.xml, domain.xml '''

    class DomainController:
        ''' Represents part of configuration of host controller, that define a role of host controller:
            a) managed by remote domain controller or
            b) act this host controller as domain controller '''

        class Type:
            LOCAL = 'local'
            REMOTE = 'remote'

        def __init__(self, type_, remoteHost = None, remotePort = None):
            ''' @types: ServerConfigDescriptorV7.DomainController.Type, str, str '''
            assert type_
            self.__type = type_
            self.__remoteHost = remoteHost
            self.__remotePort = remotePort

        def __repr__(self):
            return 'DomainController(type=%s, remoteHost=%s, remotePort=%s)' % \
                    (self.__type, self.__remoteHost, self.__remotePort)

        def getType(self):
            r'@types: -> ServerConfigDescriptorV7.DomainController.Type'
            return self.__type

        def getRemoteHost(self):
            r'''@types: -> str
            May be ip, hostname or config-expression like: host="${jboss.domain.main.address}" '''
            return self.__remoteHost

        def getRemotePort(self):
            r'''@types: -> str
            May be digit or config expression like: port="${jboss.domain.main.port:9999}" '''
            return self.__remotePort

    class Interface(entity.HasName):
        ''' Named network interfaces. The interfaces may or may not be fully specified
             (i.e. include criteria on how to determine their IP address.)
            Can be defined in: standalone, managed server, domain, host-controller configuration '''

        def __init__(self, name, inetAddress = None, nicName = None):
            ''' @types: str, str, str '''
            assert name
            self.setName(name)
            self.__inetAddress = inetAddress
            self.__nicName = nicName

        def __repr__(self):
            return 'Interface(name=%s, inetAddress=%s, nicName=%s)' % \
                    (self.getName(), self.__inetAddress, self.__nicName)

        def getInetAddress(self):
            r'@types: -> str'
            return self.__inetAddress

        def getNicName(self):
            r'@types: -> str'
            return self.__nicName

    class SocketBinding(entity.HasName):
        ''' Configuration information for a socket defined inside socketBindingGroup'''

        def __init__(self, name, interfaceName = None, port = None, \
                     fixedPort = None, multicastAddress = None, multicastPort = None):
            ''' @types: str, str, str, str, str, str
            @param interfaceName: Name of the declared interface to which the socket should be bound.
            @param port: May be str, because can consist system property expression,
                         like port="${jboss.management.native.port:9999}"
            @param fixedPort: Value is string: "true" or "false".
                              Whether the port value should remain fixed even if numerically
                              offsets are applied to the other sockets in the socket group
            @param multicastPort: May be str, because can consist system property expression,
                                  like port="${jboss.management.native.port:9999}" '''
            assert name
            self.setName(name)
            self.__interfaceName = interfaceName
            self.__port = port
            self.__fixedPort = fixedPort
            self.__multicastAddress = multicastAddress
            self.__multicastPort = multicastPort

        def __repr__(self):
            return 'SocketBinding(name=%s, interfaceName=%s, port=%s, \
                    fixedPort=%s, multicaseAddress=%s, multicastPort=%s)' % \
                    (self.getName(), self.__interfaceName, self.__port, \
                     self.__fixedPort, self.__multicastAddress, self.__multicastPort)

        def getPort(self):
            r'@types: -> str'
            return self.__port

        def getInterfaceName(self):
            r'@types: -> str'
            return self.__interfaceName

        def getFixedPort(self):
            r'@types: > str'
            return self.__fixedPort

        def isFixedPort(self):
            r'@types: -> bool'
            return self.__fixedPort == 'true'

        def getMulticastAddress(self):
            r'@types: -> str'
            return self.__multicastAddress

        def getMulticastPort(self):
            r'@types: -> str'
            return self.__multicastPort

    class SocketBindingGroup(entity.HasName):
        ''' Contains a list of socket configurations
        defaultInterfase - name of an interface, that should be used as
        the interface for any sockets that do not explicitly declare one.
        Can be defined in: standalone or domain configuration.
        Server-group and managed server may be referenced to SocketBindingGroup '''

        def __init__(self, name, defaultInterfaceName, portOffset = None, bindings = None):
            ''' @types: str, str, str, list(ServerConfigDescriptorV7.SocketBinding)
            @param portOffset: May be str, because can consist system property expression,
                               like port-offset="${jboss.socket.binding.port-offset:0}" '''
            assert name and defaultInterfaceName
            self.setName(name)
            self.__defaultInterfaceName = defaultInterfaceName
            # portOffset make sense in case of standalone server, for domain portOffset defined in serverGroup
            self.__portOffset = portOffset
            self.__bindings = []
            if bindings: self.__bindings.extend(bindings)

        def __repr__(self):
            return 'SocketBindingGroup(name=%s, defaultInterface=%s, \
                    portOffset=%s, bindings=%s)' % \
                    (self.getName(), self.__defaultInterfaceName, \
                     self.__portOffset, self.__bindings)

        def getDefaultInterfaceName(self):
            r'@types: -> str'
            return self.__defaultInterfaceName

        def getPortOffset(self):
            r'@types: -> str'
            return self.__portOffset

        def getBindings(self):
            r'@types: -> list(ServerConfigDescriptorV7.SocketBinding)'
            return self.__bindings

    class Profile:
        ''' Contains a list of subsystems.Standalone server has only single profile.
        Managed servers from the same group use the same profile. A profile
        may include unique configuration elements from other profiles.
        Profiles be defined in: standalone or domain configuration.
        Server-group has reference to profile '''

        def __init__(self, name = None, datasources = None, \
                     jmsResources = None, includedProfilesNames = None):
            ''' @types: str, list(jee.Datasource), list(jms.Datasource), list(str) '''
            self.__name = name
            self.__datasources = []
            if datasources: self.__datasources.extend(datasources)
            self.__jmsResources = []
            if jmsResources: self.__jmsResources.extend(jmsResources)
            self.__includedProfilesNames = []
            if includedProfilesNames: self.__includedProfilesNames.extend(includedProfilesNames)

        def __repr__(self):
            return 'Profile(name=%s, datasources=%s, \
                    jmsResources=%s, includedProfilesNames=%s)' % \
                    (self.__name, self.__datasources, \
                     self.__jmsResources, self.__includedProfilesNames)

        def getName(self):
            r'@types: -> str'
            return self.__name

        def getDatasources(self):
            r'@types: -> list(jee.Datasource)'
            return self.__datasources

        def getJmsResources(self):
            r'@types: -> list(jms.Datasource)'
            return self.__jmsResources

        def getIncludedProfilesNames(self):
            r'@types: -> list(str)'
            return self.__includedProfilesNames

        def addJmsResource(self, resource):
            ''' @types: jms.Datasource '''
            if resource: self.__jmsResources.append(resource)

        def addDatasource(self, datasource):
            ''' @types: jee.Datasource '''
            if datasource: self.__datasources.append(datasource)


    class ServerGroup(entity.HasName):
        ''' Represents group of managed servers.
        Each server group may link with separate profile, socket binding group, applications.
        Defined in domain configuration. '''

        def __init__(self, name, profileName, socketBindingGroupName, applications = None, systemProperties = None):
            ''' @types: str, str, str, list(jee.Application), dict[str, str] '''
            assert name and profileName and socketBindingGroupName
            self.setName(name)
            self.__profileName = profileName
            self.__socketBindingGroupName = socketBindingGroupName
            self.__applications = []
            if applications: self.__applications.extend(applications)
            self.__systemProperties = {}
            if systemProperties: self.__systemProperties.update(systemProperties)

        def __repr__(self):
            return 'ServerGroup(name=%s, profileName=%s, socketBindingGroupName=%s, \
                    applications=%s, systemProperties=%s)' % \
                    (self.getName(), self.__profileName, self.__socketBindingGroupName, \
                     self.__applications, self.__systemProperties)

        def getProfileName(self):
            r'@types: -> str'
            return self.__profileName

        def getSocketBindingGroupName(self):
            r'@types: -> str'
            return self.__socketBindingGroupName

        def getApplications(self):
            r'@types: -> list(jee.Application)'
            return self.__applications

        def getSystemProperties(self):
            r'@types: -> dict[str, str]'
            return self.__systemProperties


    class StandaloneServerConfig:
        ''' Represents root element for a document specifying the configuration
            of a single "standalone" server that does not operate as part of a domain.'''

        def __init__(self, serverName = None, systemProperties = None, \
                     managementEndpoints = None, profile = None, interfaces = None, \
                     socketBindingGroup = None, applications = None):
            ''' @types: str, dict[str, str], list(ServerConfigDescriptorV7.SocketBinding), ServerConfigDescriptorV7.Profile, list(ServerConfigDescriptorV7.Interface), ServerConfigDescriptorV7.SocketBindingGroup, list(jee.Application) '''
            # serverName may be not defined, then take it from InetAddress.getLocalHost().getHostName()
            self.__serverName = serverName
            self.__systemProperties = {}
            if systemProperties: self.__systemProperties.update(systemProperties)
            self.__managementEndpoints = []
            if managementEndpoints: self.__managementEndpoints.extend(managementEndpoints)
            self.__profile = profile
            self.__interfaces = []
            if interfaces: self.__interfaces.extend(interfaces)
            self.__socketBindingGroup = socketBindingGroup
            self.__applications = []
            if applications: self.__applications.extend(applications)

        def __repr__(self):
            return 'StandaloneServerConfig(serverName=%s, systemProperties=%s, \
                    managementEndpoints=%s, profile=%s, interfaces=%s, \
                    socketBindingGroup=%s, applications=%s)' % \
                    (self.__serverName, self.__systemProperties, \
                     self.__managementEndpoints, self.__profile, self.__interfaces, \
                     self.__socketBindingGroup, self.__applications)

        def getServerName(self):
            r'@types: -> str'
            return self.__serverName

        def getSystemProperties(self):
            r'@types: -> dict[str, str]'
            return self.__systemProperties

        def getManagementEndpoints(self):
            r'@types: -> list(ServerConfigDescriptorV7.SocketBinding)'
            return self.__managementEndpoints

        def getProfile(self):
            r'@types: -> ServerConfigDescriptorV7.Profile'
            return self.__profile

        def getInterfaces(self):
            r'@types: -> list(ServerConfigDescriptorV7.Interface)'
            return self.__interfaces

        def getSocketBindingGroup(self):
            r'@types: -> ServerConfigDescriptorV7.SocketBindingGroup'
            return self.__socketBindingGroup

        def getApplications(self):
            r'@types: -> list(jee.Application)'
            return self.__applications

    class ManagedServer:
        ''' Represents part of the configuration of a server that operates as part of a domain. '''

        def __init__(self, serverName, serverGroupName, interfaces = None, \
                     socketBindingGroupName = None, portOffset = 0, systemProperties = None):
            ''' @types: str, str, list(ServerConfigDescriptorV7.Interface), str, digit, dict[str, str] '''
            assert serverName and serverGroupName
            self.__serverName = serverName
            self.__serverGroupName = serverGroupName
            self.__interfaces = []
            if interfaces: self.__interfaces.extend(interfaces)
            self.__socketBindingGroupName = socketBindingGroupName
            self.__portOffset = entity.WeakNumeric(int)
            self.__portOffset.set(portOffset)
            self.__systemProperties = {}
            if systemProperties: self.__systemProperties.update(systemProperties)

        def __repr__(self):
            return 'ManagedServer(serverName=%s, serverGroupName=%s, interfaces=%s, \
                    socketBindingGroupName=%s, portOffset=%s, systemProperties=%s)' % \
                    (self.__serverName, self.__serverGroupName, self.__interfaces, \
                     self.__socketBindingGroupName, self.__portOffset, self.__systemProperties)

        def getServerName(self):
            r'@types: -> str'
            return self.__serverName

        def getServerGroupName(self):
            r'@types: -> str'
            return self.__serverGroupName

        def getInterfaces(self):
            r'@types: -> list(ServerConfigDescriptorV7.Interface)'
            return self.__interfaces

        def getSocketBindingGroupName(self):
            r'@types: -> str'
            return self.__socketBindingGroupName

        def getPortOffset(self):
            r'@types: -> entity.WeakNumeric'
            return self.__portOffset.value()

        def getSystemProperties(self):
            r'@types: -> dict[str, str]'
            return self.__systemProperties

    class HostControllerConfig:
        ''' Represents host controller configuration and
            the group of servers under the control of that host controller.
            The standard usage would be for a domain to have one such host controller
            on each physical (or virtual) host machine. '''

        def __init__(self, domainController, hostControllerName = None, systemProperties = None, \
                     managementBindings = None, interfaces = None, managedServers = None):
            ''' @types: ServerConfigDescriptorV7.DomainController, str, dict[str, str], list(ServerConfigDescriptorV7.SocketBinding), list(ServerConfigDescriptorV7.Interface), list(ServerConfigDescriptorV7.ManagedServer) '''
            assert domainController
            self.__domainController = domainController
            # name may be not defined, then take it from InetAddress.getLocalHost().getHostName()
            self.__hostControllerName = hostControllerName
            self.__systemProperties = {}
            if systemProperties: self.__systemProperties.update(systemProperties)
            self.__managementBindings = []
            if managementBindings: self.__managementBindings.extend(managementBindings)
            self.__interfaces = []
            if interfaces: self.__interfaces.extend(interfaces)
            self.__managedServers = []
            if managedServers: self.__managedServers.extend(managedServers)

        def __repr__(self):
            return 'HostControllerConfig(domainController=%s, hostControllerName=%s, systemProperties=%s, \
                    ManagementBindings=%s, interfaces=%s, managedServers=%s)' % \
                    (self.__domainController, self.__hostControllerName, self.__systemProperties, \
                     self.__managementBindings, self.__interfaces, self.__managedServers)

        def getDomainController(self):
            r'@types: -> ServerConfigDescriptorV7.DomainController'
            return self.__domainController

        def getHostControllerName(self):
            r'@types: -> str'
            return self.__hostControllerName

        def getSystemProperties(self):
            r'@types: -> dict[str, str]'
            return self.__systemProperties

        def getManagementBindings(self):
            r'@types: -> list(ServerConfigDescriptorV7.SocketBinding)'
            return self.__managementBindings

        def getInterfaces(self):
            r'@types: -> list(ServerConfigDescriptorV7.Interface)'
            return self.__interfaces

        def getManagedServers(self):
            r'@types: -> list(ServerConfigDescriptorV7.ManagedServer)'
            return self.__managedServers


    class DomainConfig:
        ''' Represents core configuration for the servers in a domain,
            available to the host controller that is configured
            to act as the domain controller. '''

        def __init__(self, systemProperties = None, profiles = None, interfaces = None, \
                     socketBindingGroups = None, serverGroups = None):
            ''' @types: dict[str, str], list(ServerConfigDescriptorV7.Profile), list(ServerConfigDescriptorV7.Interface), list(ServerConfigDescriptorV7.SocketBindingGroup), list(ServerConfigDescriptorV7.ServerGroup) '''
            self.__systemProperties = {}
            if systemProperties: self.__systemProperties.update(systemProperties)
            self.__profiles = []
            if profiles: self.__profiles.extend(profiles)
            self.__interfaces = []
            if interfaces: self.__interfaces.extend(interfaces)
            self.__socketBindingGroups = []
            if socketBindingGroups: self.__socketBindingGroups.extend(socketBindingGroups)
            self.__serverGroups = []
            if serverGroups: self.__serverGroups.extend(serverGroups)

        def __repr__(self):
            return 'DomainConfig(systemProperties=%s, profiles=%s, interfaces=%s, \
                    socketBindingGroups=%s, serverGroups=%s)' % \
                    (self.__systemProperties, self.__profiles, self.__interfaces, \
                     self.__socketBindingGroups, self.__serverGroups)

        def getSystemProperties(self):
            r'@types: -> dict[str, str]'
            return self.__systemProperties

        def getProfiles(self):
            r'@typs: list(ServerConfigDescriptorV7.Profile)'
            return self.__profiles

        def getInterfaces(self):
            r'@typs: -> list(ServerConfigDescriptorV7.Interface)'
            return self.__interfaces

        def getSocketBindingGroups(self):
            r'@typs: -> list(ServerConfigDescriptorV7.SocketBindingGroup)'
            return self.__socketBindingGroups

        def getServerGroups(self):
            r'@typs: -> list(ServerConfigDescriptorV7.ServerGroup)'
            return self.__serverGroups

class ServerConfigParserV7(entity.HasPlatformTrait, jee_discoverer.BaseXmlParser):
    ''' JBoss 7 configuration files: domain.xml, host.xml and standalone.xml parsers '''

    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool '''
        return trait.majorVersion.value() >= 7

    def parseSystemProperties(self, propertiesNodes):
        ''' Parse system properties of domain, host, server-group or server from domain.xml or host.xml or standalone.xml config files
        @types: XPathConstants.NODESET -> dict(name, value) '''
        properties = {}
#        logger.debug('=== parseSystemProperties ||| found system properties: %s' % propertiesNodes.getLength())
        for propertyIndex in range(0, propertiesNodes.getLength()):
            propertyNode = propertiesNodes.item(propertyIndex)
            name = propertyNode.getAttribute('name')
            value = propertyNode.getAttribute('value')
            properties[name] = value
#        logger.debug('+++ properties: %s' % properties)
        return properties

    def parseManagementBindings(self, interfaceNodes):
        ''' Parse Management Interfaces from host.xml or standalone.xml config files in cases:
        <native-interface interface="management" port="9999" />
        <native-interface><socket interface="webmgmt" port="9999"/></native-interface>
        @types: XPathConstants.NODESET -> list(ServerConfigDescriptorV7.SocketBinding) '''
        managementBindings = []
        interfaceTypeByNodeName = {
            'native-interface' : 'native',
            'http-interface' : 'http'
        }
#        logger.debug('=== parseManagementBindings ||| found interfaces: %s' % interfaceNodes.getLength())
        for interfaceIndex in range(0, interfaceNodes.getLength()):
            interfaceNode = interfaceNodes.item(interfaceIndex)
            name = interfaceTypeByNodeName.get(interfaceNode.getNodeName())
            interface = interfaceNode.getAttribute('interface')
            xpath = self._getXpath()
            if not interface: interface = xpath.evaluate(r'socket/@interface', interfaceNode, XPathConstants.STRING)
            port = interfaceNode.getAttribute('port')
            if not port: port = xpath.evaluate(r'socket/@port', interfaceNode, XPathConstants.STRING)
            managementBinding = ServerConfigDescriptorV7.SocketBinding(name, interface, port)
#            logger.debug('=== parseManagementInterface ||| managementInterface: %s' % managementBinding)
            managementBindings.append(managementBinding)
#        logger.debug('+++ managementBindings: %s' % managementBindings)
        return managementBindings

    def parseProfiles(self, profileNodes):
        ''' Parse Profiles from domain.xml or standalone.xml config files
        @types: XPathConstants.NODESET -> list(ServerConfigDescriptorV7.Profile) '''
        profileByName = {}
        # fill full list of profiles and their root resources:
        for profileIndex in range(0, profileNodes.getLength()):
            profileNode = profileNodes.item(profileIndex)
            name = profileNode.getAttribute('name')
            includedProfilesNames = []
            xpath = self._getXpath()
            includedProfilesNamesNodes = xpath.evaluate('include', profileNode, XPathConstants.NODESET)
            for includedIndex in range(0, includedProfilesNamesNodes.getLength()):
                includeProfileName = includedProfilesNamesNodes.item(includedIndex).getAttribute('profile')
                if includeProfileName: includedProfilesNames.append(includeProfileName)
            datasources = self.parseDatasources(profileNode)
            jmsResources = self.parseJmsResources(profileNode)
            profile = ServerConfigDescriptorV7.Profile(name, datasources, jmsResources, includedProfilesNames)
            profileByName[name] = profile
        # mix included profile resources to profiles:
        profiles = profileByName.values()
        for profile in profiles:
            for includedProfile in profile.getIncludedProfilesNames():
                includedProfileJmsResources = profileByName[includedProfile].getJmsResources()
                if includedProfileJmsResources:
                    for resource in includedProfileJmsResources:
                        profile.addJmsResource(resource)
                includedProfileDatasources = profileByName[includedProfile].getDatasources()
                if includedProfileDatasources:
                    for datasource in includedProfileDatasources:
                        profile.addDatasource(datasource)
        return profiles

    def parseDatasources(self, profileNode):
        jeeDatasources = []
        jeeDatasources.extend(self.parseNonXADatasources(profileNode))
        jeeDatasources.extend(self.parseXADatasources(profileNode))
        return jeeDatasources

    def parseNonXADatasources(self, profileNode):
        ''' Parse JEE non-XA Datasources from domain.xml or standalone.xml config files
        @types: XPathConstants.NODESET -> list(jee.Datasource) '''
        nonXADatasources = []
        xpath = self._getXpath()
        datasourcesNodes = xpath.evaluate(r'subsystem/datasources/datasource', profileNode, XPathConstants.NODESET)
#        if datasourceNodes.getLength() != 0: logger.debug('=== parseNonXADatasources ||| found datasources: %s' % datasourceNodes.getLength())
        for datasourceIndex in range(0, datasourcesNodes.getLength()):
            datasourceNode = datasourcesNodes.item(datasourceIndex)
            jndiName = datasourceNode.getAttribute('jndi-name')
            datasource = jee.Datasource(jndiName)
            datasource.setJndiName(jndiName)
            datasource.url = xpath.evaluate('connection-url', datasourceNode, XPathConstants.STRING)
            datasource.driverClass = xpath.evaluate('driver', datasourceNode, XPathConstants.STRING)
            #TODO: add driver parsing
            datasource.userName = xpath.evaluate('security/user-name', datasourceNode, XPathConstants.STRING)
#            logger.debug('=== parseNonXADatasources ||| datasource: %s' % datasource)
            nonXADatasources.append(datasource)
#        logger.debug('+++ datasources: %s' % datasources)
        return nonXADatasources

    def parseXADatasources(self, profileNode):
        ''' Parse XA Datasources from domain.xml or standalone.xml config files
        @types: XPathConstants.NODESET -> list(jee.Datasource) '''
        XADatasources = []
        xpath = self._getXpath()
        XADatasourcesNodes = xpath.evaluate(r'subsystem/datasources/xa-datasource', profileNode, XPathConstants.NODESET)
#        if datasourceNodes.getLength() != 0: logger.debug('=== parseXADatasources ||| found datasources: %s' % datasourceNodes.getLength())
        for XADatasourceIndex in range(0, XADatasourcesNodes.getLength()):
            XADatasourceNode = XADatasourcesNodes.item(XADatasourceIndex)
            jndiName = XADatasourceNode.getAttribute('jndi-name')
            connectionUrl = xpath.evaluate(r'connection-url', XADatasourceNode, XPathConstants.STRING) or \
                            xpath.evaluate(r"xa-datasource-property[@name='URL']", XADatasourceNode, XPathConstants.STRING)
            urlDelimiter = xpath.evaluate(r'url-delimiter', XADatasourceNode, XPathConstants.STRING)
            separatedUrls = []
            # JBoss admin-console place properties with tab-indent, strip them
            connectionUrl = connectionUrl and connectionUrl.strip()
            if connectionUrl:
                separatedUrls.extend(urlDelimiter
                                     # split url by delimeter:
                                     and re.split(re.escape(urlDelimiter), connectionUrl)
                                     or (connectionUrl,))
            for url in separatedUrls:
                datasource = jee.Datasource(jndiName)
                datasource.setJndiName(jndiName)
                datasource.url = url
                datasource.driverClass = xpath.evaluate('driver', XADatasourceNode, XPathConstants.STRING)
                #TODO: add driver parsing
                datasource.userName = xpath.evaluate('security/user-name', XADatasourceNode, XPathConstants.STRING)
#                logger.debug('=== parseXADatasources ||| datasource: %s' % datasource)
                XADatasources.append(datasource)
#        logger.debug('+++ datasources: %s' % datasources)
        return XADatasources

    def parseJmsResources(self, profileNode):
        ''' Parse JMS resources (topics and queues) from HornetQ (JBoss built-in jms) config in domain.xml or standalone.xml config files
        @types: XPathConstants.NODESET -> list(jms.Datasource) '''
        jmsResources = []
        xpath = self._getXpath()
        jmsDatasourceNode = xpath.evaluate(r'subsystem/hornetq-server', profileNode, XPathConstants.NODE)
        if jmsDatasourceNode:
            jmsDatasource = jms.Datasource('hornetq-server')
            for queue in self.parseJmsQueues(jmsDatasourceNode): jmsDatasource.addDestination(queue)
            for topic in self.parseJmsTopics(jmsDatasourceNode): jmsDatasource.addDestination(topic)
            jmsResources.append(jmsDatasource)
        return jmsResources

    def parseJmsQueues(self, jmsDatasourceNode):
        ''' Parse HornetQ JMS Queues
        @types: XPathConstants.NODESET -> list(jms.Queue) '''
        jmsQueues = []
        xpath = self._getXpath()
        jmsQueuesNodes = xpath.evaluate(r'jms-destinations/jms-queue', jmsDatasourceNode, XPathConstants.NODESET)
        for queueIndex in range(0, jmsQueuesNodes.getLength()):
            queueNode = jmsQueuesNodes.item(queueIndex)
            name = queueNode.getAttribute('name')
            jndiName = xpath.evaluate('entry/@name', queueNode, XPathConstants.STRING)
            queue = jms.Queue(name)
            queue.setJndiName(jndiName)
            jmsQueues.append(queue)
        return jmsQueues

    def parseJmsTopics(self, jmsDatasourceNode):
        ''' Parse HornetQ JMS Topics
        @types: XPathConstants.NODESET -> list(jms.Topic) '''
        jmsTopics = []
        xpath = self._getXpath()
        jmsTopicsNodes = xpath.evaluate(r'jms-destinations/jms-topic', jmsDatasourceNode, XPathConstants.NODESET)
        for topicIndex in range(0, jmsTopicsNodes.getLength()):
            topicNode = jmsTopicsNodes.item(topicIndex)
            name = topicNode.getAttribute('name')
            jndiName = xpath.evaluate('entry/@name', topicNode, XPathConstants.STRING)
            topic = jms.Topic(name)
            topic.setJndiName(jndiName)
            jmsTopics.append(topic)
        return jmsTopics

    def parseInterfaces(self, interfaceNodes):
        ''' Parse Interfaces from host.xml or standalone.xml config files
        @types: XPathConstants.NODESET -> list(ServerConfigDescriptorV7.Interface) '''
        interfaces = []
#        logger.debug('=== parseInterfaces ||| found interfaces: %s' % interfaceNodes.getLength())
        for interfaceIndex in range(0, interfaceNodes.getLength()):
            interfaceNode = interfaceNodes.item(interfaceIndex)
            interfaceName = interfaceNode.getAttribute('name')
            xpath = self._getXpath()
            inetAddress = xpath.evaluate(r'inet-address/@value', interfaceNode, XPathConstants.STRING)
            nicName = xpath.evaluate(r'nic/@name', interfaceNode, XPathConstants.STRING)
            interface = ServerConfigDescriptorV7.Interface(interfaceName, inetAddress, nicName)
#            logger.debug('=== parseInterfaces ||| interface: %s' % interface)
            interfaces.append(interface)
#        logger.debug('+++ interfaces: %s' % interfaces)
        return interfaces

    def resolveInterface(self, interface, systemProperties):
        return ServerConfigDescriptorV7.Interface(interface.getName(),
                systemProperties.resolveProperty(interface.getInetAddress()),
                interface.getNicName())

    def parseSocketBindings(self, socketBindingNodes):
        ''' Parse Socket Bindings from domain.xml or standalone.xml config files
        @types: XPathConstants.NODESET -> list(ServerConfigDescriptorV7.SocketBinding) '''
        socketBindings = []
#        logger.debug('=== parseSocketBindings ||| found socket-bindings: %s' % socketBindingNodes.getLength())
        for socketBindingIndex in range(0, socketBindingNodes.getLength()):
            socketBindingNode = socketBindingNodes.item(socketBindingIndex)
            name = socketBindingNode.getAttribute('name')
            interfaceName = socketBindingNode.getAttribute('interface')
            port = socketBindingNode.getAttribute('port')
            fixedPort = socketBindingNode.getAttribute('fixed-port')
            multicastAddress = socketBindingNode.getAttribute('multicast-address')
            multicastPort = socketBindingNode.getAttribute('multicast-port')
            socketBinding = ServerConfigDescriptorV7.SocketBinding(name, interfaceName, port, fixedPort, multicastAddress, multicastPort)
#            logger.debug('=== parseSocketBindings ||| binding: %s' % socketBinding)
            socketBindings.append(socketBinding)
#        logger.debug('+++ socketBindings: %s' % socketBindings)
        return socketBindings

    def resolveSocketBinding(self, socketBinding, systemProperties):
            # resolve port from expression to value
            return  ServerConfigDescriptorV7.SocketBinding(
                     socketBinding.getName(),
                     socketBinding.getInterfaceName(),
                     systemProperties.resolveProperty(socketBinding.getPort()),
                     socketBinding.getFixedPort(),
                     socketBinding.getMulticastAddress(),
                     socketBinding.getMulticastPort())


    def parseSocketBingingGroups(self, socketBindingGroupNodes):
        ''' Parse Socket Binding Groups from domain.xml or standalone.xml config files
        @types: XPathConstants.NODESET -> list(ServerConfigDescriptorV7.SocketBindingGroup) '''
        socketBindingGroups = []
#        logger.debug('=== parseSocketBingingGroups ||| found socket-binding groups: %s' % socketBindingGroupNodes.getLength())
        for socketBindingGroupIndex in range(0, socketBindingGroupNodes.getLength()):
            socketBindingGroupNode = socketBindingGroupNodes.item(socketBindingGroupIndex)
            name = socketBindingGroupNode.getAttribute('name')
            defaultInterface = socketBindingGroupNode.getAttribute('default-interface')
            portOffset = socketBindingGroupNode.getAttribute('port-offset')
            bindingsNodes = self._getXpath().evaluate('socket-binding', socketBindingGroupNode, XPathConstants.NODESET)
            bindings = self.parseSocketBindings(bindingsNodes)
            socketBindingGroup = ServerConfigDescriptorV7.SocketBindingGroup(name, defaultInterface, portOffset, bindings)
#            logger.debug('=== parseSocketBindingGroups ||| bindingGroup: %s' % socketBindingGroup)
            socketBindingGroups.append(socketBindingGroup)
#        logger.debug('+++ socketBindingGroups: %s' % socketBindingGroups)
        return socketBindingGroups

    def resolveSocketBindingGroup(self, socketBindingGroup, systemProperties):
        # resolve portOffset from expression to value
        return ServerConfigDescriptorV7.SocketBindingGroup(
                socketBindingGroup.getName(),
                socketBindingGroup.getDefaultInterfaceName(),
                systemProperties.resolveProperty(socketBindingGroup.getPortOffset()),
                map(fptools.partiallyApply(self.resolveSocketBinding, fptools._ , systemProperties), socketBindingGroup.getBindings()))

    def parseApplications(self, deploymentNodes):
        ''' Parse JEE Applications with modules (ear with rar + ejb-jar + war)
        @types: XPathConstants.NODESET -> list(jee.Application) '''
        applications = []
        for deploymentIndex in range(0, deploymentNodes.getLength()):
            deploymentNode = deploymentNodes.item(deploymentIndex)
            # name is unique across whole domain, using in domain deployments repository
            name = deploymentNode.getAttribute('name')
            # runtimeName unique deployment name across managed server
            # For example, two different deployments running on different
            # servers in the domain could both have a 'runtime-name' of
            # 'example.war', with one having a 'name' of 'example.war_v1'
            # and another with an 'name' of 'example.war_v2'.
            runtimeName = deploymentNode.getAttribute('runtime-name')
            application = jee.Application(runtimeName)
            xpath = self._getXpath()
            modulesNodes = xpath.evaluate('content | fs-archive | fs-exploded', deploymentNode, XPathConstants.NODESET)
            for moduleIndex in range(0, modulesNodes.getLength()):
                moduleNode = modulesNodes.item(moduleIndex)
                name = moduleNode.getAttribute('root')
                if name: application.addModule(jee.Module(name))
            applications.append(application)
        return applications

    def parseDomainServerGroups(self, serverGroupNodes):
        ''' Parse Server Groups from domain.xml
        @types: XPathConstants.NODESET -> list(ServerConfigDescriptorV7.ServerGroup) '''
        serverGroups = []
#        logger.debug('=== parseServerGroup ||| found server groups: %s' % serverGroupNodes.getLength())
        for serverGroupIndex in range(serverGroupNodes.getLength()):
            serverGroupNode = serverGroupNodes.item(serverGroupIndex)
            name = serverGroupNode.getAttribute('name')
            profileName = serverGroupNode.getAttribute('profile')
            xpath = self._getXpath()
            socketBindingGroupNode = xpath.evaluate(r'socket-binding-group', serverGroupNode, XPathConstants.NODE)
            socketBindingGroupName = None
            if socketBindingGroupNode: socketBindingGroupName = socketBindingGroupNode.getAttribute('ref')
            applicationNodes = xpath.evaluate(r'deployments/deployment', serverGroupNode, XPathConstants.NODESET)
            applications = self.parseApplications(applicationNodes)
            propertiesNodes = xpath.evaluate(r'system-properties/property', serverGroupNode, XPathConstants.NODESET)
            systemProperties = self.parseSystemProperties(propertiesNodes)
            serverGroup = ServerConfigDescriptorV7.ServerGroup(name, profileName, socketBindingGroupName, applications, systemProperties)
#            logger.debug('=== parseDomainServerGroups ||| group: %s' % serverGroup)
            serverGroups.append(serverGroup)
#        logger.debug('+++ serverGroups: %s' % serverGroups)
        return serverGroups

    def parseDomainController(self, domainControllerNodes):
        ''' Parse Domain Controllers from host.xml config file
        @types: XPathConstants.NODESET -> ServerConfigDescriptorV7.DomainController '''
#        logger.debug('=== parseDomainController ||| found domainController: %s' % domainControllerNodes.getLength())
        for domainControllerIndex in range(0, domainControllerNodes.getLength()):
            domainControllerNode = domainControllerNodes.item(domainControllerIndex)
            # type of domain controller: ServerConfigDescriptorV7.DomainController.Type (remote or local)
            dcType = domainControllerNode.getNodeName()
            remoteEndpoint = None

            def resolvePropertyfromNode(property_):
                if property_:
                    propertiesCount = len(re.findall('\$\{', property_))
                    if propertiesCount:
                        name = value = defaultValue = None
                        before = ''
                        after = ''
                        if re.match('(.+)?\$\{[^\${^/}]+\:.+\}(.+)?', property_):  # default value exists:
                            m = re.match('(.+)?\$\{([^\${^/}])+\:(.+)?\}(.+)?', property_)
                            before = m.group(1)
                            name = m.group(2)
                            defaultValue = m.group(3)
                            after = m.group(4)
                        elif re.match('(.+)?\$\{([^\${^/}]+)\}(.+)?', property_):  # only propertyName exists:
                            m = re.match('(.+)?\$\{([^\${^/}]+)\}(.+)?', property_)
                            before = m.group(1)
                            name = m.group(2)
                            after = m.group(3)
                        if defaultValue and not value:  # apply default value from property
                            value = defaultValue
                        if value:
                            if before: value = ''.join([before, value])
                            if after: value = ''.join([value, after])
                        else:  # failed to get value for property, returning initial property view
                            value = property_
                        unresolvedPropertiesCount = len(re.findall('\$\{', value))
                        if unresolvedPropertiesCount == 0 or propertiesCount == unresolvedPropertiesCount:
                            return value
                        else:
                                     # case not handled, should not happens
                            return value
                return property_

            if dcType == ServerConfigDescriptorV7.DomainController.Type.REMOTE:
                remoteEndpoint = netutils.createTcpEndpoint(resolvePropertyfromNode(domainControllerNode.getAttribute('host')),
                                                            resolvePropertyfromNode(domainControllerNode.getAttribute('port')))
                domainController = ServerConfigDescriptorV7.DomainController(dcType, remoteEndpoint.getAddress(), str(remoteEndpoint.getPort()))
            else:
                domainController = ServerConfigDescriptorV7.DomainController(dcType)
#            logger.debug('+++ domainController: %s' % domainController)
            return domainController

    def resolveDomainController(self, domainController, systemProperties):
        return ServerConfigDescriptorV7.DomainController(domainController.getType(),
                                                         systemProperties.resolveProperty(domainController.getRemoteHost()),
                                                         systemProperties.resolveProperty(domainController.getRemotePort()))

    def parseManagedServers(self, serverNodes):
        ''' Parse Managed Server from host.xml config file
        @types: XPathConstants.NODESET -> list(ServerConfigDescriptorV7.ManagedServer) '''
        servers = []
#        logger.debug('=== parseManagedServers ||| found servers: %s' % serverNodes.getLength())
        for serverIndex in range(0, serverNodes.getLength()):
            serverNode = serverNodes.item(serverIndex)
            name = serverNode.getAttribute('name')
            group = serverNode.getAttribute('group')
            xpath = self._getXpath()
            socketBindingGroupNode = xpath.evaluate(r'socket-binding-group', serverNode, XPathConstants.NODE)
            socketBindingGroupName = portOffset = None
            if socketBindingGroupNode:
                socketBindingGroupName = socketBindingGroupNode.getAttribute('ref')
                portOffset = socketBindingGroupNode.getAttribute('port-offset')
            # get managed server interfaces
            interfacesContent = xpath.evaluate(r'interfaces/interface', serverNode, XPathConstants.NODESET)
            interfaces = self.parseInterfaces(interfacesContent)
            # get managed server system properties
            systemPropertiesContent = xpath.evaluate(r'system-properties/property', serverNode, XPathConstants.NODESET)
            systemProperties = self.parseSystemProperties(systemPropertiesContent)
            server = ServerConfigDescriptorV7.ManagedServer(name, group, interfaces, socketBindingGroupName, portOffset, systemProperties)
#            logger.debug('=== parseManagedServers ||| server: %s' % server)
            servers.append(server)
#        logger.debug('+++ servers: %s' % servers)
        return servers

    def resolveManagedServerConfig(self, managedServer, systemProperties):
        return ServerConfigDescriptorV7.ManagedServer(managedServer.getServerName(),
                managedServer.getServerGroupName(),
                map(fptools.partiallyApply(self.resolveInterface, fptools._, systemProperties), managedServer.getInterfaces()),
                managedServer.getSocketBindingGroupName(),
                systemProperties.resolveProperty(str(managedServer.getPortOffset())),
                managedServer.getSystemProperties())

    def parseStandaloneServerConfig(self, content):
        ''' Parse Stanalone Server config file (standalone.xml)
        @types: str -> ServerConfigDescriptorV7.StandaloneServerConfig '''
        document = self._buildDocumentForXpath(content, namespaceAware = 0)
        xpath = self._getXpath()
        serverName = xpath.evaluate(r'server/@name', document, XPathConstants.STRING)
        systemPropertiesContent = xpath.evaluate(r'server/system-properties/property', document, XPathConstants.NODESET)
        managementInterfacesContent = xpath.evaluate(r'server/management/management-interfaces/child::*', document, XPathConstants.NODESET)
        # standalone server has only 1 profile
        profileContent = xpath.evaluate(r'server/profile', document, XPathConstants.NODESET)
        profile = self.parseProfiles(profileContent)[0]
        interfacesContent = xpath.evaluate(r'server/interfaces/interface', document, XPathConstants.NODESET)
        # standalone server has only 1 socketBindingGroup
        socketBindingGroupContent = xpath.evaluate(r'server/socket-binding-group', document, XPathConstants.NODESET)
        socketBindingGroup = self.parseSocketBingingGroups(socketBindingGroupContent)[0]
        deploymentsContent = xpath.evaluate(r'server/deployments/deployment', document, XPathConstants.NODESET)
        return ServerConfigDescriptorV7.StandaloneServerConfig(serverName,
                                                               self.parseSystemProperties(systemPropertiesContent),
                                                               self.parseManagementBindings(managementInterfacesContent),
                                                               profile,
                                                               self.parseInterfaces(interfacesContent),
                                                               socketBindingGroup,
                                                               self.parseApplications(deploymentsContent))

    def resolveStandaloneServerConfig(self, standaloneServerConfig, systemProperties):
        return ServerConfigDescriptorV7.StandaloneServerConfig(
                standaloneServerConfig.getServerName(),
                standaloneServerConfig.getSystemProperties(),
                standaloneServerConfig.getManagementEndpoints(),
                standaloneServerConfig.getProfile(),
                map(fptools.partiallyApply(self.resolveInterface, fptools._, systemProperties), standaloneServerConfig.getInterfaces()),
                self.resolveSocketBindingGroup(standaloneServerConfig.getSocketBindingGroup(), systemProperties),
                standaloneServerConfig.getApplications()
                )

    def parseDomainConfig(self, content):
        ''' Parse Domain config file (domain.xml)
        @types: str -> ServerConfigDescriptorV7.DomainConfig '''
        document = self._buildDocumentForXpath(content, namespaceAware = 0)
        xpath = self._getXpath()
        systemPropertiesContent = xpath.evaluate(r'domain/system-properties/property', document, XPathConstants.NODESET)
        profilesContent = xpath.evaluate(r'domain/profiles/profile', document, XPathConstants.NODESET)
        interfacesContent = xpath.evaluate(r'domain/interfaces/interface', document, XPathConstants.NODESET)
        socketBindingGroupContent = xpath.evaluate(r'domain/socket-binding-groups/socket-binding-group', document, XPathConstants.NODESET)
        serverGroupsContent = xpath.evaluate(r'domain/server-groups/server-group', document, XPathConstants.NODESET)
        return ServerConfigDescriptorV7.DomainConfig(self.parseSystemProperties(systemPropertiesContent),
                                                     self.parseProfiles(profilesContent),
                                                     self.parseInterfaces(interfacesContent),
                                                     self.parseSocketBingingGroups(socketBindingGroupContent),
                                                     self.parseDomainServerGroups(serverGroupsContent))

    def resolveDomainConfig(self, domainConfig, systemProperties):
        return ServerConfigDescriptorV7.DomainConfig(domainConfig.getSystemProperties(),
                domainConfig.getProfiles(),
                map(fptools.partiallyApply(self.resolveInterface, fptools._, systemProperties), domainConfig.getInterfaces()),
                map(fptools.partiallyApply(self.resolveSocketBindingGroup, fptools._, systemProperties), domainConfig.getSocketBindingGroups()),
                domainConfig.getServerGroups())

    def parseHostControllerConfig(self, content):
        ''' Parse Host Controller config file (host.xml)
        @types: str -> ServerConfigDescriptorV7.HostControllerConfig '''
        document = self._buildDocumentForXpath(content, namespaceAware = 0)
        xpath = self._getXpath()
        name = xpath.evaluate(r'host/@name', document, XPathConstants.STRING)
        domainControllerContent = xpath.evaluate(r'host/domain-controller/child::*', document, XPathConstants.NODESET)
        systemPropertiesContent = xpath.evaluate(r'host/system-properties/property', document, XPathConstants.NODESET)
        managementInterfacesContent = xpath.evaluate(r'host/management/management-interfaces/child::*', document, XPathConstants.NODESET)
        interfacesContent = xpath.evaluate(r'host/interfaces/interface', document, XPathConstants.NODESET)
        serversContent = xpath.evaluate(r'host/servers/server', document, XPathConstants.NODESET)
        return ServerConfigDescriptorV7.HostControllerConfig(self.parseDomainController(domainControllerContent),
                                                             name,
                                                             self.parseSystemProperties(systemPropertiesContent),
                                                             self.parseManagementBindings(managementInterfacesContent),
                                                             self.parseInterfaces(interfacesContent),
                                                             self.parseManagedServers(serversContent))

    def resolveHostControllerConfig(self, hostControllerConfig, systemProperties):
        return ServerConfigDescriptorV7.HostControllerConfig(self.resolveDomainController(hostControllerConfig.getDomainController(), systemProperties),
                hostControllerConfig.getHostControllerName(),
                hostControllerConfig.getSystemProperties(),
                map(fptools.partiallyApply(self.resolveSocketBinding, fptools._, systemProperties), hostControllerConfig.getManagementBindings()),
                map(fptools.partiallyApply(self.resolveInterface, fptools._, systemProperties), hostControllerConfig.getInterfaces()),
                hostControllerConfig.getManagedServers())

class SystemPropertiesDiscoverer:
    ''' JBoss system properties can be defined as command-line elements:
        - known command line option, e.g. -b <host>, -c <configName>, etc
        - java properties -D<propName>=<propValue>
        or in the properties file:
        - path specified as cmd-line options: -P or --properties=<url> '''

    def __splitToKeyValuePair(self, property_):
        return property_.split(':', 1)

    def __removeBrackets(self, property_):
        '${property} -> property'
        return property_[2:-1]

    def getPropertiesSet(self, line):
        return sets.Set(re.findall(r'(\$\{.*?\})', line))

    def getPropertyName(self, property_):
        '${propName:defaultValue} -> propName'
        withoutBrackets = self.__removeBrackets(property_)
        if len(self.__splitToKeyValuePair(withoutBrackets)) in (1,2):
            return self.__splitToKeyValuePair(withoutBrackets)[0]

    def getDefaultValue(self, property_):
        '${propName:someDefaultValue} -> someDefaultValue'
        withoutBrackets = self.__removeBrackets(property_)
        if len(self.__splitToKeyValuePair(withoutBrackets)) == 2:
            return self.__splitToKeyValuePair(withoutBrackets)[1]

    def getDefaultValueByName(self, propertiesSet):
        properties = {}
        for property_ in propertiesSet:
            properties[self.getPropertyName(property_)] = self.getDefaultValue(property_)
        return properties

    def resolvedValuesByDefinedProperties(self, propertiesWithDefaultValueByName, serverSystemProperties):
        properties = {}
        for propName in propertiesWithDefaultValueByName.keys():
            if serverSystemProperties.get(propName):
                properties[propName] = serverSystemProperties.get(propName)
            else:
                properties[propName] = propertiesWithDefaultValueByName.get(propName)
        return properties

    def resolveLine(self, lineWithProperties, serverSystemProperties):
        if lineWithProperties:
            resolvedLine = lineWithProperties
            propertiesSet = self.getPropertiesSet(lineWithProperties)
            propertiesWithDefaultValueByName = self.getDefaultValueByName(propertiesSet)
            propertiesWithValueByName = self.resolvedValuesByDefinedProperties(propertiesWithDefaultValueByName, serverSystemProperties)
            for property_ in propertiesSet:
                propertyValue = propertiesWithValueByName.get(self.getPropertyName(property_))
                if propertyValue:
                    resolvedLine = resolvedLine.replace(property_, propertyValue)
                else:
                    logger.debug('Cannot resolve property: ', property_)
            return resolvedLine

    def resolveLineList(self, lineList, systemProperties):
        # resolve each line in list
        fn = fptools.partiallyApply(self.resolveLine, fptools._,
                                    systemProperties)
        return map(fn, lineList)

    def discoverProperties(self, fs, cmdLineElements):
        ''' Calculate dict of JBoss System Properties from cmd-line and Properties File
        @types: str, file_system.FileSystem -> dict[str, str] '''
        serverSystemProperties = SystemProperties()
        for cmdLineOption in cmdLineElements:
            # if option is java Property, just add it to dict:
            if cmdLineOption.getType() == jee.CmdLineElement.Type.JAVA_OPTION:
                propertyName = cmdLineOption.getName()
                serverSystemProperties[propertyName] = cmdLineOption.getValue()
            # if option is JBoss command-line parameter:
            elif cmdLineOption.getType() == jee.CmdLineElement.Type.GENERIC_OPTION:
                # if path or URL to properties file found:
                if cmdLineOption.getName() == '-P' or cmdLineOption.getName() == '--properties':
                    propertyFilePath = serverSystemProperties.getFilePathFromURLValue(cmdLineOption.getValue())
                    try: # get Property File content and parse System Properties
                        content = fs.getFile(propertyFilePath, [file_topology.FileAttrs.CONTENT]).content
                        properties = Properties()
                        properties.load(ByteArrayInputStream(String(content).getBytes()))
                        for propertyName in properties.keySet():
                            serverSystemProperties[propertyName] = properties.get(propertyName)
                    except (Exception, JException):
                        logger.debugException('Failed to get JBoss System Properties from properties file')
                else: # transform other known command-line parameters to System Properties:
                    propertyName, propertyValue = serverSystemProperties.getSystemPropertyByCmdLineOption(cmdLineOption)
                    if propertyName: serverSystemProperties[propertyName] = propertyValue
        return serverSystemProperties


class ServerDiscovererByShell(jee_discoverer.DiscovererByShell, entity.HasPlatformTrait):

    def __init__(self, shell, layout, configParser):
        r'@types: shellutils.Shell, jboss.BaseServerLayout, jboss.ServerConfigParser'
        jee_discoverer.DiscovererByShell.__init__(self, shell, layout)
        self._configParser = configParser

    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        '''
        return trait.majorVersion.value() < 5

    def discoverBindingsByBindingManager(self):
        ''' Name from jboss-service.xml
        Suitable for JBoss 3.x - 4.x
        @types: -> list(ServerSocketDescriptor)
        @
        '''
        bindings = []
        try:
            path = self.getLayout().getBindingConfigPath()
            content = self._getShell().getXML(path)
            jbossService = self._getShell().getXML(self.getLayout().getConfigFilePath())
            bindingSetName = self._configParser.parseBindingManagerConfigName(jbossService)
            if bindingSetName:
                bindings.extend(self._configParser.parseBindingsFromBindingManagerConfig(content, bindingSetName))
        except Exception:
            logger.debug('Failed to get bindings by bindingManager config')
        return bindings

    def discoverBindingsByJbossServiceXml(self):
        bindings = []
        try:
            path = self.getLayout().getConfigFilePath()
            content = self._getShell().getXML(path)
            bindings.extend(self._configParser.parseBindingsFromJBossServiceXml(content))
        except Exception:
            logger.debug('Failed to discover bindings from jboss-service.xml')
        return bindings

class ServerDiscovererByShellV5(ServerDiscovererByShell):

    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        '''
        return trait.majorVersion.value() == 5 or trait.majorVersion.value() == 6

class ServerDiscovererByShellV7(ServerDiscovererByShell):

    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        '''
        return trait.majorVersion.value() == 7

    def discoverInterfaces(self, serverInterfaces, dnsResolver, ipAddressList):
        ''' Discover ip-address lists of interface to dict with interfaceName key
        @types: list(ServerConfigDescriptorV7.Interface), dict[str, str], netutils.DnsResolverByShell, list(str) -> dict[str, list(str)] '''
        # skip Interfaces without inetAddress
        withInetAddress, withoutInetAddress = \
            fptools.partition(ServerConfigDescriptorV7.Interface.getInetAddress, serverInterfaces)
        if withoutInetAddress: logger.debug('Found %s interfaces with no inetAddress specified' % len(withoutInetAddress))
        ipAddressListByInterfaceName = {}
        for interface in withInetAddress:
            # replace systemProperties with its values in inetAddress:
            inetAddress = interface.getInetAddress()
            ips = []
            if netutils.isValidIp(inetAddress): # if inetAddress specified as IP-address:
                if netutils.isLoopbackIp(inetAddress):
                    logger.debug('Skipped %s, because inetAddress is loopback' % interface)
                    continue
                if inetAddress == '0.0.0.0':
                    # add all listen IPs
                    ips.extend(ipAddressList)
                    continue
                # add regular IP
                ips.append(inetAddress)
            else: # try to resolve inetAddress as hostname, get first IP:
                try:
                    resolvedIp = dnsResolver.resolveIpsByHostname(inetAddress)[0]
                    # add resolved IP
                    ips.append(resolvedIp)
                except:
                    logger.debug('Skipped %s, failed to resolve hostname' % interface)
            ipAddressListByInterfaceName[interface.getName()] = ips
        return ipAddressListByInterfaceName


class ServerDiscovererByJmx(jee_discoverer.HasJmxProvider):
    'Discoverer supports only deployment of one server'

    def discoverDomain(self):
        '''@types: -> jee.Domain
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        logger.info("Discover servers in domains")
        try:
            servers = self.findServers()
        except (Exception, JException):
            raise Exception("Failed to find information about servers")
        if len(servers) > 1:
            logger.warn("Deployment with more than one server is not supported by discovery. Only one server will be reported.")
        server = servers[ 0 ]
        logger.info('Discover JNP and RMI ports for server %s' % server)
        try:
            portsInfo = self.findServerPortsInfo(server)
        except Exception:
            logger.warnException('Failed to determine JNP and RMI ports for %s.' % server)
        else:
            roleWithEndpoinds = jee.RoleWithEndpoints()
            if _isServerEnvironmentProperty(portsInfo.jnpBindAddress,'jboss.bind.address') or portsInfo.jnpBindAddress == '0.0.0.0':
                portsInfo.jnpBindAddress = server.ip.value()
            if _isServerEnvironmentProperty(portsInfo.rmiBindAddress,'jboss.bind.address') or portsInfo.rmiBindAddress == '0.0.0.0':
                portsInfo.rmiBindAddress = server.ip.value()
            logger.debug('Adding endpoint: %s, %s ' % (portsInfo.jnpBindAddress, portsInfo.jnpPort.value()))
            roleWithEndpoinds.addEndpoint(netutils.createTcpEndpoint(portsInfo.jnpBindAddress, portsInfo.jnpPort.value()))
            logger.debug('Adding endpoint: %s, %s ' % (portsInfo.rmiBindAddress, portsInfo.rmiPort.value()))
            roleWithEndpoinds.addEndpoint(netutils.createTcpEndpoint(portsInfo.rmiBindAddress, portsInfo.rmiPort.value()))
            server.addRole(roleWithEndpoinds)
        server.ip.set(self._getProvider().getIpAddress())
        try:
            server.version = self.findVersionByNameAndNumber()
        except Exception:
            logger.debug('Failed to determine version by VersionName and VersionNumber attributes for %s.' % server)
            try:
                server.version = self.findVersionByFullVersionAndName()
            except Exception:
                logger.debug('Failed to determine version by Version and VersionName attributes for %s.' % server)
        domain = jee.Domain(server.getName())
        node = jee.Node(server.getName())
        node.addServer(server)
        domain.addNode(node)
        return domain

    def findServers(self):
        ''' Find information about servers from configurations
        @types: -> list(jee.Server)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        servers = []
        query = jmx.QueryByPattern('jboss.system:type', 'ServerConfig').addAttributes('ServerName')
        for serverConfigItem in self._getProvider().execute(query):
            name = serverConfigItem.ServerName
            # look at Properties attribute has hostname, vm name, os name, node name, jboss.bind.address
            if not name:
                logger.warn("Server skipped without name. Properties: %s" % dir(serverConfigItem))
                continue
            ip = self._getProvider().getIpAddress()
            server = jee.Server(name, ip)
            server.ip.set(ip)
            server.setObjectName(serverConfigItem.ObjectName)
            role = jboss.ServerRole()
            role.setPort(self._getProvider().getPort())
            server.addRole(role)
            servers.append(server)
        return servers

    def findVersionByFullVersionAndName(self):
        query = jmx.QueryByPattern('jboss.system:type', 'Server')
        query.addAttributes('Version', 'VersionName')
        for serverItem in self._getProvider().execute(query):
            fullVersion = serverItem.Version
            if fullVersion and fullVersion.find('(build: ') != -1:
                versionName = fullVersion[:fullVersion.find('(build: ')]
                return '%s [%s]' % (versionName, serverItem.VersionName)

    def findVersionByNameAndNumber(self):
        query = jmx.QueryByPattern('jboss.system:type', 'Server')
        query.addAttributes('VersionNumber', 'VersionName')
        for serverItem in self._getProvider().execute(query):
            if serverItem.VersionNumber and serverItem.VersionName:
                cutEAPfromNumber = lambda x: x.endswith('_EAP') and x[:-4] or x
                return '%s [%s]' % (cutEAPfromNumber(serverItem.VersionNumber),
                                    serverItem.VersionName)

    def findServerPortsInfo(self, server):
        r''' Find JNP and RMI server ports information from jboss:service=Naming mbean
        @types: jee.Server -> BindingsConfiguration.NamingService
        '''
        query = jmx.QueryByPattern('jboss:service', 'Naming')
        query.addAttributes('BindAddress', 'Port', 'RmiBindAddress', 'RmiPort')
        for result in self._getProvider().execute(query):
            port = bindAddress = rmiPort = rmiBindAddress = None
            if result.Port and result.Port != '0':
                port = result.Port
            bindAddress = result.BindAddress
            if result.RmiPort and result.RmiPort != '0':
                rmiPort = result.RmiPort
            rmiBindAddress = result.RmiBindAddress
            return BindingsConfiguration.NamingService(port, bindAddress, rmiPort, rmiBindAddress)


class ServerDiscovererByJmxV7(jee_discoverer.HasJmxProvider):
    '''Discoverer for Jboss 7+ version'''

    def discoverDomain(self, hostControllerManagementPort):
        ''' Standalone and distributed Domain discoverer
        @types: str -> jee.Domain
        @param: hostControllerManagementPort - port of corresponding hostController of managedServer
        JBoss JMX doesn't contain info about owner of managed server, so to discover it we have to set it '''
        domainName = 'DefaultDomain'
        ip = self._getProvider().getIpAddress()
        try:
            serverName, nodeName, launchType = self.findServerInfo()
        except (Exception, JException):
            raise Exception("Failed to find server info")
        else:
            if serverName and launchType:
                server = jee.Server(serverName, ip)
                server.ip.set(ip)
                try:
                    serverVersion = self.findServerVersion()
                except (Exception, JException):
                    logger.debug('Failed to discover server version')
                else:
                    server.version = serverVersion
                server.addRole(jboss.ServerRole())
                if launchType == 'DOMAIN':
                    domainName = self.findDomainName(hostControllerManagementPort)
                else: #STANDALONE
                    domainName = serverName
                    # trough standalone server mbean we can get content and name of config file:
                    configName, configContent = self.findStandaloneConfigInfo()
                    if configName and configContent:
                        server.addConfigFile(jee.createXmlConfigFileByContent(configName, configContent))
                logger.debug('Discover server endpoints: %s' % server)
                serverEndpoints = []
                try:
                    serverEndpoints = self.findEndpoints()
                except (Exception, JException):
                    raise Exception("Failed to discover server endpoints")
                else:
                    server.addRole(jee.RoleWithEndpoints(serverEndpoints))
                domain = jee.Domain(domainName)
                node = jee.Node(nodeName)
                node.addServer(server)
                domain.addNode(node)
                return domain

    def findDomainName(self, hostControllerManagementPort):
        ''' DomainName in distributed domain consist of domainController host + domainController port
        @types: str -> str
        @param: hostControllerManagementPort - port of corresponding hostController of managedServer
        JBoss JMX doesn't contain info about owner of managed server, so to discover it we have to set it '''
        #TODO: connect to hostController management port and read info about domainController
        domainControllerHost = domainControllerPort = None
        if not domainControllerHost:
            #TODO: add support of remote domainController
            domainControllerHost = self._getProvider().getIpAddress()
        if not domainControllerPort:
            domainControllerPort = hostControllerManagementPort
        return '%s %s' % (domainControllerHost, domainControllerPort)

    def findServerVersion(self):
        query = jmx.QueryByName('jboss.as:management-root=server')
        query.addAttributes('productVersion')
        productVersionItem = self._getProvider().execute(query)[0]
        if productVersionItem and productVersionItem.productVersion:
            return productVersionItem.productVersion
        else:
            query.addAttributes('releaseVersion')
            releaseVersionItem = self._getProvider().execute(query)[0]
            if releaseVersionItem and releaseVersionItem.releaseVersion:
                return releaseVersionItem.releaseVersion
            else:
                logger.warn("Failed to discover JBoss version")
                return None

    def findServerInfo(self):
        ''' Find server info by JMX
        @types: -> str, str, str
        @param: nodeName of standalone server the same as serverName
        @param: launchType: DOMAIN or STANDALONE
        '''
        query = jmx.QueryByName('jboss.as:core-service=server-environment')
        query.addAttributes('launchType', 'serverName', 'nodeName')
        # each server has the one serverConfigItem only:
        serverConfigItem = self._getProvider().execute(query)[0]
        launchType = serverConfigItem.launchType # 'STANDALONE' or 'DOMAIN'
        if launchType == 'DOMAIN' and serverConfigItem.nodeName:
            serverName = serverConfigItem.nodeName.split(':', 1)[0]
            nodeName = serverConfigItem.nodeName.split(':', 1)[1]
        else:
            serverName = nodeName = serverConfigItem.serverName
        return serverName, nodeName, launchType

    def findStandaloneConfigInfo(self):
        ''' Find standalone config file and content
        @types: -> str, str '''
        query = jmx.QueryByName('jboss.as:core-service=server-environment').addAttributes('configFile')
        # standalone server has the one configFile only:
        configName = self._getProvider().execute(query)[0].configFile
        configContent = self._getProvider().invokeMBeanMethod('jboss.as:management-root=server', 'readConfigAsXml', [], [])
        return configName, configContent

    def findEndpoints(self):
        ''' Find server endpoints by JMX
        @types: -> list(netutils.Endpoint) '''
        serverEndpoints = []
        query = jmx.QueryByPattern('jboss.as:socket-binding-group', '*').patternPart('socket-binding', '*')
        query.addAttributes('bound', 'boundAddress', 'boundPort', 'name')
        for binding in self._getProvider().execute(query):
            if binding.bound == 'true':
                serverEndpoints.append(netutils.createTcpEndpoint(binding.boundAddress, binding.boundPort))
            else:
                logger.warn('Skipped unbound binding: %s' % binding.name)
        return serverEndpoints


class ApplicationDiscovererByJmxV34(jee_discoverer.HasJmxProvider, entity.HasPlatformTrait):

    def getDescriptorParser(self):
        if not hasattr(self, 'descriptorParser'):
            self.descriptorParser = asm_jboss_discover.JBossApplicationDescriptorParser()
        return self.descriptorParser

    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        '''
        return trait.majorVersion.value() in (3, 4)

    def discoverEjbModules(self):
        ''' Discover EJB modules and related entries: session, entity, md beans
        @types: -> list(jee.EjbModule)
        '''
        ejbModules = []
        try:
            ejbModules = self.findEjbModules()
        except Exception, ex:
            logger.warnException('Failed to discover EJB modules. %s' % ex)
        statelessBeans = []
        try:
            statelessBeans = self.__findItemsByJeeType('StatelessSessionBean')
        except Exception, ex:
            logger.warnException('Failed to discover Stateless Session beans. %s' % ex)
        statefullBeans = []
        try:
            statefullBeans = self.__findItemsByJeeType('StatefullSessionBean')
        except Exception, ex:
            logger.warnException('Failed to discover Statefull Session beans. %s' % ex)
        mdBeans = []
        try:
            mdBeans = self.__findItemsByJeeType('MessageDrivenBean')
        except Exception, ex:
            logger.warnException('Failed to discover Message-Driven beans. %s' % ex)
        entityBeans = []
        try:
            entityBeans = self.__findItemsByJeeType('EntityBean')
        except Exception, ex:
            logger.warnException('Failed to discover Entity beans. %s' % ex)
        for module in ejbModules:
            for entry in self.__determineModuleEntries(module, statelessBeans, jee.Stateless):
                module.addEntry(entry)
            for entry in self.__determineModuleEntries(module, statefullBeans, jee.Stateful):
                module.addEntry(entry)
            for entry in self.__determineModuleEntries(module, mdBeans, jee.MessageDrivenBean):
                module.addEntry(entry)
            for entry in self.__determineModuleEntries(module, entityBeans, jee.EntityBean):
                module.addEntry(entry)
        return ejbModules

    def discoverWebModules(self):
        '''@types: -> list(jee.Module)
        @return: list of Modules with WebModule role set
        '''
        webModules = []
        try:
            webModules = self.findWebModules()
        except Exception, ex:
            logger.warnException('Failed to discover WEB modules. %s' % ex)
        servletEntites = []
        try:
            servletEntites = self.__findItemsByJeeType('Servlet')
        except Exception, ex:
            logger.warnException('Failed to discover Servlets. %s' % ex)
        for module in webModules:
            for entry in self.__determineModuleEntries(module, servletEntites, jee.Servlet):
                module.addEntry(entry)
        return webModules

    def __determineModuleEntries(self, module, items, entryClass):
        '@types: jee.Module, list((str, str)), PyClass -> list(jee.Module.Entry)'
        entries = []
        for objectName, parentObjectName in items:
            if module.getObjectName() == parentObjectName:
                entries.append( jee.createNamedJmxObject(objectName, entryClass) )
        return entries

    def __findItemsByJeeType(self, jeeType):
        '''
        @types: str -> list(tuple(str, str))
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        query = jmx.QueryByPattern('jboss.management.local:j2eeType', jeeType)
        query.addAttributes('Parent', 'parent')
        items = []
        for item in self._getProvider().execute(query):
            parentObjectName = item.Parent or item.parent
            items.append((item.ObjectName, parentObjectName))
        return items

    def findApplications(self):
        ''' Find available applications (name and ObjectName)
        @types: -> list(jee.Application)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        query = jmx.QueryByPattern('jboss.management.local:j2eeType', 'J2EEApplication')
        query.addAttributes('ObjectName' ,'deploymentDescriptor', 'DeploymentDescriptor')
        apps = []
        for item in self._getProvider().execute(query):
            app = jee.createNamedJmxObject(item.ObjectName, jee.EarApplication)
            deploymentDescriptorContent = item.deploymentDescriptor or item.DeploymentDescriptor
            jndiName = None
            if deploymentDescriptorContent:
                configFile = jee.createXmlConfigFileByContent(app.getDescriptorName(), deploymentDescriptorContent)
                app.addConfigFile(configFile)
                deploymentDescriptor = self.getDescriptorParser().parseApplicationDescriptor(deploymentDescriptorContent, app)
                jndiName = deploymentDescriptor.getJndiName()
            if not jndiName:
                jndiName = jee_constants.ModuleType.EAR.getSimpleName(app.getName())
            app.setJndiName(jndiName)
            apps.append(app)
        return apps

    def findEjbModules(self):
        ''' Find EJB modules (name, deployment descriptor, ObjectName)
        @types: -> list(jee.WebModule)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        query = jmx.QueryByPattern('jboss.management.local:j2eeType', 'EJBModule')
        query.addAttributes('Name', 'name', 'DeploymentDescriptor', 'deploymentDescriptor','jbossDeploymentDescriptor')
        modules = []
        for item in self._getProvider().execute(query):
            if not item.ObjectName:
                logger.warn("Skip EJBModule without name %s" % item)
                continue
            module = jee.createNamedJmxObject(item.ObjectName, jee.EjbModule)
            descriptorContent = item.DeploymentDescriptor or item.deploymentDescriptor
            if descriptorContent:
                configFile = jee.createDescriptorByContent(descriptorContent, module)
                module.addConfigFile(configFile)
            #discover webservice for this ejb module
            logger.debug("discover webservice for ejb module:", module.getName())
            module.addWebServices(self.findWebServices(module.getName()))
            if item.jbossDeploymentDescriptor:
                configFile = jee.createXmlConfigFileByContent(asm_jboss_discover.JBOSS_EJB_MODULE_DEPLOYMENT_DESCRIPTOR_NAME, item.jbossDeploymentDescriptor)
                module.addConfigFile(configFile)
            module.setObjectName(item.ObjectName)
            modules.append(module)
        return modules

    def findWebModules(self):
        ''' Find WEB modules (name, jndiName, deployment descriptor, ObjectName)
        @types: -> list(jee.WebModule)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        query = jmx.QueryByPattern('jboss.management.local:j2eeType', 'WebModule')
        query.addAttributes('JNDIName', 'deploymentDescriptor',
                            'jbossWebDeploymentDescriptor')
        modules = []
        for moduleItem in self._getProvider().execute(query):
            module = jee.createNamedJmxObject(moduleItem.ObjectName, jee.WebModule)
            if moduleItem.deploymentDescriptor:
                configFile = jee.createDescriptorByContent(moduleItem.deploymentDescriptor, module)
                module.addConfigFile(configFile)
            if moduleItem.jbossWebDeploymentDescriptor:
                configFile = jee.createXmlConfigFileByContent(asm_jboss_discover.JBOSS_WEB_MODULE_DEPLOYMENT_DESCRIPTOR_NAME, moduleItem.jbossWebDeploymentDescriptor)
                module.addConfigFile(configFile)
            #discover webservice for this ejb module
            logger.debug("discover webservice for web module:", module.getName())
            module.addWebServices(self.findWebServices(module.getName()))
            module.setJndiName(moduleItem.JNDIName)
            modules.append(module)
        return modules

    def findWebServices(self, objectName):
        result = []
        context = objectName
        if objectName.rfind('.war') != -1 or objectName.rfind('.jar')!= -1 or objectName.rfind('.ear')!= -1:
            context = objectName[:len(context) - 4]
        query = jmx.QueryByPattern('jboss.ws:context', context)
        query.addAttributes('context', 'endpoint', 'Endpoint', 'Address', 'address')
        for webserviceItem in self._getProvider().execute(query):
            webserviceObjectName = jmx.restoreObjectName(webserviceItem.ObjectName)
            webserviceName = webserviceObjectName.getKeyProperty('endpoint') or webserviceObjectName.getKeyProperty('Endpoint')
            webserviceUrl = webserviceItem.Address or webserviceItem.address
            if webserviceName:
                logger.debug("found webservice: %s with url: %s" % (webserviceName, webserviceUrl))
                result.append(jee.WebService(webserviceName, webserviceUrl))
        return result

class ApplicationDiscovererByJmxV56(ApplicationDiscovererByJmxV34):

    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        '''
        return trait.majorVersion.value() in (5, 6)

    def discoverEjbModules(self):
        ejbModules = []
        try:
            ejbModules = self.findEjbModules()
        except Exception, ex:
            logger.warnException('Failed to discover EJB modules. %s' % ex)
        for module in ejbModules:
            descriptor = self.getDescriptorParser().parseJBossEjbModuleDescriptor(module)
            if descriptor:
                for bean in descriptor.getBeans():
                    module.addEntry(bean)
                if descriptor.getJndiName():
                    module.setJndiName(descriptor.getJndiName())
        return ejbModules

    def discoverWebModules(self):
        '''@types: -> list(jee.Module)
        @return: list of Modules with WebModule role set
        '''
        webModules = []
        try:
            webModules = self.findWebModules()
        except Exception, ex:
            logger.warnException('Failed to discover WEB modules. %s' % ex)
        webModuleByName = fptools.applyMapping(self.__getWebIdentifier, webModules)
        objectNames = configFiles = {}
        try:
            (objectNames, configFiles) = self.__findObjectNameAndJBossWebDeploymentDescriptor()
        except Exception, ex:
            logger.warnException('Failed to discover Servlets. %s' % ex)
        for name in objectNames:
            module = webModuleByName.get(name)
            if module:
                # override object name from jboss.web domain (binded at url) to jboss.management (real app)
                module.setObjectName(objectNames[name])
                module.addConfigFile(configFiles.get(name))
        return webModules

    def __findObjectNameAndJBossWebDeploymentDescriptor(self):
        ''' Determining linkage between webmodule name and objectName
        @types: -> dict[str, str]
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        objectNames = {}
        configFiles = {}
        query = jmx.QueryByPattern('jboss.management.local:j2eeType', 'WebModule')
        query.addAttributes('objectName','jbossWebDeploymentDescriptor')
        for item in self._getProvider().execute(query):
            objectName = item.ObjectName
            identifier = self.__getWebIdentifier(objectName=objectName)
            objectNames[identifier] = objectName
            if item.jbossWebDeploymentDescriptor:
                configFiles[identifier] = jee.createXmlConfigFileByContent(asm_jboss_discover.JBOSS_WEB_MODULE_DEPLOYMENT_DESCRIPTOR_NAME, item.jbossWebDeploymentDescriptor)
        return objectNames, configFiles

    def findWebModules(self):
        ''' Find WEB modules (name, deployment descriptor, ObjectName)
        @types: -> list(jee.WebModule)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        query = jmx.QueryByPattern('jboss.web:j2eeType', 'WebModule')
        query.addAttributes('docBase', 'deploymentDescriptor', 'servlets', 'path')
        modules = []
        # exploded wars name consist of: <warName> + 19 digits hash + '-exp' + '.war'
        # another name format found in 6.1 : <warName>+'.war-'+hash(not sure if the length is fixed)
        namePattern = r'^(.*[/\\])?(.+?)((([0-9a-f]{19}-exp)?\.war)|(\.war(-[0-9a-f]+)?))[/\\]?$'
        for moduleItem in self._getProvider().execute(query):
            warName = moduleItem.docBase
            m = re.search(namePattern, warName)
            if m:
                warName = m.group(2) + '.war'
            module = jee.WebModule(warName)
            module.setObjectName(moduleItem.ObjectName)
            if moduleItem.path:
                module.contextRoot = moduleItem.path
                module.setJndiName(moduleItem.path)
            else:
                module.setJndiName(jee_constants.ModuleType.WAR.getSimpleName(module.getName()))
            descriptorContent = moduleItem.deploymentDescriptor
            if descriptorContent:
                configFile = jee.createDescriptorByContent(descriptorContent, module)
                module.addConfigFile(configFile)
            servlets = moduleItem.servlets and moduleItem.servlets.split(';')
            for servletObjectName in servlets:
                objectName = jmx.restoreObjectName(servletObjectName)
                name = objectName.getKeyProperty('name')
                if name not in ('jsp', 'default'):  #  skip default servlets
                    servlet = jee.Servlet(name)
                    servlet.setObjectName(servletObjectName)
                    module.addEntry(servlet)
            modules.append(module)
        return modules

    def __getWebIdentifier(self, webModule=None, objectName=None):
        '''
        @type webModule: jee.WebModule
        @type objectName: str
        @return the identifier for the web module
        @rtype: str
        '''
        moduleName = None
        if webModule:
            moduleName = jee_constants.ModuleType.WAR.getSimpleName(webModule.getName())
            objectName = webModule.getObjectName()
        if objectName:
            objectName = jmx.restoreObjectName(objectName)
            applicationName = objectName.getKeyProperty('J2EEApplication')
            if applicationName == 'null' or applicationName == 'none':
                applicationName = 'default'
            if not moduleName:
                moduleName = jee_constants.ModuleType.WAR.getSimpleName(objectName.getKeyProperty('name'))
            return '%s|%s' % (applicationName, moduleName)
        return ''


class ApplicationDiscovererByJmxV7(jee_discoverer.HasJmxProvider, entity.HasPlatformTrait):
    ''' JEE Application Discoverer for JBoss 7+.
    EAR, WAR, JAR, SAR modules MBeans not available'''

    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        '''
        return trait.majorVersion.value() >= 7

    def findApplications(self):
        ''' Find JEE Applications by JMX
        @types: -> list(jee.Application) '''
        applications = []
        query = jmx.QueryByPattern('jboss.as:deployment', '*')
        query.addAttributes('runtimeName')
        return applications

    def discoverEjbModules(self):
        # MBean of application module is not implemented in JBoss7.1
        return []
    def discoverWebModules(self):
        # MBean of application module is not implemented in JBoss7.1
        return []


class ApplicationDiscovererByShell(jee_discoverer.BaseApplicationDiscovererByShell):
    def __init__(self, shell, layout, descriptorParser):
        r'''
        @types: shellutils.Shell, ApplicationLayout, ApplicationDescriptorParser
        '''
        jee_discoverer.BaseApplicationDiscovererByShell.__init__(self, shell, layout, descriptorParser)

    def _findModule(self, name, path, moduleType, jndiNameToName = None):
        module = jee_discoverer.BaseApplicationDiscovererByShell._findModule(self, name, path, moduleType)
        # Add webservice
        files = filter(lambda f: re.match(self._getDescriptorParser().WEBSERVICE_DESCRIPTOR_FILE_NAME, f.getName(), re.IGNORECASE),
                       module.getConfigFiles())
        if files:
            try:
                logger.debug('Parsing Webservice descriptor file %s for %s' % (files[0].name, module))
                webservice = self._getDescriptorParser().parseWebserviceDescriptor(files[0].content)
                if webservice:
                    logger.debug('Found Webservice %s for %s' % (webservice, module.getName()))
                    module.addWebServices(webservice)
            except (Exception, JException):
                logger.warnException('Failed to process Webservice for %s:%s' % (moduleType, module.getName()))

        return module

    def findDeployedWarApplications(self):
        r'''Find very basic information about deployed WAR applications - name & full path
        @types: -> list(jee.Application)'''
        layout = self.getLayout()
        applications = []
        for path in layout.findDeployedWarApplicationsPaths():
            name = layout.extractAppNameFromWarPath(path)
            applications.append(jee.WarApplication(name, path))
        return applications

    def findDeployedEarApplications(self):
        r'''Find very basic information about deployed EAR applications - name & full path
        @types: -> list(jee.Application)'''
        layout = self.getLayout()
        applications = []
        for path in layout.findDeployedEarApplicationsPaths():
            name = layout.extractAppNameFromEarPath(path)
            applications.append(jee.Application(name, path))
        return applications

    def findWebApplicationResources(self, application):
        r''' Expected input - application with modules and configuration files attached that will be
        parsed to get resources
        @types: jee.Application -> list(jee_discoverer.ApplicationResource)'''
        resources = []
        for module in application.getModules():
            # find JEE descriptor with name 'web.xml'
            files = filter(lambda f, expectedFileName = module.getDescriptorName():
                           f.getName() == expectedFileName, module.getConfigFiles())
            if files:
                # there may be only one JEE descriptor file with name 'web.xml'
                file_ = files[0]
                descriptor = self._getDescriptorParser().parseWebModuleDescriptor(file_.content, module)
                resources.extend(descriptor.getResources())
        return resources

class JmsDiscoverer(entity.HasPlatformTrait):

    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        '''
        return trait.majorVersion.value() == 3 or \
               (trait.majorVersion.value() == 4 and trait.minorVersion.value() <= 2)

    def getJmsDomain(self):
        return 'jboss.mq'


class JmsDiscovererV5(entity.HasPlatformTrait):

    def _isApplicablePlatformTrait(self, trait):
        return trait.majorVersion.value() == 5 or \
               (trait.majorVersion.value() == 4 and trait.minorVersion.value() == 3 )

    def getJmsDomain(self):
        return 'jboss.messaging'


class JmsDiscovererV6(entity.HasPlatformTrait):

    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        '''
        return trait.majorVersion.value() == 6

    def getJmsDomain(self):
        return 'org.hornetq'

class JmsDiscovererV7(entity.HasPlatformTrait):

    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        '''
        return trait.majorVersion.value() >= 7

    def getJmsDomain(self):
        return 'hornetq-server'

class JmsDiscovererByJmx(jee_discoverer.HasJmxProvider, JmsDiscoverer):

    def discoverJmsResourcesForServer(self, server):
        '@types: jee.Server -> list(jee.JmsDestination)'
        logger.info('Discover JMS resources for %s' % server)
        resources = []
        try:
            resources.extend(self.findJmsQueues())
        except (Exception, JException):
            logger.warnException('Failed to discover JMS Queues')
        try:
            resources.extend(self.findJmsTopics())
        except (Exception, JException):
            logger.warnException('Failed to discover JMS Topics')
        try:
            jmsServer = jms.Server(self.getJmsDomain(), server.hostname)
            for resource in resources:
                resource.server = jmsServer
        except (Exception, JException):
            logger.warnException('Failed to bind JMS destinations on JMS Server')
        return resources

    def findJmsQueues(self):
        '''@types: -> list(jms.Queue)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        return self._findJmsDestinationByType('Queue', jms.Queue)

    def findJmsTopics(self):
        '''@types: -> list(jms.Topic)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        return self._findJmsDestinationByType('Topic', jms.Topic)

    def getDestinationQueryPattern(self):
        return '.'.join([self.getJmsDomain(), 'destination:service'])

    def _findJmsDestinationByType(self, destinationType, destinationClass):
        '''@types: str, PyClass -> list(jms.Destination)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        query = jmx.QueryByPattern(self.getDestinationQueryPattern(), destinationType)
        query.addAttributes('Name', 'name', 'JNDIName')
        destinations = []
        for jmsItem in self._getProvider().execute(query):
            destination = jee.createNamedJmxObject(jmsItem.ObjectName, destinationClass)
            destination.setJndiName(jmsItem.JNDIName)
            destinations.append(destination)
        return destinations

class JmsDiscovererByJmxV5(JmsDiscovererV5, JmsDiscovererByJmx): pass
    # EAP 4.3 and 5.x community

class JmsDiscovererByJmxV6(JmsDiscovererV6, JmsDiscovererByJmx):

    def getDestinationQueryPattern(self):
        return ':'.join([self.getJmsDomain(), 'module=JMS,type'])

    def _findJmsDestinationByType(self, destinationType, destinationClass):
        query = jmx.QueryByPattern(self.getDestinationQueryPattern(), destinationType)
        query.addAttributes('Name', 'name', 'JNDIBindings')
        destinations = []
        for jmsItem in self._getProvider().execute(query):
            destination = jee.createNamedJmxObject(jmsItem.ObjectName, destinationClass)
            destination.setJndiName(jmsItem.JNDIBindings)
            destinations.append(destination)
        return destinations

class JmsDiscovererByJmxV7(JmsDiscovererV7, JmsDiscovererByJmx):

    def discoverJmsResourcesForServer(self, server):
        ''' @types: jee.Server -> list(jee.Destination) '''
        logger.info('Discover JMS resources for %s' % server)
        resources = []
        try:
            queryQueues = jmx.QueryByPattern('jboss.as:subsystem', 'messaging').patternPart(self.getJmsDomain(), '*').patternPart('jms-queue', '*')
            queryQueues.addAttributes('queueAddress')
            for queue in self._getProvider().execute(queryQueues):
                name = queue.queueAddress
                jmsQueue = jms.Queue(name)
                resources.append(jmsQueue)
        except (Exception, JException):
            logger.warnException('Failed to discover JMS Queues')
        try:
            queryTopics = jmx.QueryByPattern('jboss.as:subsystem', 'messaging').patternPart(self.getJmsDomain(), '*').patternPart('jms-topic','*')
            queryTopics.addAttributes('topicAddress')
            for topic in self._getProvider().execute(queryTopics):
                logger.warnException('Failed to discover JMS Topics')
                name = topic.topicAddress
                jmsTopic = jms.Topic(name)
                resources.append(jmsTopic)
        except (Exception, JException):
            logger.warnException('Failed to discover JMS Topics')
        try:
            jmsServer = jms.Server(self.getJmsDomain(), server.hostname)
            for resource in resources:
                resource.server = jmsServer
        except (Exception, JException):
            logger.warnException('Failed to bind JMS destinations on JMS Server')
        return resources


class JmsDiscovererByShell(jee_discoverer.DiscovererByShell, JmsDiscoverer):

    def __init__(self, shell, layout, configParser):
        r'@types: shellutils.Shell, jboss.BaseServerLayout, jboss.ServerConfigParser'
        jee_discoverer.DiscovererByShell.__init__(self, shell, layout)
        self._configParser = configParser

    def discoverJmsResourcesForServer(self, server):
        '@types: jee.Server -> list(jms.Destination)'
        logger.info('Discover JMS resources for %s' % server)
        destinations = []
        jmsServer = jms.Server(self.getJmsDomain(), server.hostname)
        try:
            role = server.getRole(jboss.ServerRole)
            if role:
                for path in self.getLayout().listJmsConfigFiles():
                    try:
                        file_ = self.getLayout().getFileContent(path)
                    except file_topology.PathNotFoundException, filePath:
                        logger.debug('JMS resources file %s for %s not found' % (filePath, server))
                    except (Exception, JException):
                        logger.warnException('Failed to get JMS destinations service file')
                    else:
                        try:
                            descriptor = self._configParser.parseDestinationsService(file_.content)
                            destinations.extend(descriptor.getJmsDestinations())
                            for destination in destinations:
                                destination.server = jmsServer
                            server.addConfigFile(jee.createXmlConfigFile(file_))
                        except (Exception, JException):
                            logger.warnException('Failed to parse JMS destinations service file')
        except (Exception, JException):
            logger.warnException('Failed to find destinations')
        return destinations

class JmsDiscovererByShellV5(JmsDiscovererV5, JmsDiscovererByShell): pass
    # EAP 4.3 and 5.x community
class JmsDiscovererByShellV6(JmsDiscovererV6, JmsDiscovererByShell): pass

class JmsDiscovererByShellV7(JmsDiscovererV7, JmsDiscovererByShell): pass


class HasParser:

    def __init__(self, parser):
        self.__parser = parser

    def getParser(self):
        return self.__parser


class HasFs:

    def __init__(self, shell):
        fs = file_system.createFileSystem(shell)
        self.__fs = _createFileSystemRecursiveSearchEnabled(fs)

    def getFs(self):
        return self.__fs


class DiscovererByShellWithParser(jee_discoverer.DiscovererByShell,
                                  HasParser,
                                  HasFs):

    def __init__(self, shell, layout, configParser):
        r'''@types: shellutils.Shell,
                    jboss.BaseServerLayout,
                    jboss.ServerConfigParser'''
        jee_discoverer.DiscovererByShell.__init__(self, shell, layout)
        HasParser.__init__(self, configParser)
        HasFs.__init__(self, shell)
        self.__propertiesDiscoverer = SystemPropertiesDiscoverer()

    def getSystemPropertiesDiscoverer(self):
        return self.__propertiesDiscoverer

    def _resolvePathList(self, fileList, relativeDir, systemProperties):
        propertiesDiscoverer = self.getSystemPropertiesDiscoverer()
        fs = self.getFs()
        pathUtil = file_system.getPath(fs)
        # resolve ${jboss} expressions
        fileListWithUrls = propertiesDiscoverer.resolveLineList(fileList,
                                                            systemProperties)
        # cut out url handler from paths like <file://>/opt/jboss/
        fn = systemProperties.getFilePathFromURLValue
        resolvedFileList = map(fn, fileListWithUrls)
        # handle relative paths:
        fn = pathUtil.isAbsolute
        absolutePathFileList, relativePathFileList = (fptools.partition(fn,
                                                            resolvedFileList))
        fn = lambda r: pathUtil.join(relativeDir, r)
        absFileList = absolutePathFileList + map(fn, relativePathFileList)
        # normalize paths: /opt/jboss/../deploy -> /opt/deploy
        return map(pathUtil.normalizePath, absFileList)


class HADiscovererByShell(DiscovererByShellWithParser):

    class BeansFileFilter(file_system.FileFilter):

        def __init__(self):
            self.filePattern = 'beans.xml'

        def accept(self, file_):
            return file_.name.lower().endswith('-beans.xml')

    def listBeansConfigFiles(self):
        configs = []
        fs = self.getFs()
        layout = self.getLayout()
        for path in layout.getResourcesDirsList():
            try:
                files = fs.getFiles(path, recursive=1,
                                    filters=[self.BeansFileFilter()],
                                    fileAttrs=[FILE_PATH])
            except Exception:
                logger.debugException("Failed to get list of beans files")
            else:
                configs.extend(files)
        return configs

    def discoverHAResourcesDirs(self, systemProperties):
        resourcesDirs = []
        fs = self.getFs()
        pathUtil = file_system.getPath(fs)
        parser = self.getParser()
        propertiesDiscoverer = self.getSystemPropertiesDiscoverer()
        for file_ in self.listBeansConfigFiles():
            try:
                path = file_.path
                config = fs.getFile(path, [FILE_CONTENT])
                content = config.content
                if parser.hasHAProfileManager(content):
                    # parse raw records from config file
                    dirsWithExpressions = parser.parseHAResourcesDirs(content)
                    # resolve ${jboss} expressions in paths
                    dirsWithURLs = propertiesDiscoverer.resolveLineList(
                                                        dirsWithExpressions,
                                                        systemProperties)
                    # cut out url handler from paths like <file://>/opt/jboss/
                    fn = systemProperties.getFilePathFromURLValue
                    resolvedDirs = map(fn, dirsWithURLs)
                    # handle relative paths
                    fn = pathUtil.isAbsolute
                    absolutePathDirs, relativePathDirs = (
                                        fptools.partition(fn, resolvedDirs))
                    serverDir = systemProperties.get('jboss.server.url')
                    fn = lambda r: pathUtil.join(serverDir, r)
                    absPaths = absolutePathDirs + map(fn, relativePathDirs)
                    # normalize paths: /opt/jboss/../deploy -> /opt/deploy
                    normalizedPaths = map(pathUtil.normalizePath, absPaths)
                    resourcesDirs.extend(normalizedPaths)
            except (Exception, JException):
                logger.debug('Failed to get HA Resources dir list')
        return resourcesDirs


class DatasourceDiscovererByShell(jee_discoverer.DiscovererByShell):

    def __init__(self, shell, layout, configParser):
        r'@types: shellutils.Shell, jboss.BaseServerLayout, jboss.ServerConfigParser'
        jee_discoverer.DiscovererByShell.__init__(self, shell, layout)
        self._configParser = configParser

    def discoverDatasourcesForServer(self, server, systemProperties):
        '''
        @types: jee.Server -> list(jee.Datasource)
        '''
        logger.info('Discover datasources for %s' % server)
        datasources = []
        try:
            files = self.getLayout().listDatasourceDescriptorsFiles()
        except (Exception, JException):
            logger.warnException('Failed to find datasource files')
        else:
            for file_ in files:
                configFile = self.getLayout().getFileContent(file_.path)
                server.addConfigFile(jee.createXmlConfigFile(configFile))
                try:
                    dsWithExpressions = self._configParser.parseDatasourceConfig(configFile.content)
                    for descriptor in dsWithExpressions:
                        # resolve expressions and set base datasource properties:
                        name = systemProperties.resolveProperty(descriptor.jndiName)
                        ds = jee.Datasource(name)
                        ds.setJndiName(name)
                        url = systemProperties.resolveProperty(descriptor.connectionUrl)
                        if url: ds.url = url
                        driverClass = systemProperties.resolveProperty(descriptor.driverClass)
                        if driverClass: ds.driverClass = driverClass
                        userName = systemProperties.resolveProperty(descriptor.userName)
                        if userName: ds.userName = userName
                        # resolve db properties
                        address = systemProperties.resolveProperty(descriptor.serverName)
                        port = systemProperties.resolveProperty(descriptor.portNumber)
                        databaseServer = db.DatabaseServer(address, port)
                        ds.setServer(databaseServer)
                        databaseName = systemProperties.resolveProperty(descriptor.databaseName)
                        if databaseName:
                            databaseServer.addDatabases(db.Database(databaseName))
                        ds.maxCapacity.set(systemProperties.resolveProperty(descriptor.maxCapacity))
                        datasources.append(ds)
                except (Exception, JException):
                    logger.warnException('Failed to parse datasource configFile file')
        logger.debug('Found %s datasources' % len(datasources))
        return datasources


class DatasourceDiscovererByJmxV7(jee_discoverer.HasJmxProvider, entity.HasPlatformTrait):

    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        '''
        return trait.majorVersion.value() >= 7

    def discoverDatasourcesForServer(self, server):
        ''' @types: jee.Server -> list(jee.Datasource) '''
        logger.info('Discover datasources for %s' % server)
        datasources = []
        try:
            query = jmx.QueryByPattern('jboss.as:subsystem', 'datasources').patternPart('data-source', '*')
            for ds_obj in self._getProvider().execute(query):
                ds_name = re.findall('jboss.as:data-source=([^,]+),subsystem=datasources', ds_obj.ObjectName)
                if ds_name:
                    logger.info("Find datasource %s" %ds_name[0])
                    logger.info("Start to query attributes of datasource %s" %ds_name[0])
                    query = jmx.QueryByName('jboss.as:subsystem=datasources,data-source='+ds_name[0])
                    query.addAttributes('enabled', 'jndiName', 'connectionUrl', 'driverClass', 'userName')
                    ds_list = self._getProvider().execute(query)
                    if ds_list:
                        ds = ds_list[0]
                        if ds.enabled == 'true':
                            jndiName = ds.jndiName
                            jeeDatasource = jee.Datasource(jndiName)
                            jeeDatasource.setJndiName(jndiName)
                            jeeDatasource.url = ds.connectionUrl
                            jeeDatasource.driverClass = ds.driverClass
                            jeeDatasource.userName = ds.userName
                            datasources.append(jeeDatasource)
                        else:
                            logger.warn('Skipped disabled datasource: %s' % ds.jndiName)
                    else:
                        logger.warn('Failed to query attributes of datasource: %s ' %ds_name[0])
        except (Exception, JException):
            logger.warnException('Failed to discover datasources')
        return datasources


class DatasourceDiscovererByJmx(jee_discoverer.HasJmxProvider, entity.HasPlatformTrait):

    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        '''
        return trait.majorVersion.value() < 7

    def discoverDatasourcesForServer(self, server):
        ''' @types: jee.Server -> list(jee.Datasource) '''
        logger.info('Discover datasources for %s' % server)
        datasources = []
        try:
            for pool in self.findManagedConnectionPools():
                objectNameStr = pool.getObjectName()
                datasource = jee.createNamedJmxObject(objectNameStr, jee.Datasource)
                try:
                    for factory in self.findConnectionFactoriesByName(pool.factoryName):
                        try:
                            datasource.url = self.getUrlForManagedFactory(factory)
                        except Exception, ex:
                            logger.warnException("Failed to get JDBC URL for managed factory. %s" % str(ex))
                        try:
                            datasource.driverClass = self.getDriverClassForManagedFactory(factory)
                        except Exception, ex:
                            logger.warnException("Failed to get JDBC Driver Class for managed factory. %s" % str(ex))
                        try:
                            datasource.userName = self.getUserNameForManagedFactory(factory)
                        except Exception, ex:
                            logger.warnException("Failed to get JDBC Username for managed factory. %s" % str(ex))
                except Exception, ex:
                    logger.warnException('Failed to find connection factories by name "%s". %s' % (pool.factoryName, ex))
                datasources.append( datasource )
        except (Exception, JException):
            logger.warnException('Failed to find managed connection pools')
        return datasources

    def findManagedConnectionPools(self):
        ''' Find managed connection pools (ObjectName, factory name)
        @types: -> list(jboss.ConnectionPool)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        query = jmx.QueryByPattern('jboss.jca:service', 'ManagedConnectionPool')
        query.addAttributes('ManagedConnectionFactoryName')
        pools = []
        for poolItem in self._getProvider().execute(query):
            connectionPool = jee.createNamedJmxObject(poolItem.ObjectName, jboss.ConnectionPool)
            connectionPool.factoryName = poolItem.ManagedConnectionFactoryName
            pools.append(connectionPool)
        return pools

    def findConnectionFactoriesByName(self, name):
        '''Find connection factories (ObjectName)
        @types: -> list(jboss.ConnectionFactory)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        query = jmx.QueryByName(name).addAttributes('ObjectName',
                                                    'ConnectionDefinition',
                                                    'ManagedConnectionFactoryClass')
        factories = []
        for factoryItem in self._getProvider().execute(query):
            if (factoryItem.ConnectionDefinition == 'javax.sql.DataSource' or
                factoryItem.ManagedConnectionFactoryClass == 'org.jboss.resource.adapter.jdbc.local.LocalManagedConnectionFactory'):
                    objectName = factoryItem.ObjectName
                    factory = jee.createNamedJmxObject(objectName,
                                                       jboss.ConnectionFactory)
                    factories.append( factory )
        return factories

    def __getManagedFactoryAttribute(self, factory, attribute):
        ''' Get connection url for specified factory
        @types: jboss.ConnectionFactory -> str or None
        @raise jmx.ClientException:jee_discoverer
        @raise jmx.AccessDeniedException:
        '''
        objectName = factory.getObjectName()
        return self._getProvider().invokeMBeanMethod(objectName, "getManagedConnectionFactoryAttribute",
                    array(["java.lang.String"], String), array([attribute], Object))

    def getUrlForManagedFactory(self, factory):
        return self.__getManagedFactoryAttribute(factory, 'ConnectionURL')

    def getDriverClassForManagedFactory(self, factory):
        return self.__getManagedFactoryAttribute(factory, 'DriverClass')

    def getUserNameForManagedFactory(self, factory):
        return self.__getManagedFactoryAttribute(factory, 'UserName')


class JvmDiscovererByJmx(jee_discoverer.HasJmxProvider):
    def __init__(self, provider):
        r'@types: jmx.Provider'
        jee_discoverer.HasJmxProvider.__init__(self, provider)

    def discoverJvm(self):
        '''
        @types: -> jee.Jvm or None
        @raise jmx.ClientException
        @raise jmx.AccessDeniedException
        '''
        try:
            runtimeName = self._getSystemPropertyValue('java.runtime.name')
            buildNumber = self._getSystemPropertyValue('java.runtime.version')
        except (Exception, JException):
            logger.warnException('Failed to discover JVM information')
        else:
            if runtimeName and buildNumber:
                jvmName = '%s (build %s)' % (runtimeName, buildNumber)
                jvm = jee.Jvm(jvmName)
                jvmBean = fptools.safeFunc(self.getJvmBean)()
                if jvmBean:
                    jvm.javaVersion = jvmBean.JavaVersion or jvmBean.javaVersion
                    jvm.javaVendor = jvmBean.JavaVendor or jvmBean.javaVendor
                    objectName = jvmBean.ObjectName
                    jvm.setObjectName(objectName)
                serverInfoBean = fptools.safeFunc(self.getServerInfo)()
                if serverInfoBean:
                    jvm.osType = serverInfoBean.OSName
                    jvm.osVersion = serverInfoBean.OSVersion
                return jvm

    def getJvmBean(self):
        attributes = ('JavaVersion', 'javaVersion',
                      'JavaVendor', 'javaVendor')
        jvmQuery = jmx.QueryByPattern('jboss.management.local:j2eeType', 'JVM',
                                      *attributes)
        # there is only one jvm bean on each server:
        return self._getBeans(jvmQuery)[0]

    def getServerInfo(self):
        attributes = ('OSVersion', 'OSName')
        serverInfoQuery = jmx.QueryByPattern('jboss.system:type',
                                             'ServerInfo', *attributes)
        # there is only one ServerInfo bean on each server
        return self._getBeans(serverInfoQuery)[0]

    def _getBeans(self, query):
        jmxProvider = self._getProvider()
        queryResult = jmxProvider.execute(query)
        if not queryResult:
            raise jmx.NoItemsFound()
        return queryResult

    def _getSystemPropertyValue(self, name):
        propertiesBbean = 'jboss:type=Service,name=SystemProperties'
        paramType = array(["java.lang.String"], String)
        jmxProvider = self._getProvider()
        return jmxProvider.invokeMBeanMethod(propertiesBbean, 'get', paramType,
                                             array([name], Object))


def _isServerEnvironmentProperty(value, propertyName = None):
    '''check if value is Jboss Environment Property (i.e. ${jboss.bind.address}) and equals defined propertyName
    @types: str, str -> bool
    '''
    if value and re.match('\$\{jboss\..+\}', value):
        if not propertyName:
            return 1
        else:
            return re.match('\$\{(jboss\..+)\}', value).group(1) == propertyName and 1 or 0
    return 0

def createServerRuntime(commandLine, ip):
    '''@types: str, str, jee.ProductInstance -> jboss.ServerRuntime'''
    commandLineDescriptor = jee.JvmCommandLineDescriptor(commandLine)
    return ServerRuntime(commandLineDescriptor, ip)

def _extractInstallDirPathFromEndorsedLibsOrRunJar(libPath, fs):
    ''' JBoss install Dir can be extracted from:
    - run.jar path: <JBOSS_HOME>/bin/run.jar or
    - java.endorsed.dirs: <JBOSS_HOME>/lib/endorsed '''
    # to be sure that we've got correct dirName we need to add one slash to end of lib-path
    if not (libPath and libPath.endswith('/') or libPath.endswith('\\')):
        libPath = '%s/' % libPath
    path = file_system.getPath(fs)
    # take 2 upper dirs from endorsed lib dir, i.e. from /opt/jboss-4.0.5.GA/lib/endorsed we'll take /opt/jboss-4.0.5.GA
    installDirPath = path.dirName(path.dirName(path.dirName(libPath)))
    # endorsed lib in Mercury AS located in bin-dir, take yet one dir upper:
    if installDirPath and path.baseName(installDirPath) == 'bin':
        installDirPath = path.dirName(installDirPath)
    return installDirPath

def discoverHomeDirPath(fs, serverSystemProperties, cmdLineElements):
    ''' JBoss HomeDir can be found in several ways:
    - by system properties: jboss.home.dir and jboss.home.url
    - by 2 dirs up from run.jar defined in classPath
    - by 2 dirs up from path defined in system property java.endorsed.dirs
    @types: str, jboss_discoverer.SystemProperties, list[jee.CmdLineElement] -> str '''
    fsPath = file_system.getPath(fs)
    homeDirPath = None
    homeDir = serverSystemProperties.get('jboss.home.dir')
    homeUrl = serverSystemProperties.get('jboss.home.url')
    endorsedLibDir = serverSystemProperties.get('java.endorsed.dirs')
    # search all classPath definitions:
    isClassPathElement = (lambda e: e.getName() in ('java.class.path', '-cp', '-C', '-classpath', '--classpath', '-jar'))
    classPathDefinitions = map(jee.CmdLineElement.getValue,
                       filter(isClassPathElement, cmdLineElements))
    # take JBoss homeDir from System Property 'jboss.home.dir'
    if homeDir:
        homeDirPath = fsPath.dirName(homeDir)
    # try to get it from 'jboss.home.url'
    elif homeUrl:
        homeDirPath = fsPath.dirName(SystemProperties().getFilePathFromURLValue(homeUrl))
    # try to get JBoss homeDir by 2 dirs up from JBoss run.jar in classPath
    elif classPathDefinitions:
        # split each of classPathList to separate paths and search run.jar:
        for classPathList in classPathDefinitions:
            # check what kind of separator using to split classpath,
            # in case of one elementh with no separator we are checking that ':' char not placed on 2nd position to prevent split C:\<folder>
            separator = classPathList.find(';') == -1 and classPathList[1] != ':' and ':' or ';'
            classPathElements = classPathList.split(separator)
            # search run.jar on each element of list and take 2 dir upper:
            for path in classPathElements:
                if path.lower().endswith('run.jar'):
                    homeDirPath = fsPath.isAbsolute(path) and fsPath.dirName(fsPath.dirName(path))
                    if homeDirPath: break
    # at last, try to get homeDir by 2 dirs up from 'java.endorsed.dirs'
    elif endorsedLibDir:
        # to be sure that we've got correct dirName we need to add one slash to end of lib-path
        if not (endorsedLibDir.endswith('/') or endorsedLibDir.endswith('\\')):
            endorsedLibDir = '%s/' % endorsedLibDir
        homeDirPath = fsPath.dirName(fsPath.dirName(fsPath.dirName(endorsedLibDir)))
        # endorsed lib in Mercury AS located in bin-dir, take yet one dir upper:
        if homeDirPath and fsPath.baseName(homeDirPath) == 'bin':
            homeDirPath = fsPath.dirName(homeDirPath)
    return homeDirPath

def discoverServerHomeDirPath(fs, serverName, jbossHomePath, serverSystemProperties):
    ''' Server HomeDir can be found by several ways:
        - by system properties: 'jboss.server.home.dir' or 'jboss.server.home.url'
        - by concatenation of 'jboss.server.base.dir' or 'jboss.server.base.url' + 'jboss.server.name'
    @types: file_system.FileSystem, str, str, jboss_discoverer.SystemProperties -> str '''
    serverHomeDirPath = None
    fsPath = file_system.getPath(fs)
    serverHomeDir = serverSystemProperties.get('jboss.server.home.dir')
    serverHomeUrl = serverSystemProperties.get('jboss.server.home.url')
    serverBaseDir = serverSystemProperties.get('jboss.server.base.dir')
    serverBaseUrl = serverSystemProperties.get('jboss.server.base.url')
    # take JBoss homeDir from System Property 'jboss.server.home.dir'
    if serverHomeDir:
        serverHomeDirPath = serverHomeDir
    # try to get it from 'jboss.server.home.url'
    elif serverHomeUrl:
        serverHomeDirPath = SystemProperties().getFilePathFromURLValue(serverHomeUrl)
    elif serverName:
        # try to get it from 'jboss.server.base.dir' + 'jboss.server.name'
        if serverBaseDir: serverHomeDirPath = fsPath.join(serverBaseDir, serverName)
        # at last try to get it from 'jboss.server.base.url' + 'jboss.server.name'
        elif serverBaseUrl: serverHomeDirPath = fsPath.join(SystemProperties().getFilePathFromURLValue(serverBaseUrl), serverName)
        # default location of server home:
        elif jbossHomePath:
            serverHomeDirPath = fsPath.join(jbossHomePath, 'server', serverName)
    return serverHomeDirPath

def discoverServerConfigPath(fs, serverConfigUrl, serverHomePath):
    ''' Server Config Path:
        - by default defined to: <serverHomePath>/conf
        - can be overridden by System Property 'jboss.server.config.url'
    @type: str, str -> str '''
    serverConfigDir = None
    fsPath = file_system.getPath(fs)
    if serverConfigUrl: # custom config directory:
        serverConfigDir = fsPath.normalizePath(SystemProperties().getFilePathFromURLValue(serverConfigUrl))
    else: # default location of server config directory:
        serverConfigDir = fsPath.join(serverHomePath, 'conf')
    return serverConfigDir

class ProfileLayout(jee_discoverer.Layout):

    def __init__(self, fs, serverConfigPath):
        '''@types: str, str, file_system.FileSystem'''
        jee_discoverer.Layout.__init__(self, fs)
        path = self.path()
        self.__serverConfigPath = path.absolutePath( serverConfigPath )

    def getServerConfigPath(self):
        return self.__serverConfigPath

    def getProfilePath(self):
        return self.path().join(self.getServerConfigPath(), 'bootstrap', 'profile.xml')

#class ProfileParser(jee_discoverer.BaseXmlParser):
#
#    configFile = None
#    bindingsDir = None
#    applicationsDirList = []
#    try:
#        profileContent = fsPath.getFile(fsPath.join(serverConfigPath, 'bootstrap', 'profile.xml'),
#                                               [file_topology.FileAttrs.CONTENT]).content
#        parser = ()
#        document = parser._buildDocumentForXpath(profileContent, namespaceAware = 0)
#        xpath = parser._getXpath()
#        # request suitable for JBoss 5.0.0 and 5.0.1
#        configFile = xpath.evaluate(r'deployment/bean[@class="org.jboss.system.server.profileservice.VFSBootstrapScannerImpl"]/property[@name="URIList"]/list/value/text()', document, XPathConstants.STRING)
#        deployDirs = xpath.evaluate(r'deployment/bean[@class="org.jboss.system.server.profileservice.VFSDeploymentScannerImpl"]/property[@name="URIList"]/list/value/text()', document, XPathConstants.STRING)
#        if not configFile:
#            # request suitable for JBoss 5.0 EAP, 5.1, 5.1 EAP, 6.0 and 6.1:
#            properties = xpath.evaluate(r'deployment/bean[@class="org.jboss.system.server.profileservice.StaticClusteredProfileFactory"]', document, XPathConstants.NODESET)
#            configFile = xpath.evaluate(r'property[@name="bootstrapURI"]/text()', properties, XPathConstants.STRING)
#            bindingsDir = xpath.evaluate(r'property[@name="bindingsURI"]/text()', properties, XPathConstants.STRING)
#            deployDirs = xpath.evaluate(r'property[@name="applicationURIs"]/list/value/text()', properties, XPathConstants.STRING)
#            if deployDirs:
#                applicationsDirList = deployDirs.splitlines()
#    except (Exception, JException):
#        logger.debugException('Failed to get info from profiles.xml')
#    return configFile, bindingsDir, applicationsDirList

class ProfileDiscoverer(jee_discoverer.DiscovererByShell):
    def __init__(self, shell, layout, parser):
        jee_discoverer.DiscovererByShell.__init__(self, shell, layout)
        self.__parser = parser

    def getParser(self):
        return self.__parser

    def discoverConfigFilePathName(self):
        configFile = None
        try:
            path = self.getLayout().getProfilePath()
            content = self._getShell().getXML(path)
            configFile = self.getParser().parseCustomConfigFileName(content)
        except (Exception, JException):
            logger.debug('Failed to discover JBoss config file name from file profile.xml')
        return configFile

    def discoverBindingsConfigDir(self):
        bindinsConfigDir = None
        try:
            path = self.getLayout().getProfilePath()
            content = self._getShell().getXML(path)
            bindinsConfigDir = self.getParser().parseBindingManagerConfigPath(content)
        except (Exception, JException):
            logger.debug('Failed to discover JBoss binding config dir from file profile.xml')
        return bindinsConfigDir

    def discoverResourcesDirsList(self):
        resoucesDirsList = []
        try:
            path = self.getLayout().getProfilePath()
            content = self._getShell().getXML(path)
            resoucesDirsList = self.getParser().parseResourcesDirsList(content)
        except:
            logger.debug('Failed to discover JEE Resources dirs from file profile.xml')
        return resoucesDirsList

def createServerLayout(fs, configFile, bindingConfig, resourcesDirsList, platformTrait):
    '''@types: jboss.ServerRuntime, file_system.FileSystem -> jboss.BaseServerLayout'''
    layoutClass = platformTrait.getAppropriateClass(ServerLayoutV3, ServerLayoutV4, ServerLayoutV43EAP, ServerLayoutV5, ServerLayoutV6)
    return layoutClass(fs, configFile, bindingConfig, resourcesDirsList)

def createServerDiscovererByShell(shell, layout, configParser, platformTrait):
    '@types: shellutils.Shell, BaseServerLayout, entity.PlatformTrait -> ServerDiscovererByShell'
    discovererClass = platformTrait.getAppropriateClass(ServerDiscovererByShell, ServerDiscovererByShellV5, ServerDiscovererByShellV7)
    return discovererClass(shell, layout, configParser)

def createDatasourceDiscovererByJmx(jmxProvider, platformTrait):
    discovererClass = platformTrait.getAppropriateClass(DatasourceDiscovererByJmx, DatasourceDiscovererByJmxV7)
    return discovererClass(jmxProvider)

def createJmsDiscovererByJmx(jmxProvider, platformTrait):
    discovererClass = platformTrait.getAppropriateClass(JmsDiscovererByJmx, JmsDiscovererByJmxV5, JmsDiscovererByJmxV6, JmsDiscovererByJmxV7)
    return discovererClass(jmxProvider)

def createJmsDiscovererByShell(shell, layout, serverConfigParser, platformTrait):
    discovererClass = platformTrait.getAppropriateClass(JmsDiscovererByShell, JmsDiscovererByShellV5, JmsDiscovererByShellV6, JmsDiscovererByShellV7)
    return discovererClass(shell, layout, serverConfigParser)

def createApplicationDiscovererByJmx(jmxProvider, platformTrait):
    discovererClass = platformTrait.getAppropriateClass(ApplicationDiscovererByJmxV34, ApplicationDiscovererByJmxV56, ApplicationDiscovererByJmxV7)
    discoverer = discovererClass(jmxProvider)
    return discoverer

def createServerConfigParser(loadExternalDTD, platformTrait):
    parserClass = platformTrait.getAppropriateClass(ServerConfigParserV30, ServerConfigParserV34, ServerConfigParserV5, ServerConfigParserV6, ServerConfigParserV7)
    return parserClass(loadExternalDTD)

def createApplicationLayout(fs, serverBaseDir, deployDirsList, platformTrait):
    discovererClass = platformTrait.getAppropriateClass(ApplicationLayoutV30, ApplicationLayoutV32, ApplicationLayoutV4, ApplicationLayoutV500, ApplicationLayoutV5, ApplicationLayoutV6)
    return discovererClass(fs, serverBaseDir, deployDirsList)

class BindingsConfigsLayout(jee_discoverer.Layout):

    def __init__(self, fs, bindingsDirs):
        jee_discoverer.Layout.__init__(self, fs)
        self.__bindingsDirs = []
        self.__bindingsDirs.extend(bindingsDirs)

    def getBindingsDirs(self):
        return self.__bindingsDirs


class BootstrapLayout(jee_discoverer.Layout):

    def __init__(self, fs, serverConfigDir):
        jee_discoverer.Layout.__init__(self, fs)
        pathUtil = file_system.getPath(fs)
        self.__serverConfigDir = serverConfigDir
        self.__bootstrapXml = pathUtil.join(serverConfigDir, 'bootstrap.xml')

    def getServerConfigDir(self):
        return self.__serverConfigDir

    def getBootstrapPath(self):
        return self.__bootstrapXml


class ResourcesLayout(jee_discoverer.Layout):

    def __init__(self, fs, resourcesDirs):
        jee_discoverer.Layout.__init__(self, fs)
        self.__resourcesDirsList = []
        self.__resourcesDirsList.extend(resourcesDirs)

    def getResourcesDirsList(self):
        return self.__resourcesDirsList


class BaseJbossXmlParser(jee_discoverer.BaseXmlParser):

    def _buildDocumentForXpath(self, content, namespaceAware=0):
        return jee_discoverer.BaseXmlParser._buildDocumentForXpath(self,
                                       content, namespaceAware=namespaceAware)

    def _getBeanPatternByClassName(self, className):
        return r'"'.join(('deployment/bean[@class=', className, ']'))

    def _getBeanPatternByCode(self, code):
        return r'"'.join(('server/mbean[@code=', code, ']'))

    def __getXpathEntityByPattern(self, document, pattern, returnType):
        xpath = self._getXpath()
        return xpath.evaluate(pattern, document, returnType)

    def _getNodeSetByPattern(self, document, pattern):
        return self.__getXpathEntityByPattern(document, pattern, XPATH_NODESET)

    def _getNodeSetTextContentByPattern(self, document, pattern):
        fn = lambda x: x.getTextContent()
        nodeset = self._getNodeSetByPattern(document, pattern)
        list_ = self._getListFromNodeSet(nodeset)
        return map(fn, list_)

    def _getListFromNodeSet(self, nodeset):
        list_ = []
        for nodeIndex in range(0, nodeset.getLength()):
            list_.append(nodeset.item(nodeIndex))
        return list_

    def _getNodeByPattern(self, content, pattern):
        return self.__getXpathEntityByPattern(content, pattern, XPATH_NODE)

    def _getStringByPattern(self, document, pattern):
        return self.__getXpathEntityByPattern(document, pattern, XPATH_STRING)

    def _hasConfig(self, content, pattern):
        return self._getNodeSetByPattern(content, pattern).getLength()

    def _getMBeanAttribute(self, mbean, attribute):
        ##TODO: add parsing of all pairs, test for quotes inside pairs
        # cut out domain if it exists
        commaSeparatedAttributes = (mbean.split(':') and mbean.split(':')[-1]
                                    or mbean)
        attributePairs = commaSeparatedAttributes.split(',')
        for attibutePair in attributePairs:
            if attibutePair.split('='):
                key, value = attibutePair.split('=')
                if key == attribute:
                    return value


class BootstrapParser(BaseJbossXmlParser):

    __PROFILE_SERVICE_PATTERN = 'org.jboss.system.server.profileservice'

    PROFILE_FACTORY_BEAN_PATTERN_V5 = 'repository.StaticProfileFactory'
    CLUSTERED_PROFILE_FACTORY_PATTERN_V5 = 'StaticClusteredProfileFactory'
    PROFILE_FACTORY_BEAN_PATTERN_V6 = 'bootstrap.StaticBootstrapProfileFactory'
    CLUSTERED_PROFILE_FACTORY_PATTERN_V6 = (
                                    'bootstrap.StaticClusteredProfileFactory')
    BOOTSRAP_SCANNER_PATTERN_V500 = 'VFSDeployerScannerImpl'
    DEPLOYMENT_SCANNER_PATTERN_V500 = 'VFSDeploymentScannerImpl'
    DEPLOYMENT_REPOSITORY_PATTERN_V500 = 'repository.SerializableDeploymentRepositoryFactory'

    __BINDING_SERVICE_PATTERN = 'org.jboss.services.binding'
    BINDING_MANAGER_PATTERN = 'ServiceBindingManager'   # 5.0.1.GA
    BINDING_STORE = 'impl.PojoServiceBindingStore'      # 5.0.1.GA
    BINDING_SET = 'impl.ServiceBindingSet'              # 5.0.1.GA
    BINDING_METADATA = 'ServiceBindingMetadata'         # 5.0.1.GA


    def hasProfileFactory(self, content):
        patternList = [self.PROFILE_FACTORY_BEAN_PATTERN_V5,
                       self.CLUSTERED_PROFILE_FACTORY_PATTERN_V5,
                       self.PROFILE_FACTORY_BEAN_PATTERN_V6,
                       self.CLUSTERED_PROFILE_FACTORY_PATTERN_V6]
        # generate full name of classes:
        fn = lambda a: '.'.join((self.__PROFILE_SERVICE_PATTERN, a))
        appendedList = map(fn, patternList)
        # xpath pattern:
        pattern = '|'.join(map(self._getBeanPatternByClassName, appendedList))
        return self._hasConfig(content, pattern)

    def hasBootstrapScanner(self, content):
        className = '.'.join((self.__PROFILE_SERVICE_PATTERN,
                              self.BOOTSRAP_SCANNER_PATTERN_V500))
        pattern = self._getBeanPatternByClassName(className)
        return self._hasConfig(content, pattern)

    def hasDeploymentScanner(self, content):
        className = '.'.join((self.__PROFILE_SERVICE_PATTERN,
                              self.DEPLOYMENT_SCANNER_PATTERN_V500))
        pattern = self._getBeanPatternByClassName(className)
        return self._hasConfig(content, pattern)

    def hasDeploymentRepository(self, content):
        className = '.'.join((self.__PROFILE_SERVICE_PATTERN,
                              self.DEPLOYMENT_REPOSITORY_PATTERN_V500))
        pattern = self._getBeanPatternByClassName(className)
        return self._hasConfig(content, pattern)

    def hasBindingManager(self, content):
        className = '.'.join((self.__BINDING_SERVICE_PATTERN,
                              self.BINDING_MANAGER_PATTERN))
        pattern = self._getBeanPatternByClassName(className)
        return self._hasConfig(content, pattern)

    def parseCustomConfigsFileNames(self, content):
        patternList = [self.BOOTSRAP_SCANNER_PATTERN_V500,
                       self.PROFILE_FACTORY_BEAN_PATTERN_V5,
                       self.CLUSTERED_PROFILE_FACTORY_PATTERN_V5,
                       self.PROFILE_FACTORY_BEAN_PATTERN_V6,
                       self.CLUSTERED_PROFILE_FACTORY_PATTERN_V6]
        # generate full name of classes:
        fn = lambda a: '.'.join((self.__PROFILE_SERVICE_PATTERN, a))
        appendedList = map(fn, patternList)
        # xpath pattern:
        beansXpathPattern = map(self._getBeanPatternByClassName, appendedList)
        uriList = lambda a: '/'.join((a,
                                      'property[@name="URIList"]/list/value'))
        bootstrapURI = lambda a: '/'.join((a,
                                           'property[@name="bootstrapURI"]'))
        pattern = '|'.join(map(uriList, beansXpathPattern)
                           + map(bootstrapURI, beansXpathPattern))
        return self._getNodeSetTextContentByPattern(content, pattern)

    def parseResourceDirsList(self, content):
        patternList = [self.DEPLOYMENT_SCANNER_PATTERN_V500,
                       self.DEPLOYMENT_REPOSITORY_PATTERN_V500,
                       self.PROFILE_FACTORY_BEAN_PATTERN_V5,
                       self.CLUSTERED_PROFILE_FACTORY_PATTERN_V5,
                       self.PROFILE_FACTORY_BEAN_PATTERN_V6,
                       self.CLUSTERED_PROFILE_FACTORY_PATTERN_V6]
        # generate full name of classes:
        fn = lambda a: '.'.join((self.__PROFILE_SERVICE_PATTERN, a))
        appendedList = map(fn, patternList)
        # xpath pattern:
        beansXpathPattern = map(self._getBeanPatternByClassName, appendedList)
        uriList = lambda a: '/'.join((a,
                                      'property[@name="URIList"]/list/value'))
        appArray = lambda a: '/'.join((a,
                              'property[@name="applicationURIs"]/array/value'))
        appList = lambda a: '/'.join((a,
                              'property[@name="applicationURIs"]/list/value'))
        pattern = '|'.join(map(uriList, beansXpathPattern)
                           + map(appList, beansXpathPattern)
                           + map(appArray, beansXpathPattern))
        return self._getNodeSetTextContentByPattern(content, pattern)

    def parseBindingsDir(self, content):
        patternList = [self.PROFILE_FACTORY_BEAN_PATTERN_V5,
                       self.CLUSTERED_PROFILE_FACTORY_PATTERN_V5,
                       self.PROFILE_FACTORY_BEAN_PATTERN_V6,
                       self.CLUSTERED_PROFILE_FACTORY_PATTERN_V6]
        # generate full name of classes:
        fn = lambda a: '.'.join((self.__PROFILE_SERVICE_PATTERN, a))
        appendedList = map(fn, patternList)
        # xpath pattern:
        beansXpathPattern = map(self._getBeanPatternByClassName, appendedList)
        uriList = lambda a: '/'.join((a, 'property[@name="bindingsURI"]'))
        pattern = '|'.join(map(uriList, beansXpathPattern))
        return self._getNodeSetTextContentByPattern(content, pattern)

    def parseFarmDirsList(self, content):
        patternList = [self.PROFILE_FACTORY_BEAN_PATTERN_V5,
                       self.CLUSTERED_PROFILE_FACTORY_PATTERN_V5,
                       self.PROFILE_FACTORY_BEAN_PATTERN_V6,
                       self.CLUSTERED_PROFILE_FACTORY_PATTERN_V6]
        # generate full name of classes:
        fn = lambda a: '.'.join((self.__PROFILE_SERVICE_PATTERN, a))
        appendedList = map(fn, patternList)
        # xpath pattern:
        beansXpathPattern = map(self._getBeanPatternByClassName, appendedList)
        uriList = lambda a: '/'.join((a,
                                      'property[@name="farmURIs"]/list/value'))
        pattern = '|'.join(map(uriList, beansXpathPattern))
        return self._getNodeSetTextContentByPattern(content, pattern)

    def parseBoostrapConfigFiles(self, content):
        pattern = r'bootstrap/url'
        return self._getNodeSetTextContentByPattern(content, pattern)


class BeansParser(BaseJbossXmlParser):

    def __getHAProfileManagerBeanPattern(self):
        # JBoss 5-6
        className = 'org.jboss.ha.singleton.HASingletonProfileManager'
        return self._getBeanPatternByClassName(className)

    def __getHASingletonControllerBeanPattern(self):
        # JBoss 3-4
        className = 'org.jboss.ha.singleton.HASingletonController'
        return self._getBeanPatternByClassName(className)

    def __getHAPartititonBeanPatternV4(self):
        code = 'org.jboss.ha.framework.server.ClusterPartition'
        return self._getBeanPatternByCode(code)

    def __getHAPartititonBeanPatternV5(self):
        className = 'org.jboss.ha.framework.server.ClusterPartition'
        return self._getBeanPatternByClassName(className)

    def hasHornetQServer(self, content):
        className = 'org.hornetq.core.server.impl.HornetQServerImpl'
        pattern = self._getBeanPatternByClassName(className)
        return self._hasConfig(content, pattern)

    def hasClusterPartition(self, content):
        pattern = '|'.join((self.__getHAPartititonBeanPatternV4(),
                            self.__getHAPartititonBeanPatternV5()))
        return self._hasConfig(content, pattern)

    def hasHAProfileManager(self, content):
        pattern = '|'.join((self.__getHASingletonControllerBeanPattern(),
                            self.__getHAProfileManagerBeanPattern()))
        return self._hasConfig(content, pattern)

    def parseHAResourcesDirs(self, content):
        resources = []
        patternV56 = '/'.join((self.__getHAProfileManagerBeanPattern(),
                               'property[@name="URIList"]/list/value'))
        patternV4 = '/'.join((self.__getHASingletonControllerBeanPattern(),
                      '*[contains(@name,"argetStartMethodArgument")]/text()'))
        resourcesURIs = self._getNodeSetByPattern(content, patternV56)
        for uriIndex in range(0, resourcesURIs.getLength()):
            uri = resourcesURIs.item(uriIndex).getTextContent()
            if uri:
                resources.append(uri)
        if not resourcesURIs.getLength():
            targetStartMethodArg = self._getStringByPattern(content, patternV4)
            if targetStartMethodArg:
                resources.append(targetStartMethodArg)
        return resources

    def parseClusterName(self, content):
        partitionNamePattern = 'property[@name="partitionName"]/text()'
        patternV4 = '/'.join((self.__getHAPartititonBeanPatternV4(),
                              partitionNamePattern))
        patternV5 = '/'.join((self.__getHAPartititonBeanPatternV5(),
                              partitionNamePattern))
        clusterName = (self._getStringByPattern(content, patternV4)
                       or self._getStringByPattern(content, patternV5))
        if not clusterName:
            clusterNodes = self._getNodeSetByPattern(content,
                                         self.__getHAPartititonBeanPatternV4())
            if clusterNodes.getLength() == 1:
                clusterNode = clusterNodes.item(0)
                nameMbean = clusterNode.getAttribute('name')
                if nameMbean:
                    clusterName = self._getMBeanAttribute(nameMbean, 'service')
        return clusterName


class DsParser(BaseJbossXmlParser):

    DATASOURCES_PATTERN = 'datasources/*'
    CONNECTION_FACTORIES_PATTERN = 'connection-factories/*'

    def __composePattern(self, name):
        return '/'.join((name, 'text()'))

    def __composeXAPropertyPattern(self, name):
        return '"'.join(('xa-datasource-property[@name=', name, ']/text()'))

    def __getJndiNamePattern(self):
        return self.__composePattern('jndi-name')

    def __getUserNamePattern(self):
        return self.__composePattern('user-name')

    def __getXaUserNamePattern(self):
        return self.__composeXAPropertyPattern('User')

    def __getConnectionUrlPattern(self):
        return self.__composePattern('connection-url')

    def __getXaConnectionUrlPattern(self):
        return self.__composeXAPropertyPattern('URL')

    def __getDriverClassPattern(self):
        return self.__composePattern('driver-class')

    def __getXaDriverClassPattern(self):
        return self.__composePattern('xa-datasource-class')

    def __getXaDescriptionPattern(self):
        return self.__composeXAPropertyPattern('Description')

    def __getXaPortNumberPattern(self):
        return self.__composeXAPropertyPattern('PortNumber')

    def __getXaDatabaseNamePattern(self):
        return self.__composeXAPropertyPattern('DatabaseName')

    def __getXaServerNamePattern(self):
        return self.__composeXAPropertyPattern('ServerName')

    def __getMaxCapacityPattern(self):
        return self.__composePattern('max-pool-size')

    def hasDatasources(self, content):
        return self._hasConfig(content, self.DATASOURCES_PATTERN)

    def hasConnectionFactories(self, content):
        return self._hasConfig(content, self.CONNECTION_FACTORIES_PATTERN)

    def parseDatasources(self, content):
        datasources = []
        jndiNamePattern = self.__getJndiNamePattern()
        userNamePattern = '|'.join((self.__getUserNamePattern(),
                                    self.__getXaUserNamePattern()))
        connectionUrlPattern = '|'.join((self.__getConnectionUrlPattern(),
                                         self.__getXaConnectionUrlPattern()))
        driverClassPattern = '|'.join((self.__getDriverClassPattern(),
                                       self.__getXaDriverClassPattern()))
        descriptionPattern = self.__getXaDescriptionPattern()
        portNumberPattern = self.__getXaPortNumberPattern()
        databaseNamePattern = self.__getXaDatabaseNamePattern()
        serverNamePattern = self.__getXaServerNamePattern()
        maxCapacityPattern = self.__getMaxCapacityPattern()
        dsNodes = self._getNodeSetByPattern(content, self.DATASOURCES_PATTERN)
        xpath = self._getXpath()
        for dsIndex in range(0, dsNodes.getLength()):
            dsNode = dsNodes.item(dsIndex)
            ds = DatasourceDescriptor()
            ds.jndiName = xpath.evaluate(jndiNamePattern, dsNode, XPATH_STRING)
            if not ds.jndiName:
                logger.debug('Datasource jndi name was not found')
                continue
            ds.userName = xpath.evaluate(userNamePattern, dsNode, XPATH_STRING)
            ds.connectionUrl = xpath.evaluate(connectionUrlPattern, dsNode, XPATH_STRING)
            ds.driverClass = xpath.evaluate(driverClassPattern, dsNode, XPATH_STRING)
            ds.description = xpath.evaluate(descriptionPattern, dsNode, XPATH_STRING)
            ds.portNumber = xpath.evaluate(portNumberPattern, dsNode, XPATH_STRING)
            ds.databaseName = xpath.evaluate(databaseNamePattern, dsNode, XPATH_STRING)
            if not ds.databaseName:
                #DB name also can be fetched from object name in depends tag
                objectNames = self._getNodeSetTextContentByPattern(dsNode,
                                                                   'depends')
                restoredObjectNames = map(jmx.restoreObjectName, objectNames)
                fn = lambda x: x.getKeyProperty('database')
                databaseNames = filter(fn, restoredObjectNames)
                ds.databaseName = databaseNames and databaseNames[0].getKeyProperty('database')
            ds.serverName = xpath.evaluate(serverNamePattern, dsNode, XPATH_STRING)
            ds.maxCapacity = xpath.evaluate(maxCapacityPattern, dsNode, XPATH_STRING)
            datasources.append(ds)
        return datasources


    def parseConnectionFactories(self, content):
        return []

def _createFileSystemRecursiveSearchEnabled(fs):

    class _FileSystemRecursiveSearchEnabled(fs.__class__):
        r''' Wrapper around file_system module interface created to provide missing
        functionality - recursive search.
        Only one method overriden - getFiles, where if "recursive" is enabled - behaviour changes a bit.
        As filter we expect to get subtype of
        '''
        def __init__(self, fs):
            r'@types: file_system.FileSystem'
            self.__fs = fs
            self.__pathUtil = file_system.getPath(fs)

        def __getattr__(self, name):
            return getattr(self.__fs, name)


        def _findFilesRecursively(self, path, filePattern):
            r'''@types: str, str -> list(str)
            @raise ValueError: Failed to find files recursively
            '''
            r'''@types: str, str -> list(str)
            @raise ValueError: Failed to find files recursively
            '''
            path = file_system.getPath(fs).normalizePath(path)
            findCommand = 'find -L ' + path + ' -name *' + filePattern + ' 2>/dev/null'
            if self._shell.isWinOs():
                if (path.find(' ') > 0) and (path[0] != '\"'):
                    path = r'"%s"' % path
                else:
                    path = path
                findCommand = 'dir %s /s /b | findstr %s' % (path, filePattern)
            output = self._shell.execCmd(findCommand)
            if self._shell.getLastCmdReturnCode() == 0 and self._shell.isWinOs() or not self._shell.isWinOs():
                return filter(lambda x: x!='' ,output.strip().splitlines())
            if output.lower().find("file not found") != -1:
                raise file_topology.PathNotFoundException()
            raise ValueError("Failed to find files recursively. %s" % output)

        def findFilesRecursively(self, baseDirPath, filters, fileAttrs = None):
            r'''@types: str, list(FileFilterByPattern), list(str) -> list(file_topology.File)
            @raise ValueError: No filters (FileFilterByPattern) specified to make a recursive file search
            '''
            # if filter is not specified - recursive search query becomes not deterministic
            if not filters:
                raise ValueError("No filters (FileFilterByPattern) specified to make a recursive file search")
            # if file attributes are note specified - default set is name and path
            fileAttrs = fileAttrs or [file_topology.FileAttrs.NAME, file_topology.FileAttrs.PATH]
            paths = []
            for filterObj in filters:
                try:
                    paths.extend(self._findFilesRecursively(baseDirPath, filterObj.filePattern))
                except file_topology.PathNotFoundException, pnfe:
                    logger.warn(str(pnfe))
                except (Exception, JException):
                    # TBD: not sure whether we have to swallow such exceptions
                    logger.warnException("Failed to find files for filter with file pattern %s" % filterObj.filePattern)
            files = []
            for path in filter(None, paths):
                try:
                    files.append(self.__fs.getFile(path, fileAttrs = fileAttrs))
                except file_topology.PathNotFoundException, pnfe:
                    logger.warn(str(pnfe))
                except (Exception, JException):
                    logger.warnException("Failed to get file %s" % path)
            return files


        def getFiles(self, path, recursive = 0, filters = [], fileAttrs = []):
            r'@types: str, bool, list(FileFilterByPattern), list(str) -> list(file_topology.File)'
            if recursive:
                return self.filter(self.findFilesRecursively(path, filters, fileAttrs), filters)
            else:
                return self.__fs.getFiles(path, filters = filters, fileAttrs = fileAttrs)
    return _FileSystemRecursiveSearchEnabled(fs)

class BeansDiscoverer(DiscovererByShellWithParser):

    class BeansFileFilter(file_system.FileFilter):

        def __init__(self):
            self.filePattern = 'beans.xml'

        def accept(self, file_):
            return file_.name.lower().endswith('-beans.xml')

    def discoverBeansConfigFiles(self):
        configs = []
        for path in self.getLayout().getDeployDirs():
            try:
                fs = self.getFs()
                files = fs.getFiles(path,
                                    recursive=1,
                                    filters=[self.BeansFileFilter()],
                                    fileAttrs=[file_topology.FileAttrs.NAME])
                ##TODO: remove join path and name
            except Exception:
                logger.debugException("Failed to get list of beans files")
            else:
                for file_ in files:
                    file_.path = self.path().join(path, file_.name)
                configs.extend(files)
        return configs

    def discoverHAResourcesDirs(self, haProfileManagerPath, systemProperties):
        haResourcesDirs = []
        try:
            fs = self.getLayout()._getFs()
            haProfileManagerConfig = fs.getFile(haProfileManagerPath,
                                            [file_topology.FileAttrs.CONTENT])
            parser = self.getParser()
            configContent = haProfileManagerConfig.content
            haResourcesDirs = parser.parseHAResourcesDirs(configContent)
            for resourceDir in haResourcesDirs:
                propertiesDiscoverer = self.getSystemPropertiesDiscoverer()
                resolvedDir = propertiesDiscoverer.resolveLine(resourceDir,
                                                           systemProperties)
                if resolvedDir:
                    haResourcesDirs.append(resolvedDir)
        except (Exception, JException):
            logger.debug('Failed to get HA Resources dir list')
        return haResourcesDirs

    def discoverClusterName(self, haClusterPartitionPath, systemProperties):
        try:
            fs = self.getLayout()._getFs()
            haClusterPartitionConfig = fs.getFile(haClusterPartitionPath,
                                          [file_topology.FileAttrs.CONTENT])
            parser = self.getParser()
            configContent = haClusterPartitionConfig.content
            clusterName = parser.parseClusterName(configContent)
            propertiesDiscoverer = self.getSystemPropertiesDiscoverer()
            return propertiesDiscoverer.resolveLine(clusterName,
                                                    systemProperties)
        except (Exception, JException):
            logger.debug('Failed to get Cluster name')


class ServiceParser(BaseJbossXmlParser):

    def __getJmsBeanPatternV34(self, pattern):
        code = ''.join(('org.jboss.mq.server.jmx.', pattern))
        return self._getBeanPatternByCode(code)

    def __getJmsBeanPatternV5(self, pattern):
        code = ''.join(('org.jboss.jms.server.destination.', pattern,
                        'Service'))
        return self._getBeanPatternByCode(code)

    def __getJmsBeanByPattern(self, pattern):
        # TODO: 6.0-6.1, EAP5.1 'hornetq-jms.xml'
        return '|'.join((self.__getJmsBeanPatternV34(pattern),
                         self.__getJmsBeanPatternV5(pattern)))

    def getJmsTopicBeanPattern(self):
        return self.__getJmsBeanByPattern('Topic')

    def hasJmsTopics(self, content):
        return self._hasConfig(content, self.getJmsTopicBeanPattern())

    def hasHornetQTopics(self, content):
        pattern = r'configuration/topic'
        return self._hasConfig(content, pattern)

    def getJmsQueueBeanPattern(self):
        return self.__getJmsBeanByPattern('Queue')

    def hasJmsQueues(self, content):
        return self._hasConfig(content, self.getJmsQueueBeanPattern())

    def hasHornetQQueues(self, content):
        pattern = r'configuration/queue'
        return self._hasConfig(content, pattern)

    def getJmsDestinationManagerBeanPattern(self):
        return self.__getJmsBeanByPattern('DestinationManager')

    def getJmsServerPeerBeanPattern(self):
        return self._getBeanPatternByCode('org.jboss.jms.server.ServerPeer')

    def hasJmsServerConfig(self, content):
        pattern = '|'.join((self.getJmsDestinationManagerBeanPattern(),
                            self.getJmsServerPeerBeanPattern()))
        return self._hasConfig(content, pattern)

    def __getJmsDomain(self, objectName):
        return objectName and objectName.split(':') and objectName.split(':')[0]

    def parseJmsServers(self, content):
        jmsServers = {}
        pattern = '|'.join((self.getJmsDestinationManagerBeanPattern(),
                            self.getJmsServerPeerBeanPattern()))
        serverNodes = self._getNodeSetByPattern(content, pattern)
        for serverIndex in range(0, serverNodes.getLength()):
            objectName = serverNodes.item(serverIndex).getAttribute('name')
            name = self.__getJmsDomain(objectName)
            if name:
                server = jms.Datasource(name)
                jmsServers[objectName] = server
        return jmsServers

    def hasJdbcDatasources(self, content):
        pattern = ('server/mbean[contains(@code,"ConnectionManager")]/'
                   'depends/mbean[contains(@code,"RARDeployment")]')
        return self._hasConfig(content, pattern)

    def __getJmsServerNamePatternV34(self):
        return 'depends[@optional-attribute-name="DestinationManager"]/text()'

    def __getJmsServerNamePatternV5(self):
        return 'depends[@optional-attribute-name="ServerPeer"]/text()'

    def __getJmsServerName(self, item):
        xpath = self._getXpath()
        pattern = '|'.join((self.__getJmsServerNamePatternV34(),
                            self.__getJmsServerNamePatternV5()))
        return str(xpath.evaluate(pattern, item, XPATH_STRING)).strip()

    def parseTopics(self, content):
        topics = {}
        topicNodes = self._getNodeSetByPattern(content, self.getJmsTopicBeanPattern())
        #nodes = mapNodes(identity, topicNodes)
        # servernames = map(self.__getJmsServerName, nodes)
        # mbeans = map(getAtttributeNameFn, nodes)
        # topics = dict(zip(mbeans, servernames))

        for topicIndex in range(0, topicNodes.getLength()):
            jmsServerName = self.__getJmsServerName(topicNodes.item(topicIndex))
            mbean = topicNodes.item(topicIndex).getAttribute('name')
#            name = self._getMBeanAttribute(mbean, 'name')
#            if name:
#                topic = jms.Topic(name)
#                topic.setObjectName(mbean)
            topics[mbean] = jmsServerName
        return topics

    def __parseHornetQDestination(self, content, destinationType):
        destinations = []
        destinationTypeBySignature = {
            'queue' : jms.Queue,
            'topic' : jms.Topic
        }
        pattern = ''.join((r'configuration/', destinationType))
#        pattern = r'configuration/topic | configuration/queue'
        destinationNodes = self._getNodeSetByPattern(content, pattern)
        for nodeIndex in range(0, destinationNodes.getLength()):
            destination = destinationNodes.item(nodeIndex)
            destinationType = destination.getNodeName()
            destinationName = destination.getAttribute('name')
            destinationJndiName = self._getStringByPattern(destination, r'entry/@name')
            destinationClass = destinationTypeBySignature.get(destinationType)
            if destinationClass:
                jmsDestination = destinationClass(destinationName)
                jmsDestination.setJndiName(destinationJndiName)
                destinations.append(jmsDestination)
        return destinations

    def parseHornetQTopics(self, content):
        return self.__parseHornetQDestination(content, 'topic')

    def parseHornetQQueues(self, content):
        return self.__parseHornetQDestination(content, 'queue')

    def parseQueues(self, content):
        queues = {}
        queueNodes = self._getNodeSetByPattern(content, self.getJmsQueueBeanPattern())
        for queueIndex in range(0, queueNodes.getLength()):
            jmsServerName = self.__getJmsServerName(queueNodes.item(queueIndex))
            mbean = queueNodes.item(queueIndex).getAttribute('name')
#            name = self._getMBeanAttribute(mbean, 'name')
#            if name:
            queues[mbean] = jmsServerName
        return queues


class ServiceDiscoverer(DiscovererByShellWithParser):

    class ServiceFileFilter(file_system.FileFilter):

        def __init__(self):
            self.filePattern = 'service.xml'

        def accept(self, file_):
            '@types: file_topology.File -> bool'
            return file_.name.lower().endswith('-service.xml')

    def discoverServiceConfigFiles(self):
        configs = []
        for path in self.getLayout().getDeployDirs():
            files = self.getLayout()._getFs().getFiles(path, recursive=1, filters=[self.ServiceFileFilter()])
            configs.extend(files)
        return configs

    def discoverJmsResources(self, serviceFiles):
        topics = {}
        queues = {}
        for file_ in serviceFiles:
            try:
                serviceFileContent = self.getLayout().getFileContent(file_).content
                if self.getParser().hasJmsTopics(serviceFileContent):
                    topics.update(self.getParser().parseTopics(serviceFileContent))
                if self.getParser().hasJmsQueues(serviceFileContent):
                    queues.update(self.getParser().parseQueues(serviceFileContent))
            except (Exception, JException):
                logger.debug('Failed to get JMS resources')
        return topics, queues

    def discoverJmsTopics(self, serviceFiles):
        resources = {}
        for file_ in serviceFiles:
            try:
                serviceFileContent = self.getLayout().getFileContent(file_).content
                if self.getParser().hasJmsTopics(serviceFileContent):
                    resources.update(self.getParser().parseTopics(serviceFileContent))
            except (Exception, JException):
                logger.debug('Failed to get JMS topics')
        return resources

    def discoverJmsQueues(self, serviceFiles):
        resources = {}
        for file_ in serviceFiles:
            try:
                serviceFileContent = self.getLayout().getFileContent(file_).content
                if self.getParser().hasJmsQueues(serviceFileContent):
                    resources.update(self.getParser().parseQueues(serviceFileContent))
            except (Exception, JException):
                logger.debug('Failed to get JMS resources')
        return resources

    def discoverJmsServers(self, jmsServerConfigs):
        jmsServers = []
        for file_ in jmsServerConfigs:
            try:
                configContent = self.getLayout().getFileContent(file_).content
                jmsServers.extend(self.getParser().parseJmsServers(configContent))
            except (Exception, JException):
                logger.debug("Failed to get JBoss MQ servers")
        return jmsServers


class BindingsConfigsDiscovererByShell(DiscovererByShellWithParser):

    class XmlFileFilter(file_system.FileFilter):

        def __init__(self):
            self.filePattern = '.xml'

        def accept(self, file_):
            return file_.name.lower().endswith('.xml')

    def __listXmlFiles(self):
        configs = []
        fs = self.getFs()
        layout = self.getLayout()
        for path in layout.getBindingsDirs():
            try:
                files = fs.getFiles(path, recursive=1,
                                    filters=[self.XmlFileFilter()],
                                    fileAttrs=[FILE_PATH])
            except Exception:
                logger.debugException("Failed to get list of beans files")
            else:
                configs.extend(files)
        return configs

    def discoverBindingsConfigFiles(self):
        configs = []
        fs = self.getFs()
        parser = self.getParser()
        for file_ in self.__listXmlFiles():
            try:
                path = file_.path
                config = fs.getFile(path, [FILE_CONTENT])
                content = config.content
                document = parser._buildDocumentForXpath(content)
            except Exception:
                logger.debugException("Failed to get file content")
            else:
                if parser.hasBindingManager(document):
                    configs.append(path)
        return configs


class BootstrapDiscovererByShell(DiscovererByShellWithParser):

    def discoverBootstrapConfigFiles(self, systemProperties):
        configs = []
        fs = self.getFs()
        layout = self.getLayout()
        parser = self.getParser()
        try:
            config = fs.getFile(layout.getBootstrapPath(), [FILE_CONTENT])
            content = config.content
            document = parser._buildDocumentForXpath(content)
        except Exception:
            logger.debugException("Failed to get content of bootstrap file")
        else:
            rawBootstrapConfigList = parser.parseBoostrapConfigFiles(document)
            relativeDir = layout.getServerConfigDir()
            configs.extend(self._resolvePathList(rawBootstrapConfigList,
                                             relativeDir, systemProperties))
        return configs

    def discoverServerConfigAndResources(self, bootstrapFiles,
                                         systemProperties):
        rawConfigList = []
        rawResourcesDirs = []
        rawBindingsDirs = []
        rawFarmDirs = []
        bindingConfigs = []
        fs = self.getFs()
        parser = self.getParser()
        for file_ in bootstrapFiles:
            try:
                config = fs.getFile(file_, [FILE_CONTENT])
                content = config.content
                document = parser._buildDocumentForXpath(content)
            except Exception:
                logger.debugException("Failed to get content of the file")
            else:
                if parser.hasProfileFactory(document):
                    configList = parser.parseCustomConfigsFileNames(document)
                    rawConfigList.extend(configList)
                    resourceDirs = parser.parseResourceDirsList(document)
                    rawResourcesDirs.extend(resourceDirs)
                    bindingsDirs = parser.parseBindingsDir(document)
                    # JBoss 6.0-6.1 using default location
                    defaultBindingsDir = '${jboss.server.home.url}conf/bindingservice.beans'
                    if defaultBindingsDir not in bindingsDirs:
                        bindingsDirs.append(defaultBindingsDir)
                    rawBindingsDirs.extend(bindingsDirs)
                    farmDirs = parser.parseFarmDirsList(document)
                    rawFarmDirs.extend(farmDirs)
                if parser.hasBootstrapScanner(document):
                    configList = parser.parseCustomConfigsFileNames(document)
                    rawConfigList.extend(configList)
                if (parser.hasDeploymentScanner(document) or
                    parser.hasDeploymentRepository(document)):
                    resourceDirs = parser.parseResourceDirsList(document)
                    rawResourcesDirs.extend(resourceDirs)
                if parser.hasBindingManager(document):
                    bindingConfigs.append(file_)
        relativeDir = systemProperties.get('jboss.server.url')
        configList = self._resolvePathList(rawConfigList, relativeDir,
                                           systemProperties)
        fn_getFile = lambda x: fs.getFile(x, [FILE_CONTENT, FILE_PATH])
        configFiles = map(fn_getFile, configList)
        resourcesDirs = self._resolvePathList(rawResourcesDirs, relativeDir,
                                              systemProperties)
        farmDirs = self._resolvePathList(rawFarmDirs, relativeDir,
                                         systemProperties)
        bindingsDirs = self._resolvePathList(rawBindingsDirs, relativeDir,
                                             systemProperties)
        return (configFiles, resourcesDirs, farmDirs, bindingsDirs,
                                                                bindingConfigs)


class ResourcesDiscovererByShell(DiscovererByShellWithParser):

    class BeansFileFilter(file_system.FileFilter):

        def __init__(self):
            self.filePattern = 'beans.xml'

        def accept(self, file_):
            return file_.name.lower().endswith('-beans.xml')

    class ServiceFileFilter(file_system.FileFilter):

        def __init__(self):
            self.filePattern = 'service.xml'

        def accept(self, file_):
            return file_.name.lower().endswith('-service.xml')

    class HornetQFileFilter(file_system.FileFilter):

        def __init__(self):
            self.filePattern = 'hornetq-jms.xml'

        def accept(self, file_):
            return file_.name.lower() == 'hornetq-jms.xml'

    class DsFileFilter(file_system.FileFilter):

        def __init__(self):
            self.filePattern = 'ds.xml'

        def accept(self, file_):
            return file_.name.lower().endswith('-ds.xml')

    def __listFilesByFilter(self, dirList, filter_):
        configs = []
        fs = self.getFs()

        for path in dirList:
            try:
                files = fs.getFiles(path, recursive=1,
                                    filters=[filter_],
                                    fileAttrs=[FILE_PATH])
            except Exception:
                logger.debugException("Failed to get file list")
            else:
                configs.extend(files)
        return configs

    def listBeansConfigFiles(self):
        filter_ = self.BeansFileFilter()
        layout = self.getLayout()
        dirList = layout.getResourcesDirsList()
        return self.__listFilesByFilter(dirList, filter_)

    def listServiceConfigFiles(self, dirList):
        filter_ = self.ServiceFileFilter()
        return self.__listFilesByFilter(dirList, filter_)

    def listHornetQConfigFiles(self, dirList):
        filter_ = self.HornetQFileFilter()
        return self.__listFilesByFilter(dirList, filter_)

    def listDsConfigFiles(self, dirList):
        filter_ = self.DsFileFilter()
        return self.__listFilesByFilter(dirList, filter_)

    def discoverResourcesByBeansFiles(self, systemProperties):
        haResDirs = []
        clusterName = None
        configFiles = []
        hornetQServer = False
        fs = self.getFs()
        parser = self.getParser()
        for file_ in self.listBeansConfigFiles():
            try:
                path = file_.path
                config = fs.getFile(path, [FILE_CONTENT, FILE_PATH])
                content = config.content
                document = parser._buildDocumentForXpath(content)
                if parser.hasHAProfileManager(document):
                    rawHaResDirs = parser.parseHAResourcesDirs(document)
                    relativeDir = systemProperties.get('jboss.server.url')
                    haResDirs.extend(self._resolvePathList(rawHaResDirs,
                                                           relativeDir,
                                                           systemProperties))
                    configFiles.append(config)
                if parser.hasClusterPartition(document):
                    rawClusterName = parser.parseClusterName(document)
                    propertiesDiscoverer = SystemPropertiesDiscoverer()
                    clusterName = \
                        propertiesDiscoverer.resolveLine(rawClusterName,
                                                         systemProperties)
                    configFiles.append(config)
                if parser.hasHornetQServer(document):
                    hornetQServer = True
                    configFiles.append(config)
            except (Exception, JException):
                logger.debug('Failed to get resources from *-beans.xml files')
        return haResDirs, clusterName, configFiles, hornetQServer

    def __resolveDatasourceDescriptorProperties(self, rawDatasourceDescriptor,
                                                systemProperties):
        datasource = DatasourceDescriptor()
        publicAttrs = [x for x in dir(rawDatasourceDescriptor)
                       if not x.startswith('_')]
        for attr in publicAttrs:
            value = getattr(rawDatasourceDescriptor, attr)
            if value is not None and isinstance(value, basestring):
                resolvedValue = systemProperties.resolveProperty(value)
                setattr(datasource, attr, resolvedValue)
        return datasource

    def __createDatasourceByDescriptor(self, dsDescriptor):
        ds = jee.Datasource(dsDescriptor.jndiName)
        ds.setJndiName(dsDescriptor.jndiName)
        if dsDescriptor.connectionUrl:
            ds.url = dsDescriptor.connectionUrl
        if dsDescriptor.description:
            ds.description = dsDescriptor.description
        if dsDescriptor.driverClass:
            ds.driverClass = dsDescriptor.driverClass
        if dsDescriptor.maxCapacity:
            ds.maxCapacity.set(dsDescriptor.maxCapacity)
        if dsDescriptor.userName:
            ds.userName = dsDescriptor.userName
        databaseName = dsDescriptor.databaseName
        if databaseName:
            ds.databaseName = databaseName
        address = dsDescriptor.serverName
        port = dsDescriptor.portNumber
        databaseServer = db.DatabaseServer(address, port)
        ds.setServer(databaseServer)
        databaseName and databaseServer.addDatabases(db.Database(databaseName))
        return ds

    def discoverResourcesByDsFiles(self, resourcesDirs, systemProperties):
        datasources = []
        configFiles = []
        fs = self.getFs()
        parser = self.getParser()
        for file_ in self.listDsConfigFiles(resourcesDirs):
            try:
                path = file_.path
                config = fs.getFile(path, [FILE_CONTENT, FILE_PATH])
                content = config.content
                document = parser._buildDocumentForXpath(content)
                if parser.hasDatasources(document):
                    rawDatasourceDescriptors = parser.parseDatasources(document)
                    fn = lambda x: self.__resolveDatasourceDescriptorProperties(x, systemProperties)
                    resolvedDatasourceDescriptors = map(fn, rawDatasourceDescriptors)
                    fn = lambda x: x.connectionUrl
                    fn = lambda x: x.databaseName
                    fn = lambda x: x.jndiName
                    dsWithName, dsWithoutName = (
                        fptools.partition(fn, resolvedDatasourceDescriptors))
                    if dsWithoutName:
                        logger.debug("Skipped %s datasources without jndi-name" % len(dsWithoutName))
                    jeeDatasources = map(self.__createDatasourceByDescriptor, dsWithName)
                    fn = lambda x: x.url
                    fn = lambda x: x.databaseName
                    datasources.extend(jeeDatasources)
                    configFiles.append(config)
#                #TODO: handle connection factories
#                if parser.hasConnectionFactories(document):
#                    rawConnectionFactories = \
#                        parser.parseConnectionFactories(document)
#                    connectionFactories.extend(rawConnectionFactories)
#                    configFiles.append(file_)

            except (Exception, JException):
                logger.debugException('Failed to get resources from *-ds.xml files')
        return datasources, configFiles

    def discoverResoucesByServiceFiles(self, resourcesDirs, systemProperties):
        jmsServers = {}
        topics = {}
        queues = {}
        configFiles = []
        fs = self.getFs()
        parser = self.getParser()
        for file_ in self.listServiceConfigFiles(resourcesDirs):
            try:
                path = file_.path
                config = fs.getFile(path, [FILE_CONTENT, FILE_PATH])
                content = config.content
                document = parser._buildDocumentForXpath(content)
                if parser.hasJmsServerConfig(document):
                    jmsServers.update(parser.parseJmsServers(document))
                    configFiles.append(config)
                if parser.hasJmsTopics(document):
                    jmsTopics = parser.parseTopics(document)
                    topics.update(jmsTopics)
                    configFiles.append(config)
                if parser.hasJmsQueues(document):
                    jmsQueues = parser.parseQueues(document)
                    queues.update(jmsQueues)
                    configFiles.append(config)
            except (Exception, JException):
                logger.debugException('Failed to get resources from *-service.xml files')
        return jmsServers, topics, queues, configFiles

    def discoverResourcesByHornetQConfiguration(self, resourcesDirs, systemProperties):
        topics = []
        queues = []
        configFiles = []
        fs = self.getFs()
        parser = self.getParser()
        for file_ in self.listHornetQConfigFiles(resourcesDirs):
            try:
                path = file_.path
                config = fs.getFile(path, [FILE_CONTENT, FILE_PATH])
                content = config.content
                document = parser._buildDocumentForXpath(content)
                if parser.hasHornetQTopics(document):
                    topics.extend(parser.parseHornetQTopics(document))
                    configFiles.append(config)
                if parser.hasHornetQQueues(document):
                    queues.extend(parser.parseHornetQQueues(document))
                    configFiles.append(config)
            except (Exception, JException):
                logger.debug('Failed to get resources from hornetq-jms.xml files')
        return topics, queues, configFiles


