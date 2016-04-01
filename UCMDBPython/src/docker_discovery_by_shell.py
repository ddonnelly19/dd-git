# coding=utf-8
import re
import logger
import modeling
import shellutils
import applications
import process as process_module
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from docker_simple_json import _JSONs


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    client = Framework.createClient()
    shell = shellutils.ShellFactory().createShell(client)

    # Image Id -> Image OSH
    imageDict = dict()
    # Container Id -> Container OSH
    containerDict = dict()
    # Container Id -> linked Container Id
    containerLinks = dict()

    # Node from Trigger
    nodeId = Framework.getTriggerCIData('hostId')
    nodeOSH = modeling.createOshByCmdbIdString("node", nodeId)
    OSHVResult.add(nodeOSH)

    # Trigger CI Running Software docker daemon
    dockerId = Framework.getTriggerCIData("triggerId")
    dockerDaemonOSH = modeling.createOshByCmdbIdString("docker_daemon", dockerId)
    OSHVResult.add(dockerDaemonOSH)

    # Docker version for docker daemon
    versionOutput = shell.execCmd('docker -v')
    if shell.getLastCmdReturnCode() == 0:
        dockerDaemonOSH.setAttribute('version', versionOutput.strip())
    else:
        Framework.reportError('Failed in command: docker version.')

    #Get Filesystem
    filesystemDict = dict()
    skipDockerVolume = getFilesystem(shell, filesystemDict)

    # Docker
    dockerOSH = ObjectStateHolder('docker')
    dockerOSH.setAttribute('name', 'Docker')
    dockerOSH.setContainer(nodeOSH)
    OSHVResult.add(dockerOSH)
    dockerDaemonLink = modeling.createLinkOSH('membership', dockerOSH, dockerDaemonOSH)
    OSHVResult.add(dockerDaemonLink)
    dockerNodeLink = modeling.createLinkOSH('dependency', dockerOSH, nodeOSH)
    OSHVResult.add(dockerNodeLink)

    discoverDockerImage(shell, imageDict, nodeOSH, OSHVResult, Framework)

    discoverDockerContainer(shell, skipDockerVolume, filesystemDict, containerDict, containerLinks, imageDict, dockerDaemonOSH, nodeOSH, client, Framework, OSHVResult)

    return OSHVResult

def discoverDockerImage(shell, imageDict, nodeOSH, OSHVResult, Framework):
    # docker images
    # REPOSITORY   TAG   IMAGE_ID   CREATED   VIRTUAL_SIZE
    imagesOutput = shell.execCmd('docker images')
    imagesLines = None
    if shell.getLastCmdReturnCode() == 0:
        imagesLines = checkLastCmd(imagesOutput)
    else:
        Framework.reportError('Failed in command: docker images.')
    if imagesLines:
        count = 0
        for imageLine in imagesLines:
            count += 1
            if count == 1:
                continue
            imageLine = imageLine.strip()
            imageInfo = imageLine.split()
            logger.debug('docker image: ', imageInfo[0])
            if len(imageInfo) == 0:
                continue

            imageInspectCMD = 'docker inspect ' + imageInfo[2]
            imageInspectOutput = shell.execCmd(imageInspectCMD)
            if shell.getLastCmdReturnCode() == 0:
                processImageInfo(imageInspectOutput, imageInfo, nodeOSH, imageDict, OSHVResult)
            else:
                Framework.reportError(('Failed in command: docker inspect image <%s>.' % imageInfo[2]))

