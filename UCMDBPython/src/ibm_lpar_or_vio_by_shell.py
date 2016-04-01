#coding=utf-8
import re
import logger
import modeling
import shellutils
import netutils
import errormessages
import storage_topology
import ibm_hmc_lib

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

from java.lang import Exception
from ibm_hmc_lib import createInterfaceOsh
from TTY_HR_CPU_Lib import _Cpu, VioCpuDiscoverer, AixCpuDiscoverer

def parseEthAdapterInformation(output, adaptersDict):
    if output:
        entries = re.split('ETHERNET STAT', output)
        for entrie in entries:
            ifaceName = re.search('ISTICS \(\s*(\w+)\s*\)', entrie)
            if not ifaceName:
                continue
            ifaceName = ifaceName.group(1).strip()
            
            ifaceType = re.search('Device Type:\s+([\w \-\\/]+)' , entrie)
            if not ifaceType:
                continue
            ifaceType = ifaceType.group(1).strip()
            
            ifaceMac = re.search('Hardware Address:\s+(..:..:..:..:..:..)', entrie)
            if ifaceMac:
                ifaceMac = ifaceMac.group(1).strip()

            adapter = adaptersDict.get(ifaceName)
            if adapter:
                
                ifaceSpeed = re.search('Media Speed Running:\s+(\d+)', entrie)
                if ifaceSpeed:
                    adapter.speed = int(ifaceSpeed.group(1)) * 1000

                if ifaceType.lower() == "shared ethernet adapter":
                    adapter.interfaceType = ibm_hmc_lib.SEA_ADAPTER
                    adapter.isVirtual = 1
                elif ifaceType.lower() == "etherchannel":
                    adapter.interfaceType = ibm_hmc_lib.LINK_AGGREGATION_ADAPTER
                    if ifaceMac and netutils.isValidMac(ifaceMac):
                        adapter.macAddress = netutils.parseMac(ifaceMac)
                else:
                    if re.search('virtual', ifaceType, re.I):
                        adapter.isVirtual = 1
                    if ifaceMac and netutils.isValidMac(ifaceMac):
                        adapter.macAddress = netutils.parseMac(ifaceMac)
                adaptersDict[ifaceName] = adapter

def parseEthernetAdapters(output):
    adaptersDict = {}
    if output:
        entries = ibm_hmc_lib.splitCommandOutput(output)
        for entrie in entries:
            if entrie and entrie.find(':') != -1:
                try:
                    iface = ibm_hmc_lib.LparNetworkInterface()
                    tokens = entrie.split(':')
                    iface.name = tokens[0].strip()
                    if iface.name:
                        ifaceIndex = re.match('\s*[A-Za-z]+(\d+)', iface.name)
                        if ifaceIndex:
                            iface.interfaceIndex = ibm_hmc_lib.toInteger(ifaceIndex.group(1))
                    iface.physicalPath = tokens[1].strip()
                    iface.interfaceType = ibm_hmc_lib.ETH_ADAPTER 
                    adaptersDict[iface.name] = iface
                except:
                    logger.warn('Failed parsing interface from string %s' % entrie)
    return adaptersDict

def parseEthernetAdapterSpeedAndRelation(output, adapter):
    if output:
        mediaSpeed = re.search('media_speed\s+(\w+)\s+', output)
        if mediaSpeed:
            mediaSpeed = mediaSpeed.group(1).strip()
            speed = re.match('(\d+)', mediaSpeed)
            if speed:
                adapter.speed = ibm_hmc_lib.toInteger(speed.group(1)) * 1000
        usedAdapters = re.search('adapter_names\s+([\w\,]+)\s+EtherChannel', output)
        if usedAdapters:
            adapter.usedAdapters.extend(usedAdapters.group(1).strip().split(','))
        
        #determine link aggr operation status
        if adapter.interfaceType == ibm_hmc_lib.LINK_AGGREGATION_ADAPTER:
            aggrMode = re.search('mode\s+(\w+)\s+EtherChannel\s+mode', output)
            failOverInterface = re.search('backup_adapter\s+(\w+)', output)
            if aggrMode:
                if (aggrMode.group(1) == 'netif_backup') or (failOverInterface and failOverInterface.group(1).strip() and failOverInterface.group(1).strip().upper() != 'NONE'):
                    adapter.operatingMode = ibm_hmc_lib.AGGREGATED_FAILOVER
                    adapter.backupAdapter = failOverInterface.group(1).strip()
                else:
                    adapter.operatingMode = ibm_hmc_lib.AGGREGATED_BAND

    return adapter

def validateEthAdapters(adaptersDict):
    validatedDict = {}
    if adaptersDict:
        for (ifaceName, iface) in adaptersDict.items():
            if iface.interfaceType in [ibm_hmc_lib.ETH_ADAPTER, ibm_hmc_lib.LINK_AGGREGATION_ADAPTER] and iface.macAddress:
                validatedDict[ifaceName] = iface
            elif iface.interfaceType == ibm_hmc_lib.SEA_ADAPTER:
                validatedDict[ifaceName] = iface
    return validatedDict

def parseLsMapInterfaceRelation(output, ethAdaptersDict):
    if output and ethAdaptersDict:
        for entrie in re.split("------ --------------------------------------------", output):
            matcher = re.match("\s*(\w+)\s.*SEA\s+(\w+).*Backing device\s+(\w+)", entrie, re.DOTALL)
            if matcher:
                vIfaceName = matcher.group(1).strip()
                seaName = matcher.group(2).strip()
                bkDev = matcher.group(3).strip()
                
                adapter = ethAdaptersDict.get(vIfaceName)
                adapter.usedAdapters.append(seaName)
                ethAdaptersDict[vIfaceName] = adapter
                
                adapter = ethAdaptersDict.get(seaName)
                adapter.usedAdapters.append(bkDev)
                ethAdaptersDict[seaName] = adapter

