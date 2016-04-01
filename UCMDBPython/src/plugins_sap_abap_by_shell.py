# coding=utf-8
import sys
import logger
import netutils
import sap_discoverer_by_shell

from plugins import Plugin


class SapAbapPlugin(Plugin):
    """
        Plugin Sets SAP ABAP Application Server Name by shell.
    """

    def __init__(self):
        Plugin.__init__(self)
        self.__client = None
        self.__process = None
        self.shell = None
        self.__isWinOs = None


    def isApplicable(self, context):
        self.__client = context.client
        try:
            self.__process = context.application.getProcesses()[0]
            if self.__process:
                return 1
        except:
            logger.errorException(sys.exc_info()[1])

    def process(self, context):
        self.shell = context.client
        applicationOsh = context.application.getOsh()
        applicationServerName = str(applicationOsh.getAttributeValue('name'))
        applicationServerIp = str(applicationOsh.getAttributeValue('application_ip'))
        applicationProfile = str(applicationOsh.getAttributeValue('sap_instance_profile'))
        logger.info('SAP ABAP Application Server Name: ', applicationServerName)
        logger.info('SAP ABAP Application Server application_ip: ', applicationServerIp)
        logger.info('SAP ABAP Application Server Profile: ', applicationProfile)

        # SAP ABAP Application Server CIT should be created with Name attribute in format
        # - ${HOSTNAME}_${SAPSYSTEMNAME}_${INSTANCE_NUMBER}

        # get the hostname from file
        hostnameF = None
        # get the hostname from command
        hostnameC = None
        # get the hostname from ip address
        hostname = None

        underLines = applicationServerName.count('_')
        serverName = applicationServerName.split('_', underLines - 1)

        fileContent = sap_discoverer_by_shell.read_pf(self.shell, applicationProfile)
        if fileContent and fileContent[1]:
            hostnameF = fileContent[1].get('SAPLOCALHOST') or fileContent[1].get(u'SAPLOCALHOST')
        if hostnameF:
            logger.info('SAP ABAP Application Server hostname, fetch from profile: ', hostnameF)
            applicationServerName = str(hostnameF).lower() + '_' + serverName[-1]
            applicationOsh.setStringAttribute('name', applicationServerName)
            return
        
        # if there is no SAPLOCALHOST from profile, try to get the hostname from command
        try:
            hostnameC = str(self.shell.execCmd('hostname'))
            if hostnameC:
                applicationServerName = hostnameC.lower() + '_' + serverName[-1]
                applicationOsh.setStringAttribute('name', applicationServerName)
                logger.info('SAP ABAP Application Server hostname, get from command: ', hostnameC)
                return
        except:
            logger.debug('cannot get hostname by command')

        # if cannot get the hostname by command, try to resolve it by IP address
        if applicationServerIp:
            hostname = netutils.getHostName(applicationServerIp)

        if hostname:
            applicationServerName = hostname.lower() + '_' + serverName[-1]
            logger.info('SAP ABAP Application Server hostname, resolved by ip: ', hostname)
            applicationOsh.setStringAttribute('name', applicationServerName)
        else:
            logger.debug('there is no valid ip address or hostname')