def processImageInfo(imageInspectOutput, imageInfo, nodeOSH, imageDict, OSHVResult):

    json = _JSONs()
    jsonOutput = json.loads(imageInspectOutput)
    inspectJsonObj = jsonOutput[0]

    imageName = imageInfo[0].strip()
    imageTag = imageInfo[1]
    imageIdShort = imageInfo[2]
    virtualSize = imageInfo[len(imageInfo) - 2] + imageInfo[len(imageInfo) - 1]
    imageId = inspectJsonObj['Id']

    imageOSH = ObjectStateHolder('docker_image')
    if imageName == '<none>':
        imageOSH.setAttribute('name', 'Docker Image')
    else:
        imageOSH.setAttribute('name', imageName)
    imageOSH.setAttribute('docker_image_id', imageId)
    imageOSH.setAttribute('repository', imageName)
    imageOSH.setAttribute('tag', imageTag)
    imageOSH.setAttribute('virtual_size', virtualSize)
    imageOSH.setContainer(nodeOSH)

    OSHVResult.add(imageOSH)
    imageDict[imageId] = imageOSH

def discoverDockerContainer(shell, skipDockerVolume, filesystemDict, containerDict, containerLinks, imageDict, dockerDaemonOSH, nodeOSH, client, Framework, OSHVResult):
    # containerInfo: Container_ID   Image_Name   Container_name   Container_Ports
    containersOutput = shell.execCmd('docker ps --format "{{.ID}}{SEPARATOR}{{.Image}}{SEPARATOR}{{.Names}}{SEPARATOR}{{.Ports}}"')
    containersLines = None
    formatedResult = False
    if shell.getLastCmdReturnCode() == 0:
        containersLines = checkLastCmd(containersOutput)
        formatedResult = True
    else:
        containersOutput = shell.execCmd('docker ps')
        if shell.getLastCmdReturnCode() == 0:
            containersLines = checkLastCmd(containersOutput)
        else:
            Framework.reportError('Failed in command: docker ps.')
    if containersLines:
        containerscount = 0
        for containersline in containersLines:
            containersline = containersline.strip()
            if formatedResult:
                containerInfo = containersline.split('{SEPARATOR}')
                if len(containerInfo) == 0:
                    continue
            else:
                containerscount += 1
                if containerscount == 1:
                    continue
                containerInfoFull = containersline.split()
                if len(containerInfoFull) == 0:
                    continue
                containerInfo = [containerInfoFull[0], containerInfoFull[1], containerInfoFull[-1]]

            # docker inspect container
            inspectCmd = 'docker inspect ' + containerInfo[0]
            containerInspectOutput = shell.execCmd(inspectCmd)
            if shell.getLastCmdReturnCode() == 0:
                processContainerInfo(shell, skipDockerVolume, filesystemDict, containerInspectOutput, containerInfo, imageDict, containerDict, containerLinks, dockerDaemonOSH, nodeOSH, client, Framework, OSHVResult)
            else:
                Framework.reportError(('Failed in command: docker inspect container <%s>.' % containerInfo[0]))

    # add link for linked containers
    for containerId in containerLinks.keys():
        linkedContainerId = containerLinks[containerId]
        containersLink = modeling.createLinkOSH('usage', containerDict[containerId], containerDict[linkedContainerId])
        OSHVResult.add(containersLink)