def parseEthAdapterVpdInformation(output, ethAdaptersDict):
    if output:
        match = re.match('\s*(e[nt]+\d+).*?Network Address[\s.]+(\w+).*?Displayable Message[\s.]+([\w /\-\(\)]*).*?Hardware Location Code[\s.]+([\w\-\.]*)', output, re.DOTALL)
        if match:
            ifaceName = match.group(1)
            iface = ethAdaptersDict.get(ifaceName)
            if iface:
                ifaceMac = match.group(2)
                if ifaceMac and netutils.isValidMac(ifaceMac):
                    iface.macAddress = netutils.parseMac(ifaceMac)
                
                ifaceDescription = match.group(3)
                if ifaceDescription:
                    iface.description = ifaceDescription
                    if re.search('virtual', ifaceDescription, re.I):
                        iface.isVirtual = 1
                
                physPath = match.group(4)
                if physPath:
                    iface.physicalPath = physPath
                
def parseEthernetAliases(output):
    if output:
        return re.findall('(e[nt]\d+)\s+Available', output)

def discover_cpus(shell, framework, is_vio):
    r'''
    @types: shellutils.Shell, Framework, bool -> list[TTY_HR_CPU_Lib._Cpu]
    '''
    lang_bandle = framework.getEnvironmentInformation().getBundle('langHost_Resources_By_TTY', 'eng')
    if is_vio:
        vio_cpu_discoverer = VioCpuDiscoverer(shell, lang_bandle)
        cpus = vio_cpu_discoverer.get_frame_cpus()
    else:
        aix_cpu_discoverer = AixCpuDiscoverer(shell, lang_bandle)
        cpus = aix_cpu_discoverer.get_frame_cpus()
    return cpus

def discoverEhernetAdapterAliasses(shell):
    aliasesList = []
    output = shell.execAlternateCmds('/usr/ios/cli/ioscli lsdev -dev \'en*\' | grep Available', 'ioscli lsdev -dev \'en*\' | grep Available')
    if output and shell.getLastCmdReturnCode() == 0:
        aliasesList = parseEthernetAliases(output)

    output = shell.execAlternateCmds('/usr/ios/cli/ioscli lsdev -dev \'et*\' | grep Available', 'ioscli lsdev -dev \'et*\' | grep Available')
    if output and shell.getLastCmdReturnCode() == 0:
        aliasesList.extend(parseEthernetAliases(output))

    return aliasesList

def discoverEthernetAdapters(shell):
    #Discovering adapters name and physical path
    ethAdaptersDict = {}
    output = shell.execAlternateCmds('/usr/ios/cli/ioscli lsdev -dev \'ent*\' -field name physloc -fmt :', 'ioscli lsdev -dev \'ent*\' -field name physloc -fmt :')
    if output and shell.getLastCmdReturnCode() == 0:
        ethAdaptersDict = parseEthernetAdapters(output)
        
    #discovering Network adapters MAC addresses and Types
    for ethAdapterName in ethAdaptersDict.keys():
        output = shell.execAlternateCmds('/usr/ios/cli/ioscli entstat -all ' + ethAdapterName,'ioscli entstat -all '+ ethAdapterName)
        if output and shell.getLastCmdReturnCode() == 0:
            parseEthAdapterInformation(output, ethAdaptersDict)
        else:
            output = shell.execAlternateCmds('/usr/ios/cli/ioscli lsdev -dev %s -vpd' % ethAdapterName, 'ioscli lsdev -dev %s -vpd' % ethAdapterName)
            if output and shell.getLastCmdReturnCode() == 0:
                parseEthAdapterVpdInformation(output, ethAdaptersDict)
    validateEthAdapters(ethAdaptersDict)
    
    #discover Ethernet adapter Media Speed
    for (adapterName , ethAdapter) in ethAdaptersDict.items():
        if ethAdapter.interfaceType in [ibm_hmc_lib.ETH_ADAPTER, ibm_hmc_lib.LINK_AGGREGATION_ADAPTER]:
            output = shell.execAlternateCmds('ioscli lsdev -dev ' + adapterName + ' -attr', '/usr/ios/cli/ioscli lsdev -dev ' + adapterName + ' -attr')
            if output and shell.getLastCmdReturnCode() == 0:
                ethAdaptersDict[adapterName] = parseEthernetAdapterSpeedAndRelation(output, ethAdapter)
                
    #discover adapter relations
    output = shell.execAlternateCmds('ioscli lsmap -all -net', '/usr/ios/cli/ioscli lsmap -all -net')
    if output and shell.getLastCmdReturnCode() == 0:
        parseLsMapInterfaceRelation(output, ethAdaptersDict)
    return ethAdaptersDict

def discoverAixLparEthernetAdapters(shell):
    #Discovering adapters name and physical path
    ethAdaptersDict = {}
    output = shell.execAlternateCmds('lsdev -Cc adapter -F"name:physloc" | grep ent')
    if output and shell.getLastCmdReturnCode() == 0:
        ethAdaptersDict = parseEthernetAdapters(output)
        
    #discovering Network adapters MAC addresses and Types
    for ethAdapterName in ethAdaptersDict.keys():
        output = shell.execAlternateCmds('entstat -d ' + ethAdapterName)
        if output and shell.getLastCmdReturnCode() == 0:
            parseEthAdapterInformation(output, ethAdaptersDict)
        else:
            output = shell.execAlternateCmds('lscfg -vpl %s' % ethAdapterName)
            if output and shell.getLastCmdReturnCode() == 0:
                parseEthAdapterVpdInformation(output, ethAdaptersDict)
    validateEthAdapters(ethAdaptersDict)
    
    #discover Ethernet adapter Media Speed
    for (adapterName , ethAdapter) in ethAdaptersDict.items():
        if ethAdapter.interfaceType in [ibm_hmc_lib.ETH_ADAPTER, ibm_hmc_lib.LINK_AGGREGATION_ADAPTER]:
            output = shell.execAlternateCmds('lsattr -El ' + adapterName)
            if output and shell.getLastCmdReturnCode() == 0:
                ethAdaptersDict[adapterName] = parseEthernetAdapterSpeedAndRelation(output, ethAdapter)
                
    return ethAdaptersDict

