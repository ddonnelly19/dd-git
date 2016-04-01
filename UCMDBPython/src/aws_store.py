#coding=utf-8
'''
Created on Sep 19, 2011

@author: vvitvitskiy
'''
import aws
import entity
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
import modeling
from java.util import Date
from java.lang import Double


class Volume:
    'Base class for store volume types'
    def __repr__(self):
        return 'Volume'


class Ebs(Volume, aws.HasId, entity.HasOsh):
    r'''Amazon Elastic Block Store - Block level storage volumes for use with
    Amazon EC2 instances. Using Amazon EBS, data on the root device will persist
    independently from the lifetime of the instance'''
    def __init__(self, id_, sizeInMb=None, snapshotId=None, state=None,
                 availabilityZoneName=None):
        r'@types: str, long, str, str, str'
        aws.HasId.__init__(self, id_)
        entity.HasOsh.__init__(self)
        self.sizeInMb = entity.WeakNumeric(long)
        if sizeInMb is not None:
            self.sizeInMb.set(sizeInMb)
        # EbsSnapshot ID from which this volume was created
        self.__snapshotId = snapshotId
        self.__state = state
        self.__availabilityZoneName = availabilityZoneName

    def getAvailabilityZoneName(self):
        r'@types: -> Maybe[str]'
        return self.__availabilityZoneName

    def getSnapshotId(self):
        r'@types: -> Maybe[str]'
        return self.__snapshotId

    def acceptVisitor(self, visitor):
        return visitor.visitAwsEbs(self)

    def __repr__(self):
        return "aws_store.Ebs(%s, %s)" % (self.getId(), self.getSnapshotId())

    class Snapshot(aws.HasId, entity.HasOsh):
        r'''EBS Snapshot'''
        def __init__(self, id_, volume=None, description=None, startTime=None):
            r'''@types: str, aws_store.Ebs, str, Date
            @raise ValueError: Wrong EBS Volume specified
            @raise ValueError: Wrong format of start time
            '''
            aws.HasId.__init__(self, id_)
            entity.HasOsh.__init__(self)
            self.description = description
            # set volume
            self.__volume = None
            if volume is not None:
                if isinstance(volume, Ebs):
                    self.__volume = volume
                else:
                    raise ValueError("Wrong Ebs Volume specified")
            self.__startTime = None
            if startTime:
                if isinstance(startTime, Date):
                    self.__startTime = startTime
                else:
                    raise ValueError("Wrong format of start time")

        def getVolume(self):
            r'@types: -> aws_store.Volume or None'
            return self.__volume

        def getStartTime(self):
            r'@types: -> Maybe[java.util.Date]'
            return self.__startTime

        def acceptVisitor(self, visitor):
            return visitor.visitAwsEbsSnapshot(self)

        def __repr__(self):
            return "aws_store.EbsSnapshot(%s, %s)" % (
                    self.getId(), self.getVolume())


class InstanceStore(Volume, entity.HasOsh):
    'Local instance store. Persists during the life of the instance'
    def __init__(self):
        entity.HasOsh.__init__(self)

    def acceptVisitor(self, visitor):
        visitor.visitAwsInstanceStore(self)


class MappedVolume(entity.HasName, entity.HasOsh):
    r'Volume mapped to the instance or image, so it has a name'
    def __init__(self, name, volume):
        r'@types: str, aws_store.Volume'
        entity.HasName.__init__(self)
        entity.HasOsh.__init__(self)
        self.setName(name)
        if not (volume and isinstance(volume, Volume)):
            raise ValueError("Wrong volume specified")
        self.__volume = volume

    def acceptVisitor(self, visitor):
        return visitor.visitAwsMappedVolume(self)

    def getVolume(self):
        r'@types: -> aws_store.Volume'
        return self.__volume

    def __repr__(self):
        return 'aws_store.MappedVolume(%s, %s)' % (self.getName(), self.__volume)


