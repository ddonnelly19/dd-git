#coding=utf-8
import time
import re 
import os
import logger
import sys
import modeling
import iniparser 
import shellutils
import getopt
import netutils
import errormessages
import file_mon_utils
import mysql_version_by_shell

from appilog.common.system.types import ObjectStateHolder

class MySqlDiscoverer:

    DEFAULTS_FILE_OPT_NAME = 'defaults-file'
    DATADIR_SHORT_OPT = 'h'
    DEFAULT_SECTION = 'mysqld'
    SECTION_OPT_NAME = 'section'
    LONG_OPT_PREFIX = '--'
    SHORT_OPT_PREFIX = '-' 

    def __init__(self, Framework, processPath, processParams, shell = None):
        """
        @param list opts list of command line arguments
        @param self.Framework self.Framework self.Framework instance
        """
        self.Framework = Framework 
        self.processPath = processPath
        self.configPath = None
        self.configVars = None
        self.cnfContent = None
        self.shell = shell 
        if not shell:
            self.shell = self.createShell()
        self.opts = self.parseOpts(processParams)
    
    def createShell(self):
        """
        @return ShellUtils shell utils
        """        
        client = self.Framework.createClient()
        return shellutils.ShellUtils(client)

    def createDbOsh(self, dbsid, dbport, ipaddress): 
        hostOsh = modeling.createHostOSH(ipaddress)
        mysqlOsh = modeling.createDatabaseOSH('mysql', dbsid, dbport, ipaddress, hostOsh)
        if not mysqlOsh.getAttribute('application_version'): 
            mysql_version_by_shell.setVersion(mysqlOsh, self.processPath, self.shell)
        return mysqlOsh, hostOsh 

    def readConfigVars(self):
        """
        Returns content of my.cnf
        @return ConfigParser config parser instance
        """                         
        if self.configVars:
            return self.configVars
        cnfContent = self.getConfigContent()
        if cnfContent: 
            self.configVars = iniparser.getInivars(cnfContent)
            return self.configVars 

    def getConfigContent(self):
        """
        Reads content of my.cnf file
        @return string[] list of strings
        """
        time.asctime()
        if self.cnfContent:
            return self.cnfContent 
        cnfPath = self.findConfigPath()
        if cnfPath:
            content = None
            try:                              
                content = self.shell.safecat(cnfPath)
            except Exception, ex:
                logger.warn(str(ex))
           
            if not content:
                try:
                    content = self.shell.safecat(os.path.dirname(self.processPath) + cnfPath)
                except Exception, ex:
                    logger.warn(str(ex))

            if not content:
                try:
                    content = self.shell.safecat(os.path.dirname(self.processPath) + cnfPath)
                except Exception, ex:
                    logger.warn(str(ex))

            if content:
                myCnfContent = content.split('\n')
                self.cnfContent = []
                for line in myCnfContent:
                    if not line.startswith('main-password'):
                        self.cnfContent.append(line)                      
                size = len(content) - len(myCnfContent) + 1
                if self.shell.isWinOs():
                    size = self.getWinFileSize(cnfPath, size);                    
                return self.cnfContent, size
            else:
                raise ValueError, "Failed getting contents of configuration file"
        
    def getWinFileSize(self, cnfPath, size = 0):
        dirOutput = self.shell.execCmd("dir /-C " + cnfPath)
        if self.shell.getLastCmdReturnCode() == 0:
            for outputLine in dirOutput.split('\n'):
                if len(outputLine.split()) > 1 and outputLine.split()[1] == 'File(s)':
                    return outputLine.split()[2]
        return size

    HELP_OPTIONS_LIST = ('--help --verbose', '--help -v')    
    def getConfigsFromHelp(self, fileMonitor):
        mysqlCommandList = []
        for cmd in self.HELP_OPTIONS_LIST:
            if self.shell.isWinOs():
                mysqlCommand = '"%s" %s' % (self.processPath, cmd)
            else:
                mysqlCommand = '%s %s' % (self.processPath, cmd)
            mysqlCommandList.append(mysqlCommand)
        try:
            help = self.shell.execAlternateCmdsList(mysqlCommandList)
            if self.shell.getLastCmdReturnCode() != 0:
                logger.error('Failed to get MySql help info.')            
        except:
            logger.error('Failed to get MySql help info. %s' % sys.exc_info()[1])
        else: 
            pathsFound = re.search('Default options.*order:.*\n(.*\n)', help)
            if pathsFound:
                filesLine = pathsFound.group(1)
                logger.debug('verifying existence of %s' % filesLine)
                #suppose that file have to be ended by .ext
                lookupConfPaths = re.findall('((([a-zA-Z]:)|(~?\/)).*?[\\\/]?\.?\w+\.\w+)(\s|$)', filesLine)
                if lookupConfPaths:
                    for lookupConfPath in lookupConfPaths:
                        if fileMonitor.checkPath(lookupConfPath[0]):
                            self.configPath = lookupConfPath[0]
                            return self.configPath
        if not self.configPath:
            logger.warn('MySQL configuration file was not found in mysql help')
        return self.configPath

    def findConfigPath(self):
        """
        Returns path to mysql configuration file
        @return string my.cnf path
        """
        if self.configPath:
            return self.configPath
        #try to take from options
        fileMonitor = file_mon_utils.FileMonitor(self.Framework, self.shell, None, '', None)
        if self.DEFAULTS_FILE_OPT_NAME in self.opts.keys():
            self.configPath = self.opts[self.DEFAULTS_FILE_OPT_NAME]
            cnfPath = self.opts[self.DEFAULTS_FILE_OPT_NAME]
            if fileMonitor.checkPath(cnfPath):
                self.configPath = cnfPath
            else:                      
                strException = 'MySQL configuration file path is not valid'
                errormessages.resolveAndReport(strException, self.Framework.getDestinationAttribute('Protocol'), self.Framework)
        #try to get from help
        elif not self.getConfigsFromHelp(fileMonitor):
            strException = 'Failed to find MySQL configuration file location'
            errormessages.resolveAndReport(strException, self.Framework.getDestinationAttribute('Protocol'), self.Framework)
        return self.configPath
    
    def getProperty(self, property):
        """
        Returns value of mysql global variable defined in command line option list or config file
        @param string property variable name
        @return string variable value
        """

        def filter_list(value):#for error happened during paring config, the result may be a list
            if value:
                if isinstance(value, list):
                    value = value[0]
            return value

        configVars = self.readConfigVars()
        if property in self.opts.keys():
            return filter_list(self.opts[property])
        if self.SECTION_OPT_NAME in self.opts.keys() and \
            configVars.has_section(self.opts[self.SECTION_OPT_NAME]) and \
            configVars.has_option(self.opts[self.SECTION_OPT_NAME], property):
                return filter_list(configVars.get(self.opts[self.SECTION_OPT_NAME], property))
        elif configVars.has_section(self.DEFAULT_SECTION) and \
            configVars.has_option(self.DEFAULT_SECTION, property):
                return filter_list(configVars.get(self.DEFAULT_SECTION, property))
    
    INT_ARGS = ['server_id', 'database_max_connections', 'main_connect_retry']
    def setAttribute(self, osh, attribute, mapping):
        """
        Sets value of OSH related to mysql
        @param ObjectStateHolder osh mysql of replication osh
        @param string param variable name
        @param dict mapping correlation between mysql variables names and osh attributes
        @return None
        """
        propertyName = mapping[attribute]
        value = self.getProperty(propertyName)
        if value:
            if attribute in self.INT_ARGS:
                osh.setIntegerAttribute(attribute, value)
            else:
                osh.setAttribute(attribute, value)
        else:
            logger.warn('The value for attribute %s not found.' % attribute)
    
    REPL_ARGS_MAPPING = {'main_user'          : 'main-user',
                         'main_connect_retry' : 'main-connect-retry'}
    def discoverReplication(self, mysqlOsh):
        """
        Tries to find config variables related to mysql replication 
        @param ObjectStateHolder mysqlOsh mysql osh
        @return list list of OSHs
        """
        mainHostIp = self.getProperty('main-host')
        if not mainHostIp:
            return 
        if not netutils.isValidIp(mainHostIp):
            try:
                resolver = netutils.DnsResolverByShell(self.shell)
                mainHostIp = resolver.resolveIpsByHostname(mainHostIp)[0]
            except netutils.ResolveException:
                logger.warn('Failed to resolve Main Host into IP')
                return
        mainPort = self.getProperty('main-port')
        mysqlReplicationOsh = ObjectStateHolder('mysql_replication')
        mysqlReplicationOsh.setAttribute('data_name', 'MySQL Replication')
        mysqlReplicationOsh.setContainer(mysqlOsh)
        self.setAttribute(mysqlReplicationOsh, 'main_user', self.REPL_ARGS_MAPPING)
        self.setAttribute(mysqlReplicationOsh, 'main_connect_retry', self.REPL_ARGS_MAPPING)
        mainHostOsh = modeling.createHostOSH(mainHostIp)
        serviceAddressOsh = modeling.createServiceAddressOsh(mainHostOsh, mainHostIp, mainPort, modeling.SERVICEADDRESS_TYPE_TCP)
        clientServerLink = modeling.createLinkOSH('client_server', mysqlReplicationOsh, serviceAddressOsh)
        clientServerLink.setStringAttribute('clientserver_protocol', 'TCP')
        clientServerLink.setLongAttribute('clientserver_destport', int(mainPort))