def parseFiberChannel(output):
    fcHbaList = []
    if output:
        for line in re.split("[\r\n]+", output):
            if line.strip():
                tokens = line.split(":")
                fcHba = ibm_hmc_lib.FiberChannelHba()
                fcHba.name = tokens[0]
                fcHba.physPath = tokens[1]
                fcHba.descr = tokens[2]
                fcHbaList.append(fcHba)
    return fcHbaList

def parseFiberChannedAdditionalAttributes(output, fcHba):
    if output and fcHba:
        for line in re.split('[\r\n]+', output):
            wwnBuf = re.search('\s*Network\s+Address\.+(\w+)', line)
            if wwnBuf:
                fcHba.wwn = wwnBuf.group(1).strip()
            modelBuf = re.search('\s*Model:\s*([\w\-\.]+)', line)
            if modelBuf:
                fcHba.model = modelBuf.group(1).strip()
            serialBuf = re.search('\s*Serial\s+Number\.+([\w\-\.]+)', line)
            if serialBuf:
                fcHba.serialNumber = serialBuf.group(1).strip()
            vendorBuf = re.search('\s*Manufacturer\.+([\w\-\.]+)', line)
            if vendorBuf:
                fcHba.vendor = vendorBuf.group(1).strip()
            physLocBuf = re.search('\s*Hardware Location Code\.+([\w\-\.]+)', line)
            if physLocBuf:
                physPath = physLocBuf.group(1).strip()
                ioSlotNameBuf = re.match("\s*(\w{5}\.\w{3}\.\w{7}\-\w{2}\-\w{2})", physPath)
                if ioSlotNameBuf:
                    fcHba.physPath = ioSlotNameBuf.group(1)

def getFibreChannelsOnVio(shell):
    fcHbaList = []
    output = shell.execAlternateCmds('ioscli lsdev -dev fcs* -field name physloc description -fmt :', '/usr/ios/cli/ioscli lsdev -dev fcs* -field name physloc description -fmt :')
    if shell.getLastCmdReturnCode() == 0:
        fcHbaList = parseFiberChannel(output)
    else:
        raise ValueError, "Failed to discover Fibre Channels"
    return fcHbaList

def parseFiberChannelLpar(lsdevOutput):
    fcHbaList = []
    if not lsdevOutput:
        return fcHbaList
    
    for line in lsdevOutput.split('\n'):
        line = line and line.strip()
        if line:
            match = re.match("(\w+)\s+(.*)", line)
            if match:
                fcHba = ibm_hmc_lib.FiberChannelHba()
                fcHba.name = match.group(1)
                fcHba.descr = match.group(2)
                fcHbaList.append(fcHba)
    return fcHbaList

def getFibreChannnelsOnLpar(shell):
    fcHbaList = []
    output = shell.execCmd("lsdev -l fcs* -F 'name description'")
    if shell.getLastCmdReturnCode() == 0:
        fcHbaList = parseFiberChannelLpar(output)
    else:
        raise ValueError, "Failed to discover Fibre Channels"
    return fcHbaList

def discoverFiberChannels(shell):
    try:
        fcHbaList = getFibreChannelsOnVio(shell)
    except:
        fcHbaList  = getFibreChannnelsOnLpar(shell)
        
    for fcHba in fcHbaList:
        lscfgCommand = 'lscfg -vpl %s' % fcHba.name
        lsdevCommand = 'lsdev -dev %s -vpd' % fcHba.name 
        output = shell.execAlternateCmds(lscfgCommand, '/usr/sbin/' + lscfgCommand, lsdevCommand, 'ioscli ' + lsdevCommand, '/usr/ios/cli/ioscli ' + lsdevCommand)
        if output and shell.getLastCmdReturnCode() == 0:
            parseFiberChannedAdditionalAttributes(output, fcHba)
        else:
            raise ValueError, "Command 'lscfg' failed to run. WWNN cannot be obtained."
            
    return fcHbaList

def parseScsi(output, physicalVolumeDict, logicalVolumeDict):
    scsiList = []
    if output:
        blocks = re.split("--------------- -------------------------------------------- ------------------", output)
        for block in blocks:
            match = re.match("\s*([\w\-\.]+)\s+([\w\.\-]+)\s+.*LUN\s*0[xX](\d+)", block, re.DOTALL)
            if match:
                scsi = storage_topology.ScsiAdapter()
                scsi.name = match.group(1).strip()
                scsi.physicalPath = match.group(2).strip()
                localSlotNumber = re.search("-[Cc](\d+)", scsi.physicalPath) or re.search("-[Pp](\d+)", scsi.physicalPath)
                if not localSlotNumber:
                    continue
                scsi.slotNumber = localSlotNumber.group(1).strip()
                scsi.lunId = match.group(3).strip()
                backingDevices = re.findall("Backing device\s+([\w/\.\-]+)", block)
                if not backingDevices:
                    continue
                for backingDevice in backingDevices:
                    if physicalVolumeDict.has_key(backingDevice):
                        physVol = physicalVolumeDict.get(backingDevice)
                        physVol.scsiAdapterSlotNumber = scsi.slotNumber
                        physicalVolumeDict[backingDevice] = physVol
                    elif logicalVolumeDict.has_key(backingDevice):
                        logVol = logicalVolumeDict.get(backingDevice)
                        logVol.scsiAdapterSlotNumber = scsi.slotNumber
                        logicalVolumeDict[backingDevice] = logVol
                scsi.isVirtual = 1
                scsiList.append(scsi)
    return scsiList

def discoverScsi(shell, physicalVolumeDict, logicalVolumeDict):
    output = shell.execAlternateCmds('ioscli lsmap -all', '/usr/ios/cli/ioscli lsmap -all')
    if output and shell.getLastCmdReturnCode() == 0:
        return parseScsi(output, physicalVolumeDict, logicalVolumeDict)
    
