#coding=utf-8
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
import modeling
import logger


class ScsiAdapter:
    """
    SCSI Adapter Data Object
    """
    def __init__(self):
        self.name = None
        self.type = None
        self.bios = None
        self.bandwidth = None
        self.parentId = None
        self.patentName = None
        self.slotNumber = None
        self.isVirtual = None
        self.physicalPath = None
        self.lunId = None

class VolumeGroup:
    """
    Volume Group Data Object
    """
    def __init__(self):
        self.vgName = None
        self.vgId = None
        self.vgState = None
        self.vgPpSize = None
        self.logicalVolumes = None
        self.physicalVolumes = None

class PhysicalVolume:
    """
    Physical Volume Data Object
    """
    def __init__(self):
        self.pvName = None
        self.pvId = None
        self.pvState = None
        self.pvSize = None
        self.pvAlternateName = None
        self.volumeGroupName = None
        self.scsiAdapterSlotNumber = None

class LogicalVolume:
    """
    Logical Volume Data Object
    """
    def __init__(self):
        self.lvName = None
        self.lvId = None
        self.lvAccType = None
        self.lvAvailability = None
        self.lvDomainId = None
        self.lvFsType = None
        self.lvShareName = None
        self.lvSize = None
        self.lvState = None
        self.lvStorCapabilities = None
        self.mountPoint = None
        self.volumeGroupName = None
        self.lvFree = None
        self.lvUsed = None
        self.scsiAdapterSlotNumber = None
        
def createVolumeGroupOsh(volumeGroup, parentOsh):
    """
    Creates Object State Holder for Volume Group CI
    @param volumeGroup: the discovered Volume Group
    @type volumeGroup: instance of the VolumeGroup Data Object
    @param parentOsh: Object State Holder of the Host this Volume Group belongs to
    @type parentOsh: OSH instance of a Host CI or any of its siblings
    @return: Volume Group OSH  
    """
    if volumeGroup and volumeGroup.vgName:
        vgOsh = ObjectStateHolder("volumegroup")
        vgOsh.setStringAttribute("data_name", volumeGroup.vgName)
        if volumeGroup.vgId:
            vgOsh.setStringAttribute("volume_group_id", volumeGroup.vgId)
        vgOsh.setContainer(parentOsh)
        return vgOsh
        

def createPhysicalVolumeOsh(physicalVolume, parentOsh):
    """
    Creates Object State Holder for Physical Volume CI
    @param physicalVolume: the discovered Physical Volume
    @type physicalVolume: instance of the PhysicalVolume Data Object
    @param parentOsh: Object State Holder of the Host this Physical Volume belongs to
    @type parentOsh: OSH instance of a Host CI or any of its siblings
    @return: Physical Volume OSH  
    """
    if physicalVolume and physicalVolume.pvName:
        pvOsh = ObjectStateHolder("physicalvolume")
        pvOsh.setStringAttribute("data_name", physicalVolume.pvName)
        if physicalVolume.pvId:
            pvOsh.setStringAttribute("volume_id", physicalVolume.pvId)
        if physicalVolume.pvSize:
            pvOsh.setDoubleAttribute("volume_size", physicalVolume.pvSize)
        pvOsh.setContainer(parentOsh)
        return pvOsh

def createLogicalVolumeOsh(logicalVolume, parentOsh):
    """
    Creates Object State Holder for Logical Volume CI
    @param logicalVolume: the discovered Logical Volume
    @type logicalVolume: instance of the LogicalVolume Data Object
    @param parentOsh: Object State Holder of the Host this Logical Volume belongs to
    @type parentOsh: OSH instance of a Host CI or any of its siblings
    @return: Logical Volume OSH  
    """
    if logicalVolume and logicalVolume.lvName:
        lvOsh = ObjectStateHolder("logicalvolume")
        lvOsh.setStringAttribute("data_name", logicalVolume.lvName)
        if logicalVolume.lvId:
            lvOsh.setIntegerAttribute("logicalvolume_id", logicalVolume.lvId)
        if logicalVolume.lvSize:
            lvOsh.setDoubleAttribute("logicalvolume_size", logicalVolume.lvSize)
        if logicalVolume.lvState:
            lvOsh.setStringAttribute("logicalvolume_status", logicalVolume.lvState)
        if logicalVolume.lvStorCapabilities:
            lvOsh.setStringAttribute("logicalvolume_stotagecapabilities", logicalVolume.lvStorCapabilities)
        if logicalVolume.lvAccType:
            lvOsh.setStringAttribute("logicalvolume_accesstype", logicalVolume.lvAccType)
        if logicalVolume.lvAvailability:
            lvOsh.setStringAttribute("logicalvolume_availability", logicalVolume.lvAvailability)
        if logicalVolume.lvDomainId:
            lvOsh.setStringAttribute("logicalvolume_domainid", logicalVolume.lvDomainId)
        if logicalVolume.lvFsType:
            lvOsh.setStringAttribute("logicalvolume_fstype", logicalVolume.lvFsType)
        if logicalVolume.lvShareName:
            lvOsh.setStringAttribute("logicalvolume_sharename", logicalVolume.lvShareName)
        if logicalVolume.lvFree:
            lvOsh.setDoubleAttribute("logicalvolume_free", logicalVolume.lvFree)
        if logicalVolume.lvUsed:
            lvOsh.setDoubleAttribute("logicalvolume_used", logicalVolume.lvUsed)
        lvOsh.setContainer(parentOsh)
        return lvOsh