#        mainMysqlOsh = modeling.createDatabaseOSH('mysql', 'MySQL. Port ' + mainPort, mainPort, mainHostIp, mainHostOsh)
#        useLink = modeling.createLinkOSH('use', mainHostOsh, serviceAddressOsh)
        return [mainHostOsh, serviceAddressOsh, clientServerLink, mysqlReplicationOsh]

    PROCESS_ARGS = [DEFAULTS_FILE_OPT_NAME + '=', 'main-host=', 'main-user=', 'server-id=', 'datadir=', 'max_connections=', 'default-storage-engine=', 'main-connect-retry=']
    def parseOpts(self, processParams):
        paramGroupsList = re.findall('\s*("[^"]+")|([^"]\S*="[^"]+")|([^"]\w*)', processParams)
        paramList = []
        for groups in paramGroupsList: 
            if groups[0]:         
                arg = re.search('"([^=]+)=(.*)', groups[0])
                if arg:
                    paramList.append('%s="%s'%(arg.group(1).strip(), arg.group(2).strip()))  
                else:
                    paramList.append(groups[0])
            elif groups[1]:           
                paramList.append(groups[1].strip())
            elif groups[2]:           
                paramList.append(groups[2].strip())
        processedParamList = []
        for param in paramList:                                                  
            if param.startswith(self.SHORT_OPT_PREFIX + self.DATADIR_SHORT_OPT):
                processedParamList.append(param)
                continue
            for arg in self.PROCESS_ARGS:
                if param.startswith(self.LONG_OPT_PREFIX + arg):
                    processedParamList.append(param)
                    break    
        mysqlOpts, args = getopt.getopt(processedParamList, self.DATADIR_SHORT_OPT + ":", self.PROCESS_ARGS)
        opts = {}
        for opt in mysqlOpts:                          
            if opt[0] == '-' + self.DATADIR_SHORT_OPT:
                opts['datadir'] = opt[1]
            else:
                if opt[0].startswith(self.LONG_OPT_PREFIX): 
                    opts[opt[0][len(self.LONG_OPT_PREFIX):]] = opt[1]
                else:
                    opts[opt[0][len(self.SHORT_OPT_PREFIX):]] = opt[1]
        if args:                                     
            opts[self.SECTION_OPT_NAME] = args[0]            
        return opts