def parseHdiskToScsiCorres(output, splitPattern = "\s+"):
    hdisks = []
    devices = []
    if output:
        lines = [line.strip() for line in ibm_hmc_lib.splitCommandOutput(output) if line and re.match('\s*hdisk', line)]
        for line in lines:
            vals = re.split(splitPattern, line.strip())
            hdiskName = vals[0]
            deviceName = vals[1]
            hdisks.append(hdiskName)
            devices.append(deviceName)
    return (hdisks, devices)

def discoverLparPhysScsiAndRaid(shell, physicalVolumesDict):
    scsiList = []
    physVolumes = []
    output = ""
    for hdisk in physicalVolumesDict.keys():
        try:
            output = ibm_hmc_lib.executeCommand(shell, 'lspath -l %s -F"name:parent"' % hdisk)
        except ValueError, ex:
            logger.warn(str(ex))
            continue
        (hdisks, devices) = parseHdiskToScsiCorres(output, "\:+")
        for i in range(len(devices)):
            deviceName = devices[i]
            physicalVolume = physicalVolumesDict.get(hdisks[i])
            if physicalVolume:
                command = "lscfg | grep %s" % deviceName
                try:
                    output = shell.execAlternateCmds(command, "ioscli " + command, "/usr/ios/cli/ioscli " + command) 
                    if output:
                        physicalPath = re.match('\+\s+scsi1\s+([\w\.\-]+)\s+', output.strip())
                        if physicalPath:
                            localSlotNumber = re.match(".*-[Cc](\d+)", physicalPath.group(1).strip()) or re.match(".*-[Pp](\d+)", physicalPath.group(1).strip())
                            if localSlotNumber:
                                scsi = storage_topology.ScsiAdapter()
                                scsi.physicalPath = physicalPath.group(1).strip()
                                scsi.slotNumber = localSlotNumber.group(1).strip()
                                physicalVolume.scsiAdapterSlotNumber = scsi.slotNumber
                                physVolumes.append(physicalVolume)
                                scsiList.append(scsi)
                except:
                    logger.warnException("Failed to discover physical SCSI and RAID.")
    return (scsiList, physVolumes)

def discoverPhysScsiAndRaid(shell, physicalVolumesDict):
    scsiList = []
    physVolumes = []
    output = ""
    try:
        output = ibm_hmc_lib.executeCommand(shell, "lspath -field name parent")
        if output and re.search(r"\s+isk\d+\s+sc\s+si\d+", output, re.DOTALL):
            output = output.replace('isk', 'hdisk').replace('sc si', 'scsi')
    except ValueError, ex:
        logger.reportWarning('Failed to run lspath.')
        logger.warn(str(ex))
    (hdisks, devices) = parseHdiskToScsiCorres(output)
    for i in range(len(devices)):
        deviceName = devices[i]
        physicalVolume = physicalVolumesDict.get(hdisks[i])
        if physicalVolume:
            command = "lsdev -dev %s -field physloc -fmt :" % deviceName
            try:
                output = shell.execAlternateCmds(command, "ioscli " + command, "/usr/ios/cli/ioscli " + command) 
                if output:
                    localSlotNumber = re.match(".*-[Cc](\d+)", output.strip()) or re.match(".*-[Cc](\d+)", output.strip())
                    if localSlotNumber:
                        scsi = storage_topology.ScsiAdapter()
                        scsi.physicalPath = output.strip()
                        scsi.slotNumber = localSlotNumber.group(1).strip()
                        physicalVolume.scsiAdapterSlotNumber = scsi.slotNumber
                        physVolumes.append(physicalVolume)
                        scsiList.append(scsi)
            except:
                logger.warnException("Failed to discover physical SCSI and RAID.")
    return (scsiList, physVolumes)
    
def parseLinuxVScsiAdapters(output):
    scsiList = []
    if output:
        lines = ibm_hmc_lib.splitCommandOutput(output)
        for line in lines:
            scsi = storage_topology.ScsiAdapter()
            match = re.match("\s*([v\-]*scsi\d+)\s+(.*)", line)
            if match:
                scsi.name = match.group(1).strip()
                scsi.physicalPath = match.group(2).strip()
                slotNumber = re.match(".*\-C(\d+)", scsi.physicalPath)
                if not slotNumber:
                    continue
                scsi.slotNumber = slotNumber.group(1).strip()
                scsi.slotNumber
                scsi.isVirtual = 1
                scsiList.append(scsi)
    return scsiList

def discoverLinuxVScsiAdapters(shell):
    try:
        output = shell.execAlternateCmds('/usr/sbin/vpdupdate','/sbin/vpdupdate', 'vpdupdate')
    except:
        logger.reportWarning('Failed running vpdupdate.')
        return []
    if shell.getLastCmdReturnCode() != 0:
        logger.reportWarning('Failed running vpdupdate.')
        return []
    output = shell.execAlternateCmds('/usr/sbin/lsvio -s','/sbin/lsvio -s', 'lsvio -s')
    if output and shell.getLastCmdReturnCode() == 0:
        return parseLinuxVScsiAdapters(output)
    
def parseLinuxStorageInfo(output):
    vgDict = {}
    pvDict = {}
    lvDict = {}
    if output:
        blocks = re.split("--- Volume group ---", output)
        if blocks:
            for block in blocks:
                vg = storage_topology.VolumeGroup()
                vgName = re.search('VG Name\s+([\w\-]+)', block)
                if not vgName:
                    continue
                    vg.vgName = vgName.group(1).strip()
                vgId = re.search('VG UUID\s+([\w\-]+)', block)
                if vgId:
                    vg.vgId = vgId.group(1).strip()
                vgDict[vg.vgName] = vg

                lvNames = re.findall("LV Name\s+([\w\-]+)", block)
                if lvNames:
                    for lvName in lvNames:
                        lv = storage_topology.LogicalVolume()
                        lv.lvName = lvName
                        lv.volumeGroupName = vg.vgName 
                        lvDict[lv.lvName] = lv
                pvNames = re.findall("PV Name\s+([\w/\-]+)", block)
                if pvNames:
                    for pvName in pvNames:
                        pv = storage_topology.PhysicalVolume()
                        pv.pvName = pvName
                        pv.volumeGroupName = vg.vgName
                        pvDict[pv.pvName] = pv
                    
    return (vgDict, lvDict, pvDict)
                