def createScsiAdapterOsh(scsiAdapter, parentOsh):
    """
    Creates Object State Holder for SCSI Adapter CI
    @param scsiAdapter: the discovered SCSI Adapter
    @type scsiAdapter: instance of the ScsiAdapter Data Object
    @param parentOsh: Object State Holder of the Host this SCSI Adapter belongs to
    @type parentOsh: OSH instance of a Host CI or any of its siblings
    @return: SCSI Adapter OSH  
    """
    if scsiAdapter and scsiAdapter.slotNumber:
        scsiOsh = ObjectStateHolder("scsi_adapter")
        scsiOsh.setStringAttribute("slot_id", scsiAdapter.slotNumber)
        if scsiAdapter.name:
            scsiOsh.setStringAttribute("data_name", scsiAdapter.name)
        if scsiAdapter.type:
            scsiOsh.setStringAttribute("type", scsiAdapter.type)
        if scsiAdapter.bios:
            scsiOsh.setStringAttribute("bios_version", scsiAdapter.bios)
        if scsiAdapter.bandwidth:
            scsiOsh.setIntegerAttribute("bandwidth", scsiAdapter.bandwidth)
        if scsiAdapter.isVirtual:
            scsiOsh.setBoolAttribute("isvirtual", 1)
        scsiOsh.setContainer(parentOsh)
        return scsiOsh
    
def createStorageTopology(volumeGroupList, logicalVolumeList, physicalVolumeList, scsiAdaptersList, parentOsh):
    """
    Creates Objects State Holders for Volume Groups, Logical Volumes, Physical Volumes, SCSI Adapters 
    and corresponding Use and Depend links among them
    @param volumeGroupList: discovered Volume Groups
    @type volumeGroupList: list of VolumeGroup Data Objects instances
    @param logicalVolumeList: discovered Logical Volumes 
    @type logicalVolumeList: list of LogicalVolume Data Objects instances
    @param physicalVolumeList: discovered Physical Volumes 
    @type physicalVolumeList: list of PhysicalVolume Data Objects instances
    @param scsiAdaptersList: discovered SCSI Adapters
    @type scsiAdaptersList: list of ScsiAdapter Data Objects instances
    @param parentOsh: Object State Holder of the Host this SCSI Adapter belongs to
    @type parentOsh: OSH instance of a Host CI or any of its siblings
    @return: Object State Holder Vector of the discovered topology
    """
    vector = ObjectStateHolderVector()
    vgOshDict = {}
    if volumeGroupList:
        for volumeGroup in volumeGroupList:
            vgOsh = createVolumeGroupOsh(volumeGroup, parentOsh)
            if vgOsh:
                vgOshDict[volumeGroup.vgName] = vgOsh
                vector.add(vgOsh)
    
    scsiAdaptersOshDict = {}
    if scsiAdaptersList:
        for scsiAdapter in scsiAdaptersList:
            scsiOsh = createScsiAdapterOsh(scsiAdapter, parentOsh)
            if scsiOsh:
                scsiAdaptersOshDict[scsiAdapter.slotNumber] = scsiOsh
                vector.add(scsiOsh)
                
    if logicalVolumeList:
        for logicalVolume in logicalVolumeList:
            lvOsh = createLogicalVolumeOsh(logicalVolume, parentOsh)
            if lvOsh:
                if logicalVolume.volumeGroupName and vgOshDict.has_key(logicalVolume.volumeGroupName):
                    vgOsh = vgOshDict.get(logicalVolume.volumeGroupName)
                    linkOsh = modeling.createLinkOSH('contained', vgOsh, lvOsh)
                    vector.add(linkOsh)
                if logicalVolume.scsiAdapterSlotNumber and scsiAdaptersOshDict.has_key(logicalVolume.scsiAdapterSlotNumber):
                    scsiOsh = scsiAdaptersOshDict.get(logicalVolume.scsiAdapterSlotNumber)
                    linkOsh = None
                    if scsiOsh.getAttributeValue("isvirtual"):
                        linkOsh = modeling.createLinkOSH("use", scsiOsh, lvOsh)
                    else:
                        linkOsh = modeling.createLinkOSH("depend", lvOsh, scsiOsh)
                    vector.add(linkOsh)
                if logicalVolume.mountPoint and logicalVolume.lvFsType:
                    fsOsh = modeling.createDiskOSH(parentOsh, logicalVolume.mountPoint, modeling.UNKNOWN_STORAGE_TYPE)
                    linkOsh = modeling.createLinkOSH('depend', fsOsh, lvOsh)
                    vector.add(fsOsh)
                    vector.add(linkOsh)
                vector.add(lvOsh)
    
    if physicalVolumeList:
        for physicalVolume in physicalVolumeList:
            pvOsh = createPhysicalVolumeOsh(physicalVolume, parentOsh)
            if pvOsh:
                if physicalVolume.volumeGroupName and vgOshDict.has_key(physicalVolume.volumeGroupName):
                    vgOsh = vgOshDict.get(physicalVolume.volumeGroupName)
                    linkOsh = modeling.createLinkOSH('contained', vgOsh, pvOsh)
                    vector.add(linkOsh)
                if physicalVolume.scsiAdapterSlotNumber and scsiAdaptersOshDict.has_key(physicalVolume.scsiAdapterSlotNumber):
                    scsiOsh = scsiAdaptersOshDict.get(physicalVolume.scsiAdapterSlotNumber)
                    linkOsh = None
                    if scsiOsh.getAttributeValue("isvirtual"):
                        linkOsh = modeling.createLinkOSH("use", scsiOsh, pvOsh)
                    else:
                        linkOsh = modeling.createLinkOSH("depend", pvOsh, scsiOsh)
                    vector.add(linkOsh)
                vector.add(pvOsh)
    return vector
