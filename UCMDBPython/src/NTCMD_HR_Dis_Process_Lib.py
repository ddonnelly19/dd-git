#coding=utf-8
# Jython Imports
import re
import errorcodes
import errorobject
import logger
import modeling
import processdbutils
import wmiutils

# MAM Imports
from com.hp.ucmdb.discovery.library.common import CollectorsParameters


#################################
### Discover Processes
#################################
def discoverProcesses(client, OSHVResult, hostID, Framework, pid2Process = None):
    cmdProcessInfo = 'processlist'
    ntcmdErrStr = 'Remote command returned 1(0x1)'

    localFile = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + CollectorsParameters.FILE_SEPARATOR + 'processlist.exe'
    remoteFile = client.copyFileIfNeeded(localFile)
    if not remoteFile:
        logger.warn('Failed copying %s' % cmdProcessInfo)
        return 0

    buffer = client.execCmd(remoteFile)#V@@CMD_PERMISION ntcmd protocol execution
    logger.debug('Output of ', remoteFile, ': ', buffer)
    if buffer.find(ntcmdErrStr) != -1:
        logger.warn('Failed getting process info')
    else:
        logger.debug('Got process info - parsing...')

        processes = buffer.split('\n')
        processList = []
        pdu = None
        try:
            pdu = processdbutils.ProcessDbUtils(Framework)

            hostOSH = None
            count = 0
            for process in processes:
                process = process.strip()
                name = ''
                nameLower = ''
                pid = '-1'
                try:
                    # Get process name
                    matchName = re.search('\d*\s(.+)', process)
                    if matchName:
                        name = matchName.group(1)
                        name = name.strip()
                        nameLower = name.lower()
                        if name == '[System Process]':
                            continue

                    # Get free space
                    matchPid = re.search('(\d+)\s.*', process)
                    if matchPid:
                        pid = matchPid.group(1)

                    if(pid != '-1' and pid.isnumeric()):
                        pdu.addProcess(hostID, name, pid)
                        if ((pid in processList) != 0):
                            logger.debug('process: ',name,' already reported..')
                            continue
                        count = count + 1
                        processList.append(pid)
                        if OSHVResult is not None:
                            if hostOSH == None:
                                hostOSH = modeling.createOshByCmdbIdString('host', hostID)
                            processOsh = modeling.createProcessOSH(name, hostOSH, None, pid)
                            OSHVResult.add(processOsh)
                    else:
                        logger.debug('process: ',name,' is system process or has non numeric pid')

                except:
                    logger.errorException('Error in discoverProcesses()')

            pdu.flushHostProcesses(hostID)
            if pid2Process is not None:
                pid2Process.putAll(pdu.getProcessCmdMap())
        finally:
            if pdu != None:
                pdu.close()
        logger.debug("Discovered ", str(count), " processes")
    return 1


def discoverProcessesByWmic(client, OSHVResult, hostID, Framework, pid2Process = None):
    ''' Discover system processes, report them and save in probe DB.
    Shell, oshVector, str, Framework, map[str, str] -> bool
    @command: wmic process get commandLine, creationdate, executablepath, name, processId
    '''
    wmiProvider = wmiutils.getWmiProvider(client)
    queryBuilder = wmiProvider.getBuilder('Win32_Process')
    queryBuilder.usePathCommand(1)
    #queryBuilder = wmiutils.WmicQueryBuilder('process')
    queryBuilder.addWmiObjectProperties('name', 'processId', 'commandLine', 'executablepath', 'creationdate')
    wmicAgent = wmiProvider.getAgent()

    processItems = []
    try:
        processItems = wmicAgent.getWmiData(queryBuilder)
    except:
        logger.debugException('Failed getting processes information via wmic' )
        return 0

    pdu = None
    try:
        pdu = processdbutils.ProcessDbUtils(Framework)
        processList = []
        hostOSH = None
        count = 0

        for processItem in processItems:
            if not processItem.name:
                continue            
            processName = processItem.name
            processNameLower = processName.lower()

            processPid = processItem.processId
            if processPid == '-1' or not processPid.isnumeric():
                logger.debug("Process '%s' is system process or has non numeric pid" % processName)
                continue

            processExecutablePath = processItem.executablepath
            processCommandLine = processItem.commandLine

            processStartupTimeString = processItem.creationdate
            processStartupTime = None
            if processStartupTimeString:
                try:
                    startupDate = modeling.getDateFromUtcString(processStartupTimeString)
                    processStartupTime = startupDate.getTime()
                except:
                    errobj = errorobject.createError(errorcodes.PROCESS_STARTUP_TIME_ATTR_NOT_SET, ['NTCMD', processStartupTimeString], "%s: Process startup time attribute is not set due to error while parsing date string '%s'" % ('NTCMD', processStartupTimeString))
                    logger.reportWarningObject(errobj)

            # check whether process name is included in command line
            # Obtain first token containing process from the CMD line
            matchObj = re.match('(:?["\'](.*?)["\']|(.*?)\s)', processCommandLine)
            if matchObj and matchObj.groups():
                firstCmdToken = matchObj.group(1).strip()
            else:
                firstCmdToken = processCommandLine.strip()
            #remove quotes
            firstCmdToken = re.sub('[\'"]', '', firstCmdToken).lower()
            #token has to end with process name
            if not firstCmdToken.endswith(processNameLower):
                extStartPos = processNameLower.rfind('.')
                if extStartPos != -1:
                    pnameNoExt = processNameLower[0:extStartPos]
                    if not firstCmdToken.endswith(pnameNoExt):
                        processCommandLine = '%s %s' % (processName, processCommandLine)

            processArgs = None
            argsMatch = re.match('("[^"]+"|[^"]\S+)\s+(.+)$',processCommandLine)
            if argsMatch:
                processArgs = argsMatch.group(2)

            pdu.addProcess(hostID, processName, processPid, processCommandLine, processExecutablePath, processArgs, None, processStartupTime)

            if processPid in processList:
                logger.debug("Process: '%s' already reported" % processName)
                continue

            count += 1
            processList.append(processPid)

            if OSHVResult is not None:
                if hostOSH == None:
                    hostOSH = modeling.createOshByCmdbIdString('host', hostID)
                processOsh = modeling.createProcessOSH(processName, hostOSH, processCommandLine, processPid, processExecutablePath, None, None, processStartupTime)
                OSHVResult.add(processOsh)

        pdu.flushHostProcesses(hostID)
        if pid2Process is not None:
            pid2Process.putAll(pdu.getProcessCmdMap())

    finally:
        if pdu != None:
            pdu.close()
    return 1