def discoverLinuxStorageInfo(shell):
    try:
        output = shell.execAlternateCmds('/usr/sbin/vgdisplay -v', 'vgdisplay -v')
    except:
        logger.reportWarning('Failed to discover storage info.')
        return ({}, {}, {})
    if output and shell.getLastCmdReturnCode() == 0:
        return parseLinuxStorageInfo(output)
    return ({}, {}, {})
    
def parseLogicalVolumes(output, vgName):
    lvDict = {}
    if output:
        lines = ibm_hmc_lib.splitCommandOutput(output)
        if len(lines) > 2:
            lines = lines[2:]
        for line in lines:
            tokens = re.split("\s+", line.strip())
            if tokens and len(tokens) >= 7:
                lv = storage_topology.LogicalVolume()
                lv.lvName = tokens[0]
                lv.lvFsType = tokens[1]
                lv.lvState = tokens[5]
                if tokens[6].upper() != "N/A":
                    lv.mountPoint = tokens[6]
                lv.volumeGroupName = vgName
                lvDict[lv.lvName] = lv
    return lvDict

def discoverLogicalVolumes(shell, vgDict):
    lvDict = {}
    if vgDict:
        for vg in vgDict.values():
            try:
                output = shell.execAlternateCmds("lsvg -lv %s" % vg.vgName, "lsvg -l %s" % vg.vgName)
                if output and shell.getLastCmdReturnCode() == 0:
                    lvDict.update(parseLogicalVolumes(output, vg.vgName))
            except ValueError, ex:
                logger.warn(str(ex))
    return lvDict

def parseVolumeGroupNames(output):
    vgDict = {}
    if output:
        vgNames = re.split("\s+", output)
        for vgName in vgNames:
            if vgName:
                vg = storage_topology.VolumeGroup()
                vg.vgName = vgName
                vgDict[vgName] = vg
    return vgDict

def parseVolumeGroupParameters(output):
    if output:
        vgId = re.search("VG\s+IDENTIFIER:\s+([\w\.]+)", output)
        if vgId:
            return vgId.group(1).strip()
             

def discoverVolumeGroups(shell):
    try:
        output = ibm_hmc_lib.executeCommand(shell, 'lsvg')
    except ValueError, ex:
        logger.reportWarning('Failed to discover Logical Volumes')
        logger.warn(str(ex))
        return {}
    vgDict = parseVolumeGroupNames(output)
    if vgDict:
        for vg in vgDict.values():
            try:
                output = ibm_hmc_lib.executeCommand(shell, 'lsvg %s' % vg.vgName)
                vg.vgId = parseVolumeGroupParameters(output)
                vgDict[vg.vgName] = vg
            except ValueError, ex:
                logger.warn(str(ex))
    return vgDict

def parsePhysicalVolume(output):
    pvDoDict = {}
    if output:
        lines = ibm_hmc_lib.splitCommandOutput(output)
        if lines:
            if re.match("\s*NAME\s+PVID", output):
                lines = lines[1:]
            for line in lines:
                tokens = re.split("\s+", line)
                if len(tokens) >= 3:
                    pv = storage_topology.PhysicalVolume()
                    pv.pvName = tokens[0]
                    if tokens[1] and tokens[1].lower() != 'none':
                        pv.pvId = tokens[1]
                    if tokens[2] and tokens[2].lower() != 'none':
                        pv.volumeGroupName = tokens[2]
                    pvDoDict[pv.pvName] = pv
    return pvDoDict
    
def parsePhysicalVolumeParams(output, physVolume):
    if output:
        size = re.search("TOTAL\s+PPs\:\s+\d+\s*\(\s*(\d+)", output)
        if size:
            physVolume.pvSize = ibm_hmc_lib.toFloat(size.group(1).strip())
            logger.debug('Physical Volume Size ' + str( physVolume.pvSize))
    
def discoverPhysicalVolumes(shell):
    physVolumeDict = {}
    output = ''
    try:
        output = ibm_hmc_lib.executeCommand(shell, 'lspv')
    except ValueError, ex:
        logger.reportWarning('Failed to discover Physical Volumes')
        logger.warn(str(ex))
    physVolumeDict = parsePhysicalVolume(output)
    for key in physVolumeDict.keys(): 
        try:
            output = ibm_hmc_lib.executeCommand(shell, 'lspv %s' % key)
        except ValueError, ex:
            logger.warn(str(ex))
        parsePhysicalVolumeParams(output, physVolumeDict[key])
    return physVolumeDict 
    
    
def createFiberChannelOsh(fiberChannelAdapter, parentOsh):
    if fiberChannelAdapter and parentOsh:
        fiberChannelOsh = ObjectStateHolder('fchba')
        fiberChannelOsh.setContainer(parentOsh)
        fiberChannelOsh.setStringAttribute('data_name', fiberChannelAdapter.name)
        if fiberChannelAdapter.descr:
            if len(fiberChannelAdapter.descr) > 600:
                fiberChannelAdapter.descr = fiberChannelAdapter.descr[:600]
            fiberChannelOsh.setStringAttribute('data_description', fiberChannelAdapter.descr)
        if fiberChannelAdapter.wwn is not None:
            fiberChannelOsh.setStringAttribute('fchba_wwn', fiberChannelAdapter.wwn)
        if fiberChannelAdapter.model is not None:
            fiberChannelOsh.setStringAttribute('fchba_model', fiberChannelAdapter.model)
        if fiberChannelAdapter.serialNumber is not None:
            fiberChannelOsh.setStringAttribute('fchba_serialnumber' , fiberChannelAdapter.serialNumber)
        if fiberChannelAdapter.vendor is not None:
            fiberChannelOsh.setStringAttribute('fchba_vendor' , fiberChannelAdapter.vendor)
        return fiberChannelOsh
    