def processContainerInfo(shell, skipDockerVolume, filesystemDict, containerInspectOutput, containerInfo, imageDict, containerDict, containerLinks, dockerDaemonOSH, nodeOSH, client, Framework, OSHVResult):
    json = _JSONs()
    jsonOutput = json.loads(containerInspectOutput)
    inspectJsonObj = jsonOutput[0]
    containerPorts = None
    imageName = containerInfo[1]
    containerName = containerInfo[2]
    if len(containerInfo) == 4:
        containerPorts = containerInfo[3]
    else:
        portsArray = []
        ports = inspectJsonObj['NetworkSettings']['Ports']
        if ports:
            port_keys = ports.keys()
            port_keys.sort()
            for port in port_keys:
                if ports[port]:
                    if ports[port][0]['HostIp'] and ports[port][0]['HostPort']:
                        portsArray.append(ports[port][0]['HostIp'] + ':' + ports[port][0]['HostPort'] + ' -> ' + port)
                else:
                    portsArray.append(port)
            containerPorts = ', '.join(portsArray)

    # get container related image
    containerId = inspectJsonObj['Id']
    imageId = inspectJsonObj['Image']
    containerOSH = ObjectStateHolder('docker_container')
    containerOSH.setAttribute('name', containerName)
    containerOSH.setAttribute('docker_container_id', containerId)
    containerOSH.setAttribute('docker_image_id', imageId)
    containerOSH.setAttribute('docker_image', imageName)
    containerDict[containerId] = containerOSH

    # set container ports
    containerOSH.setAttribute('docker_container_ports', containerPorts)

    OSHVResult.add(containerOSH)
    containerOSH.setContainer(dockerDaemonOSH)
    daemonContainerLink = modeling.createLinkOSH('manage', dockerDaemonOSH, containerOSH)
    OSHVResult.add(daemonContainerLink)

    # get container links
    if inspectJsonObj['HostConfig']['Links'] is not None:
        for link in inspectJsonObj['HostConfig']['Links']:
            linkedContainer = link.split(':')[0].split('/')[1]
            containerInspectCMD = 'docker inspect -f {{.Id}} ' + linkedContainer
            linkedContainerId = shell.execCmd(containerInspectCMD)
            if shell.getLastCmdReturnCode() == 0:
                linkedContainerId = linkedContainerId.strip()
                containerLinks[containerId] = linkedContainerId
            else:
                Framework.reportError(('Failed in command: docker inspect linked container <%s>.' % linkedContainer))

    # link image and container
    logger.debug('imageOSH: ', imageDict[imageId])
    logger.debug('containerOSH: ', containerOSH)
    imageContainerLink = modeling.createLinkOSH('realization', imageDict[imageId], containerOSH)
    OSHVResult.add(imageContainerLink)

    # get running software in container
    discoverRSinDockerContainer = Framework.getParameter('discoverRunningSW')
    if discoverRSinDockerContainer == 'true':
        topCmd = 'docker top ' + containerId
        topOutput = shell.execCmd(topCmd)
        logger.debug('docker top container: ', imageName)
        processList = []

        topLines = None
        if shell.getLastCmdReturnCode() == 0:
            topLines = checkLastCmd(topOutput)
        else:
            Framework.reportWarning(('Failed in command: docker top container <%s>.' % containerId))
        if topLines:
            topcount = 0
            for topLine in topLines:
                topcount += 1
                if topcount == 1:
                    continue
                topLine = topLine.strip()

                matcher = re.match(r'\s*(\w+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(.+)\s+(.+)\s+(\d+):(\d+):(\d+)\s+(.+)', topLine)
                if matcher:
                    owner = matcher.group(1)
                    pid = matcher.group(2)
                    commandLine = matcher.group(10)
                    fullCommand = None
                    argumentsLine = None

                    if commandLine:
                        tokens = re.split(r"\s+", commandLine, 1)
                        fullCommand = tokens[0]
                        if len(tokens) > 1:
                            argumentsLine = tokens[1]

                    commandName = fullCommand
                    commandPath = None
                    matcher = re.match(r"(.*/)([^/]+)$", fullCommand)
                    if matcher:
                        commandName = matcher.group(2)
                        commandPath = fullCommand

                    process = process_module.Process(commandName, pid, commandLine)
                    logger.debug('process generated: ', process)
                    process.argumentLine = argumentsLine
                    process.owner = owner
                    process.executablePath = commandPath
                    processList.append(process)

        if len(processList) > 0:
            logger.debug('start apply to: ', containerOSH)
            appSign = applications.createApplicationSignature(Framework, client, shell)
            logger.debug('created ApplicationSignature: ', containerOSH)
            appSign.setProcessesManager(applications.ProcessesManager(processList, None))
            logger.debug('ProcessesManager: ', containerOSH)
            appSign.getApplicationsTopology(containerOSH)
            logger.debug('finish apply to: ', containerOSH)

    # get container volumes
    if not skipDockerVolume:
        if inspectJsonObj.has_key('Mounts') and inspectJsonObj['Mounts']:
            mountResults = inspectJsonObj['Mounts']
            for mountStr in mountResults:
                mount = mountStr
                dockerVolumeOSH = ObjectStateHolder('docker_volume')
                dockerVolumeOSH.setAttribute('name', 'Docker Volume')
                dockerVolumeOSH.setAttribute('dockervolume_source', mount['Source'])
                dockerVolumeOSH.setAttribute('dockervolume_destination', mount['Destination'])
                if mount['RW'] == 'true':
                    dockerVolumeOSH.setAttribute('logicalvolume_accesstype', 'RW')
                else:
                    dockerVolumeOSH.setAttribute('logicalvolume_accesstype', 'R')
                OSHVResult.add(dockerVolumeOSH)
                volumeContainerLink = modeling.createLinkOSH('usage', containerOSH, dockerVolumeOSH)
                OSHVResult.add(volumeContainerLink)
                linkDockerVolumeToLv(mount['Source'], filesystemDict, nodeOSH, dockerVolumeOSH, OSHVResult)

        elif inspectJsonObj.has_key('Volumes') and inspectJsonObj.has_key('VolumesRW') and inspectJsonObj['Volumes']:
            dockerVolumeOSH = ObjectStateHolder('docker_volume')
            dockerVolumeOSH.setAttribute('name', 'Docker Volume')
            OSHVResult.add(dockerVolumeOSH)
            volumeContainerLink = modeling.createLinkOSH('usage', containerOSH, dockerVolumeOSH)
            OSHVResult.add(volumeContainerLink)
            volumResults = inspectJsonObj['Volumes']
            for (dst, src) in volumResults.items():
                dockerVolumeOSH.setAttribute('dockervolume_source', src)
                dockerVolumeOSH.setAttribute('dockervolume_destination', dst)
                if inspectJsonObj['VolumesRW'][dst] == 'true':
                    dockerVolumeOSH.setAttribute('logicalvolume_accesstype', 'RW')
                else:
                    dockerVolumeOSH.setAttribute('logicalvolume_accesstype', 'R')
                linkDockerVolumeToLv(src, filesystemDict, nodeOSH, dockerVolumeOSH, OSHVResult)
    else:
        logger.debug('Skip Docker Volume since filesystem is not find!')

