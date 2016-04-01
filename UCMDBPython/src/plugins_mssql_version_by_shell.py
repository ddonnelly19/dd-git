#coding=utf-8
import logger


from plugins import Plugin
import file_ver_lib
import regutils
from regutils import RegutilsException


class MssqlVersionByNtcmdPlugin(Plugin):
    """
    Plugin discovers MSSQL version by querying specific
    executables for their file version.
    """
  
    #name of processes we should not ask version for since it is not relevant or version requries special handling
    PROCESS_IGNORE_LIST = ["msftesql.exe"]
  
    def __init__(self):
        Plugin.__init__(self)
        
    def isApplicable(self, context):
        if context.client.isWinOs():
            processes = context.application.getProcesses()
            if processes and len(processes) > 0:
                return 1
            else:
                logger.debug("MSSQL version plug-in is not applicable since no required processes are found")
        else:
            logger.debug("Target OS is not Windows")
    
    def process(self, context):
        version = self.getVersion(context)
        if version:
            logger.debug("MSSQL version found: %s" % version)
            edition = __discoverMsSqlEdition(context.client)

            applicationOsh = context.application.getOsh()
            applicationOsh.setAttribute("application_version_number", version)

            if edition:
                logger.debug("MSSQL edition found: %s" % version)
                applicationOsh.setAttribute("description", edition)
            
        
    def getVersion(self, context):
        processes = context.application.getProcesses()
        for process in processes:
            version = self.getVersionForProcess(context, process)
            if version:
                resolvedVersion = file_ver_lib.resolveMSSQLVersion(version)
                if resolvedVersion:
                    return resolvedVersion
                else:
                    logger.debug("Cannot resolve version from string '%s', ignoring" % version)

    def getVersionForProcess(self, context, process):
        path = process.executablePath
        processName = process.getName().lower()
        if path:
            if not processName in MssqlVersionByNtcmdPlugin.PROCESS_IGNORE_LIST:
                version = self.getVersionByPathUsingWmic(context, path)
                if version:
                    return version
                else:
                    return self.getVersionByPathUsingVbScript(context, path)
        else:
            logger.debug("Cannot discover version for process '%s' due to missing path data" % processName)
            
    def getVersionByPathUsingWmic(self, context, path):
        try:
            return file_ver_lib.getWindowsWMICFileVer(context.client, path)
        except:
            logger.debugException("Exception when getting version by path '%s'\n" % path)
                 
    
    def getVersionByPathUsingVbScript(self, context, path):
        try:
            return file_ver_lib.getWindowsShellFileVer(context.client, path)
        except:
            logger.debugException("Exception when getting version by path '%s'\n" % path)


# unprefix and move to another module when you need to reuse it
def __discoverMsSqlEdition(client):
    edition = None
    instances = __getSqlInstanceNames(client)
    if instances:
        for instanceId in instances.values():
            edition = __getEdition(client, instanceId)
            if edition:
                return edition
    else:
        logger.debug("No sql instances found. Can't discover edition")
    return edition


_REG_ROOT = '''HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Microsoft SQL Server'''


def __getSqlInstanceNames(client):
    '''@types Client -> dict[instancename, instanceid]'''
    INSTANCE_NAMES_RFOLDER = _REG_ROOT + "\Instance Names\SQL"
    instances = {}
    try:
        instances = regutils.getRegKeys(client, INSTANCE_NAMES_RFOLDER)
    except (RegutilsException):
        logger.debugException('')
    return instances


def __getEdition(client, instanceId):
    EDITION_RFOLDER = "%s\%s\Setup" % (_REG_ROOT, instanceId)
    EDITION_RKEY = "Edition"
    try:
        return regutils.getRegKey(client, EDITION_RFOLDER, EDITION_RKEY)
    except (RegutilsException):
        logger.debugException('')
        return None