def createInterfaceIndexOsh(networkInterface, hostOsh):
    if hostOsh and networkInterface and networkInterface.interfaceIndex and networkInterface.speed:
        ifaceIndexOsh = ObjectStateHolder('interfaceindex')
        ifaceIndexOsh.setContainer(hostOsh)
        ifaceIndexOsh.setIntegerAttribute('interfaceindex_index', networkInterface.interfaceIndex)
        ifaceIndexOsh.setDoubleAttribute('interfaceindex_speed', networkInterface.speed)
        return ifaceIndexOsh

def createSeaOsh(seaAdapter, hostOsh):
    if seaAdapter and hostOsh:
        seaOsh = ObjectStateHolder('sea_adapter')
        seaOsh.setContainer(hostOsh)
        seaOsh.setStringAttribute('data_name', seaAdapter.name)
        if seaAdapter.speed:
            seaOsh.setLongAttribute('speed', seaAdapter.speed)
        return seaOsh

def createLinkAggrOsh(linkAggregation, hostOsh):
    if linkAggregation and hostOsh:
        linkAggregation.className = 'interface_aggregation'
        return createInterfaceOsh(linkAggregation, hostOsh)

def createAliasOsh(aliasName, hostOsh, physAdapt):
    if aliasName and hostOsh and physAdapt:
        aliasOsh = createInterfaceOsh(physAdapt, hostOsh)
        aliasOsh.setStringAttribute('interface_name', aliasName)
        aliasOsh.setBoolAttribute('isvirtual', 1)
        return aliasOsh

def getPhysicalEthAdapters(ethAdaptersList):
    adapters = []
    if ethAdaptersList:
        for eth in ethAdaptersList:
            if not eth.isVirtual and eth.interfaceType == ibm_hmc_lib.ETH_ADAPTER and eth.physicalPath and eth.macAddress and netutils.isValidMac(eth.macAddress):
                eth.macAddress = netutils.parseMac(eth.macAddress)
                adapters.append(eth)
    return adapters
    
def getVirtualEthAdapters(ethAdaptersList):
    adapters = []
    if ethAdaptersList:
        for eth in ethAdaptersList:
            if eth.isVirtual and eth.interfaceType == ibm_hmc_lib.ETH_ADAPTER:
                adapters.append(eth)
    return adapters
    
def getSeaAdapters(ethAdaptersList):
    adapters = []
    if ethAdaptersList:
        for eth in ethAdaptersList:
            if eth.interfaceType == ibm_hmc_lib.SEA_ADAPTER:
                adapters.append(eth)
    return adapters
    
def getLinkAggregationInterfaces(ethAdaptersList):
    adapters = []
    if ethAdaptersList:
        for eth in ethAdaptersList:
            if eth.interfaceType == ibm_hmc_lib.LINK_AGGREGATION_ADAPTER:
                adapters.append(eth)
    return adapters

def calculateAdaptersSpeed(adaptersList, ethAdaptersDict):
    if adaptersList and ethAdaptersDict:
        for adapter in adaptersList:
            if adapter.speed is None and adapter.usedAdapters:
                speed = 0
                for usedAdapterName in adapter.usedAdapters:
                    usedAdapter = ethAdaptersDict.get(usedAdapterName)
                    if usedAdapter:
                        if usedAdapter.speed is None and usedAdapter.usedAdapters and usedAdapterName not in usedAdapter.usedAdapters:
                            calculateAdaptersSpeed([usedAdapter], ethAdaptersDict)
                        if usedAdapter.speed is not None:
                            if adapter.interfaceType == ibm_hmc_lib.LINK_AGGREGATION_ADAPTER:
                                if adapter.operatingMode != ibm_hmc_lib.AGGREGATED_FAILOVER:
                                    speed += usedAdapter.speed
                                    continue
                            speed = usedAdapter.speed
                            
                if speed != 0:
                    adapter.speed = speed
                    
def isPhysicalSlot(ioSlot):
    if ioSlot and ioSlot.drcName and not re.search('\-V\d+\-', ioSlot.drcName, re.I):
        return 1
    
