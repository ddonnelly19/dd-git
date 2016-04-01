import applications
import logger
import ip_addr
import modeling

from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles.appsignature import ApplicationSignatureException


def createASMApplicationSignature(framework, framework_delegator, client, shell=None, connectionIp=None):
    '''
    Create Application Signature engine instance
    '''
    applicationSignature = ASMApplicationSignature(framework, framework_delegator, client, shell)

    initialSelectionRule = applications._createInitialSelectionRule(framework)
    applicationSignature.setInitialSelectionRule(initialSelectionRule)

    if connectionIp:
        applicationSignature.setConnectionIp(connectionIp)

    return applicationSignature


class ASMApplicationSignature(applications.ApplicationSignature):
    def __init__(self, framework, framework_delegator, client, shell=None):
        applications.ApplicationSignature.__init__(self, framework, client, shell)
        self.framework_delegator = framework_delegator
        self.crgMap = {}

    def getApplicationsTopologyUsingHostOsh(self, requestedHostOsh):
        applicationsToReport = []

        logger.debug("Starting applications topology discovery using osh")

        applicationComponents = self._createApplicationComponentsUsingHostOsh(requestedHostOsh)
        logger.debug(" .. total number of signatures: %s" % len(applicationComponents))

        # apply initial rule
        applicationComponents = filter(self._initialSelectionRule, applicationComponents)
        logger.debug(" .. number of enabled signatures: %s" % len(applicationComponents))

        self._relateProcessesToApplicationComponents(applicationComponents)

        applicationComponents = filter(applications.WithMatchedProcessesRule(), applicationComponents)

        applicationComponents = filter(applications.WithRequiredProcessesRule(), applicationComponents)

        logger.debug(" .. number of matched signatures: %s" % len(applicationComponents))

        self._processApplicationComponents(applicationComponents, applicationsToReport)

        lastModified = self.applicationSignatureConfigFile.getLastModified()
        self.framework.saveState(str(lastModified))

        return applicationsToReport

    def _processApplicationComponents(self, applicationComponents, applicationsToReport):
        for applicationComponent in applicationComponents:
            self.framework_delegator.setCurrentApplication(applicationComponent.getName())
            resultsVector = applicationComponent.processApplicationComponent(applicationsToReport)
            if applicationComponent.crgMap:
                for key in applicationComponent.crgMap:
                    self.crgMap[key] = applicationComponent.crgMap[key]
            self.framework_delegator.sendObjects(resultsVector)

    def _createApplicationComponentsUsingHostOsh(self, requestedHostOsh):
        applicationComponents = []
        applicationDescriptors = self.applicationSignatureConfigFile.getApplications()

        for applicationDescriptor in applicationDescriptors:
            applicationComponent = ASMApplicationComponent(self, applicationDescriptor, None, requestedHostOsh)
            applicationComponents.append(applicationComponent)

        return applicationComponents


class ASMApplicationComponent(applications.ApplicationComponent):
    def __init__(self, applicationSignature, applicationDescriptor, hostId, hostOsh):
        applications.ApplicationComponent.__init__(self, applicationSignature, applicationDescriptor, hostId)
        self.hostOsh = hostOsh
        self.crgMap = {}

    def getHostOsh(self):
        return self.hostOsh

    def _createApplication(self):
        return ASMApplication(self)

    def processApplicationComponent(self, applicationsToReport):

        logger.debug("Processing application component '%s'" % self.getName())

        self.createApplications()

        resultsVector = ObjectStateHolderVector()

        for application in self.applications:

            applicationResultsVector = ObjectStateHolderVector()
            try:

                application.process()

                self.processPluginsChain(application, applicationResultsVector)

                applicationsToReport.append(application)
                application.addResultsToVector(applicationResultsVector)

            except applications.PluginUncheckedException, ex:
                if ex.__class__ == applications.IgnoreApplicationException or ex.__class__.__name__ == "IgnoreApplicationException":
                    logger.warn("Instance of application '%s' is ignored, reason: %s" % (self.applicationName, str(ex)))
                else:
                    raise ex.__class__(ex)
            except ApplicationSignatureException, ex:
                logger.debugException("Exception while processing application '%s', application skipped" % self.applicationName)
            except ValueError, ex:
                logger.debugException("Exception while processing application '%s', application skipped" % self.applicationName)
            else:
                resultsVector.addAll(applicationResultsVector)

        return resultsVector


class ASMApplication(applications.Application):
    def __init__(self, applicationComponent):
        applications.Application.__init__(self, applicationComponent)

    def _createHostOsh(self):
        ''' method creates containing host OSH depending on settings in XML and discovered data '''

        appComponent = self.getApplicationComponent()

        if appComponent.isClustered():
            # clustered applications should use weak hosts by IP
            hostIp = self._applicationIp

            if hostIp and ip_addr.IPAddress(hostIp).get_is_private():
                hostIp = self.getConnectionIp()

            if not hostIp:
                raise applications.ApplicationSignatureException("Cannot report application since no valid host IP is found")

            logger.debug(" -- clustered application uses host by IP '%s'" % hostIp)

            self.hostOsh = modeling.createHostOSH(hostIp)
        else:
            # non-clustered applications use host by hostId

            self.hostOsh = self.getApplicationComponent().getHostOsh()
            logger.debug(self.hostOsh)

            if self.hostOsh:
                logger.debug(" -- application uses host by Host OSH")
            else:
                logger.debug(" -- application uses host by CMDB ID")
                hostId = self.getApplicationComponent().getHostId()
                if hostId:
                    self.hostOsh = modeling.createOshByCmdbIdString('host', hostId)


    def getProductName(self):
        return self.applicationOsh.getAttributeValue('product_name') or self.applicationOsh.getAttributeValue('discovered_product_name')

    def getDiscoveredProductName(self):
        return self.applicationOsh.getAttributeValue('discovered_product_name') or self.applicationOsh.getAttributeValue('product_name')