def linkDockerVolumeToLv(volumeSource, filesystemDict, nodeOSH, dockerVolumeOSH, OSHVResult):
    for mountPoint in filesystemDict.keys():
        if re.match(mountPoint, volumeSource):
            logicalVolumeOSH = ObjectStateHolder('logical_volume')
            logicalVolumeOSH.setAttribute('name', filesystemDict[mountPoint])
            logicalVolumeOSH.setContainer(nodeOSH)
            OSHVResult.add(logicalVolumeOSH)
            lvDockerVolumeLink = modeling.createLinkOSH('dependency', dockerVolumeOSH, logicalVolumeOSH)
            OSHVResult.add(lvDockerVolumeLink)
            dockerVolumeOSH.setContainer(logicalVolumeOSH)

def getFilesystem(shell, filesystemDict):
    skipDockerVolume = False
    dfOutput = shell.execCmd('df')
    dfLines = None
    if shell.getLastCmdReturnCode() == 0:
        dfLines = checkLastCmd(dfOutput)
    else:
        logger.debug('Can not get filesystem information!')
        skipDockerVolume = True
    if dfLines:
        count = 0
        for dfLine in dfLines:
            count += 1
            if count == 1:
                continue
            dfLine = dfLine.strip()
            fileSystemInfo = dfLine.split()
            logger.debug('Filesystem: ', fileSystemInfo)
            if len(fileSystemInfo) == 0:
                continue
            fileSystemName = fileSystemInfo[0]
            fileSystemMount = fileSystemInfo[-1]
            filesystemDict[fileSystemMount] = fileSystemName
    else:
        skipDockerVolume = True
    return skipDockerVolume

def checkLastCmd(lastCmdOutput):
    if lastCmdOutput.find('command not found') != -1 or len(lastCmdOutput) < 1:
        return None
    else:
        lastCmdOutputLines = lastCmdOutput.splitlines()
        return lastCmdOutputLines