def doDiscovery(shell, hostOsh, managedSystemOsh, framework, osType):
    vector = ObjectStateHolderVector()
    scsiAdaptersList = []
    physAdaptList = []
    virtAdaptList = []
    seaAdaptList = []
    linkAggrAdaptList = []
    volumeGroupsDict = {}
    physicalVolumeDict = {}
    logicalVolumeDict = {}
    scsiManList = []
    pvAssignList = []
    fiberChannelAdaptersList = []
    ethAliasesList = []
    isVio = ibm_hmc_lib.isVio(shell)
    
    try:
        cpus = discover_cpus(shell, framework, isVio)
        for cpu in cpus:
            cpuOsh = modeling.createCpuOsh(cpu.idStr, managedSystemOsh, cpu.speed, cpu.coresCount, 'ibm_corp', data_name = cpu.model)
            vector.add(cpuOsh)
    except:
        logger.errorException('')
        framework.reportWarning('Failed to discover CPUs')

    if osType and osType.upper() == 'AIX':
        try:
            fiberChannelAdaptersList = discoverFiberChannels(shell)
        except:
            framework.reportWarning("Failed to discover Fibre Channel adapters")
        ethAdaptersDict = {}
        if isVio:
            ethAdaptersDict = discoverEthernetAdapters(shell)
            ethAliasesList = discoverEhernetAdapterAliasses(shell)
        else:
            ethAdaptersDict = discoverAixLparEthernetAdapters(shell)
        physAdaptList = getPhysicalEthAdapters(ethAdaptersDict.values())
        virtAdaptList = getVirtualEthAdapters(ethAdaptersDict.values())
        seaAdaptList = getSeaAdapters(ethAdaptersDict.values())
        linkAggrAdaptList = getLinkAggregationInterfaces(ethAdaptersDict.values())
        calculateAdaptersSpeed(linkAggrAdaptList, ethAdaptersDict)
        calculateAdaptersSpeed(seaAdaptList, ethAdaptersDict)
        calculateAdaptersSpeed(virtAdaptList, ethAdaptersDict)

        volumeGroupsDict = discoverVolumeGroups(shell)
        physicalVolumeDict = discoverPhysicalVolumes(shell)
        logicalVolumeDict = discoverLogicalVolumes(shell, volumeGroupsDict)
        if isVio:
            scsiAdaptersList = discoverScsi(shell, physicalVolumeDict, logicalVolumeDict)
            (scsiManList, pvAssignList) = discoverPhysScsiAndRaid(shell, physicalVolumeDict)
        else:
            (scsiManList, pvAssignList) = discoverLparPhysScsiAndRaid(shell, physicalVolumeDict)
    elif osType and osType.upper() == 'LINUX':
        scsiAdaptersList = discoverLinuxVScsiAdapters(shell)
        (volumeGroupsDict, logicalVolumeDict, physicalVolumeDict) = discoverLinuxStorageInfo(shell)
    ethAdaptersDict = {}
    if physAdaptList:
        for physAdapt in physAdaptList:
            physAdaptOsh = createInterfaceOsh(physAdapt, hostOsh)
            linkOsh = modeling.createLinkOSH('contained', managedSystemOsh, physAdaptOsh)
            vector.add(linkOsh)
            if physAdapt.physicalPath:
                ioSlot = ibm_hmc_lib.IoSlot()
                ioSlot.name = physAdapt.physicalPath
                ioSlot.drcName = physAdapt.physicalPath
                ioSlot.normalizedDrcName = ibm_hmc_lib.normaliseIoSlotDrcName(ioSlot.drcName)
                ioSlotOsh = None
                if isPhysicalSlot(ioSlot):
                    ioSlotOsh = ibm_hmc_lib.createIoSlotOsh(ioSlot, managedSystemOsh)
                else:
                    ioSlotOsh = ibm_hmc_lib.createIoSlotOsh(ioSlot, hostOsh)
                linkOsh = modeling.createLinkOSH('contained', ioSlotOsh, physAdaptOsh)
                vector.add(ioSlotOsh)
                vector.add(linkOsh)
                
            if ethAliasesList:
                for aliasName in ['en'+str(physAdapt.interfaceIndex), 'et'+str(physAdapt.interfaceIndex)]:
                    if aliasName in ethAliasesList:
                        aliasOsh = createAliasOsh(aliasName, hostOsh, physAdapt)
                        if aliasOsh:
                            vector.add(aliasOsh)
                            vector.add(vector.add(modeling.createLinkOSH('realization', physAdaptOsh, aliasOsh)))
            if logger.Version().getVersion(framework) < 9:
                interfaceIndexOsh = createInterfaceIndexOsh(physAdapt, hostOsh)
                if interfaceIndexOsh:
                    linkOsh = modeling.createLinkOSH('parent', interfaceIndexOsh, physAdaptOsh)
                    vector.add(interfaceIndexOsh)
                    vector.add(linkOsh)