class _Type:
    EBS = 'ebs'
    INSTANCE_STORE = 'instance-store'

    def values(self):
        return (self.EBS, self.INSTANCE_STORE)


Type = _Type()


class Builder:
    def visitAwsEbsSnapshot(self, snapshot):
        r'@types: aws_store.EbsSnapshot -> ObjectStateHolder'
        osh = ObjectStateHolder('logicalvolume_snapshot')
        osh.setAttribute('name', snapshot.getId())
        if snapshot.getStartTime():
            osh.setAttribute('snapshot_create_time', snapshot.getStartTime())
        volume = snapshot.getVolume()
        if volume:
            osh.setAttribute('data_note', "VolumeId: %s" % volume.getId())
        osh.setBoolAttribute('isvirtual', 1)
        if snapshot.description:
            osh.setAttribute('description', snapshot.description)
        return osh

    def visitAwsEbs(self, ebs):
        r'@types: aws_store.Ebs -> ObjectStateHolder'
        osh = ObjectStateHolder('logical_volume')
        osh.setAttribute('logical_volume_global_id', ebs.getId())
        if ebs.sizeInMb and ebs.sizeInMb.value() is not None:
            size = Double.valueOf(ebs.sizeInMb.value())
            osh.setAttribute('logicalvolume_size', size)
        return osh

    def visitAwsInstanceStore(self, volume):
        r'@types: aws_store.InstanceStore -> ObjectStateHolder'
        return ObjectStateHolder('logical_volume')

    def visitAwsMappedVolume(self, mappedVolume):
        r'@types: aws_store.MappedVolume -> ObjectStateHolder'
        osh = mappedVolume.getVolume().build(self)
        osh.setAttribute('name', mappedVolume.getName())
        return osh


class Reporter:
    def __init__(self, builder):
        r'@types: ebs.Builder'
        self.__builder = builder

    def _createVector(self):
        return ObjectStateHolderVector()

    def reportMappedVolume(self, mappedVolume, containerOsh):
        r'@types: aws.Account, aws_store.MappedVolume -> ObjectStateHolderVector'
        if not containerOsh:
            raise ValueError("Mapped volume container is not specified")
        if not mappedVolume:
            raise ValueError("Mapped volume is not specified")
        volumeOsh = mappedVolume.build(self.__builder)
        volumeOsh.setContainer(containerOsh)
        return volumeOsh

    def linkMappedVolumeToAvailabilityZone(self, mappedVolumeOsh, zoneOsh):
        r'@types: ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder'
        if not mappedVolumeOsh:
            raise ValueError("Mapped volume is not specified")
        if not zoneOsh:
            raise ValueError("Availability Zone is notspecified")
        return modeling.createLinkOSH('membership', zoneOsh, mappedVolumeOsh)

    def linkSnapshotAndMappedVolume(self, snapshotOsh, volumeOsh):
        r'@types: ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder'
        if not snapshotOsh:
            raise ValueError("AWS EBS snapshot is not specified")
        if not volumeOsh:
            raise ValueError("Mapped volume is not specified")
        return modeling.createLinkOSH('containment', snapshotOsh, volumeOsh)

    def reportSnapshot(self, snapshot, containerOsh):
        r'@types: aws_store.EbsSnapshot, ObjectStateHolder -> ObjectStateHolderVector'
        if not snapshot:
            raise ValueError("AWS EBS snapshot is not specified")
        if not containerOsh:
            raise ValueError("AWS Snapshot container is not specified")
        osh = snapshot.build(self.__builder)
        osh.setContainer(containerOsh)
        return osh


def createByType(storeType, storeName):
    r'@types: aws_store.Volume.Type, str -> aws_store.Volume'
    if storeType not in Type.values():
        raise ValueError("Unsupported store type")
    if storeType == Type.EBS:
        return Ebs(storeName)
    return InstanceStore()