#            vector.add(physAdaptOsh)
            ethAdaptersDict[physAdapt.name] = physAdaptOsh
    if linkAggrAdaptList:
        for linkAggr in linkAggrAdaptList:
            linkAggrOsh = createLinkAggrOsh(linkAggr, hostOsh)
            if linkAggr.usedAdapters:
                vector.add(linkAggrOsh)
                ethAdaptersDict[linkAggr.name] = linkAggrOsh
                for usedAdapterName in linkAggr.usedAdapters:
                    physAdaptOsh = ethAdaptersDict.get(usedAdapterName)
                    if physAdaptOsh:
                        #change the KEY attribute for the Physical Ethernet Adapter
                        mac = physAdaptOsh.getAttributeValue('interface_macaddr')
                        newKey = '%s_%s' % (mac, usedAdapterName)
                        physAdaptOsh.setAttribute('interface_macaddr', newKey)
                        ethAdaptersDict[usedAdapterName] = physAdaptOsh
                        linkOsh = modeling.createLinkOSH('member', linkAggrOsh, physAdaptOsh)
                        vector.add(linkOsh)
            if linkAggr.backupAdapter:
                ethBackOsh = ethAdaptersDict.get(linkAggr.backupAdapter)
                linkOsh = modeling.createLinkOSH('member', linkAggrOsh, ethBackOsh)
                vector.add(linkOsh)
    #Adding Physical ETH adapters to the result vector
    if ethAdaptersDict:
        for physAdaptOsh in ethAdaptersDict.values():
            vector.add(physAdaptOsh)
    if seaAdaptList:
        for seaAdapter in seaAdaptList:
            seaAdapterOsh = createSeaOsh(seaAdapter, hostOsh)
            if seaAdapter.usedAdapters:
                vector.add(seaAdapterOsh)
                ethAdaptersDict[seaAdapter.name] = seaAdapterOsh
                for usedAdapterName in seaAdapter.usedAdapters:
                    backAdapterOsh = ethAdaptersDict.get(usedAdapterName)
                    if backAdapterOsh:
                        linkOsh = modeling.createLinkOSH('use', seaAdapterOsh, backAdapterOsh)
                        vector.add(linkOsh)
    if virtAdaptList:
        for virtualAdapter in virtAdaptList:
            virtAdapterOsh = ibm_hmc_lib.createVEthOsh(virtualAdapter, hostOsh)
            vector.add(virtAdapterOsh)
            if ethAliasesList:
                for aliasName in ['en'+str(virtualAdapter.interfaceIndex), 'et'+str(virtualAdapter.interfaceIndex)]:
                        if aliasName in ethAliasesList:
                            aliasOsh = createAliasOsh(aliasName, hostOsh, virtualAdapter)
                            if aliasOsh:
                                vector.add(aliasOsh)
                                vector.add(vector.add(modeling.createLinkOSH('realization', virtAdapterOsh, aliasOsh)))
            if virtualAdapter.usedAdapters:
                for usedAdapterName in virtualAdapter.usedAdapters:
                    backAdapterOsh = ethAdaptersDict.get(usedAdapterName)
                    if backAdapterOsh:
                        linkOsh = modeling.createLinkOSH('use', virtAdapterOsh, backAdapterOsh)
                        vector.add(linkOsh)
            if virtualAdapter.physicalPath:
                ioSlot = ibm_hmc_lib.IoSlot()
                ioSlot.name = virtualAdapter.physicalPath
                ioSlot.drcName = virtualAdapter.physicalPath
                ioSlot.normalizedDrcName = ibm_hmc_lib.normaliseIoSlotDrcName(ioSlot.drcName)
                if isPhysicalSlot(ioSlot):
                    ioSlotOsh = ibm_hmc_lib.createIoSlotOsh(ioSlot, managedSystemOsh)
                else:
                    ioSlotOsh = ibm_hmc_lib.createIoSlotOsh(ioSlot, hostOsh)
                linkOsh = modeling.createLinkOSH('contained', ioSlotOsh, virtAdapterOsh)
                vector.add(ioSlotOsh)
                vector.add(linkOsh)
                
    if fiberChannelAdaptersList:
        for fiberChannelAdapter in fiberChannelAdaptersList:
            fiberChannelOsh = createFiberChannelOsh(fiberChannelAdapter, managedSystemOsh)
            vector.add(fiberChannelOsh)
            linkOsh = modeling.createLinkOSH('contained', hostOsh, fiberChannelOsh)
            vector.add(linkOsh)
            if fiberChannelAdapter.physPath:
                ioSlot = ibm_hmc_lib.IoSlot()
                ioSlot.name = fiberChannelAdapter.physPath
                ioSlot.drcName = fiberChannelAdapter.physPath
                ioSlot.normalizedDrcName = ibm_hmc_lib.normaliseIoSlotDrcName(ioSlot.drcName)
                ioSlotOsh = None
                if isPhysicalSlot(ioSlot):
                    ioSlotOsh = ibm_hmc_lib.createIoSlotOsh(ioSlot, managedSystemOsh)
                else:
                    ioSlotOsh = ibm_hmc_lib.createIoSlotOsh(ioSlot, hostOsh)
                linkOsh = modeling.createLinkOSH('contained', ioSlotOsh, fiberChannelOsh)
                vector.add(ioSlotOsh)
                vector.add(linkOsh)
    #create Storage Topology
    vector.addAll(storage_topology.createStorageTopology(volumeGroupsDict.values(), logicalVolumeDict.values(), physicalVolumeDict.values(), scsiAdaptersList, hostOsh))
    if scsiManList and pvAssignList:
        pScsiDict = {}
        for scsi in scsiManList:
            scsiOsh = None
            ioSlot = ibm_hmc_lib.IoSlot()
            ioSlot.name = scsi.physicalPath
            ioSlot.drcName = scsi.physicalPath
            ioSlot.normalizedDrcName = ibm_hmc_lib.normaliseIoSlotDrcName(ioSlot.drcName)
            ioSlotOsh = None
            if isPhysicalSlot(ioSlot):
                ioSlotOsh = ibm_hmc_lib.createIoSlotOsh(ioSlot, managedSystemOsh)
                scsiOsh = storage_topology.createScsiAdapterOsh(scsi, managedSystemOsh)
                linkOsh = modeling.createLinkOSH('contained', hostOsh, scsiOsh)
                vector.add(linkOsh)
            else:
                ioSlotOsh = ibm_hmc_lib.createIoSlotOsh(ioSlot, hostOsh)
                scsiOsh = storage_topology.createScsiAdapterOsh(scsi, hostOsh)
            vector.add(scsiOsh)
            pScsiDict[scsi.slotNumber] = scsiOsh
            linkOsh = modeling.createLinkOSH('contained', ioSlotOsh, scsiOsh)
            vector.add(ioSlotOsh)
            vector.add(linkOsh)
        for pv in pvAssignList:
            pvOsh = storage_topology.createPhysicalVolumeOsh(pv, hostOsh)
            scsiOsh = pScsiDict.get(pv.scsiAdapterSlotNumber)
            if pvOsh and scsiOsh:
                vector.add(pvOsh)
                linkOsh = modeling.createLinkOSH("depend", pvOsh, scsiOsh)
                vector.add(linkOsh)

    return vector

##############################################
########      MAIN                  ##########
##############################################
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    protocol = Framework.getDestinationAttribute('Protocol')
    hostCmdbId = Framework.getDestinationAttribute('hostId')
    managedSystemCmdbId = Framework.getDestinationAttribute('managedSystemId')
    osType = Framework.getDestinationAttribute('osType')

    client = None
    shell = None
    hostOsh = modeling.createOshByCmdbId('host', hostCmdbId)
    managedSystemOsh = modeling.createOshByCmdbId('ibm_pseries_frame', managedSystemCmdbId)
    try:
        client = Framework.createClient()
        shell = shellutils.ShellUtils(client)
        OSHVResult = doDiscovery(shell, hostOsh, managedSystemOsh, Framework, osType)
    except Exception, ex:
        exInfo = ex.getMessage()
        errormessages.resolveAndReport(exInfo, protocol, Framework)
    except:
        exInfo = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(exInfo, protocol, Framework)
    try:
        shell and shell.closeClient()
    except:
        logger.debugException("")
        logger.error('Unable to close shell')
    return OSHVResult
