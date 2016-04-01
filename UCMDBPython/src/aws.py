#coding=utf-8
'''
Created on Aug 12, 2011

@author: vvitvitskiy
'''
import entity
import modeling
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector


class HasId:
    def __init__(self, id_):
        if id_ is None:
            raise ValueError("Id is empty")
        self.__id = id_

    def getId(self):
        r'@types: -> obj'
        return self.__id


class State:
    AVAILABLE = 'available'
    NOT_AVAILABE = 'notavailable'


class Account(HasId, entity.HasOsh):
    r''' Amazon account'''
    def __init__(self, id_):
        r'''@types: str
        @param id: Amazon Account ID
        '''
        HasId.__init__(self, id_)
        entity.HasOsh.__init__(self)

    def acceptVisitor(self, visitor):
        r'@types: CanVisitAwsAccount -> ObjectStateHolder'
        return visitor.visitAwsAccount(self)


class Region(entity.HasName, entity.HasOsh):
    r''' Amazon EC2 region. EC2 regions are completely isolated from each other
    '''
    def __init__(self, name, endpointHostName=None):
        r'''Region is identified by name so endpoint hostname is optional
        @types: str, str
        @param endpointHostName: Service endpoint hostname
        '''
        entity.HasName.__init__(self)
        entity.HasOsh.__init__(self)
        self.setName(name)
        self.__endpointHostName = endpointHostName
        self.__availabilityZones = []

    def addZone(self, zone):
        r'''@types: aws.AvailabilityZone
        @raise ValueError: Zone is not specified
        '''
        if not zone:
            raise ValueError("Zone is not specified")
        self.__availabilityZones.append(zone)

    def getZones(self):
        r'@types: -> list(aws.AvailabilityZone)'
        return self.__availabilityZones[:]

    def getEndpointHostName(self):
        r'@types: -> str or None'
        return str(self.__endpointHostName)

    def acceptVisitor(self, visitor):
        return visitor.visitAwsRegion(self)

    def __repr__(self):
        return 'aws.Region("%s", "%s")' % (self.getName(),
                                           self.getEndpointHostName())


class AvailabilityZone(entity.HasName, entity.HasOsh):
    r'''An EC2 availability zone, separate and fault tolerant from other
     availability zones'''

    def __init__(self, name, regionName, state):
        r'''@types: str, str, aws.State
        @raise ValueError: Name is empty
        @raise ValueError: State is empty
        @raise ValueError: Region name is empty
        '''
        entity.HasName.__init__(self)
        entity.HasOsh.__init__(self)
        self.setName(name)
        if not state:
            raise ValueError("State is empty")
        if not regionName:
            raise ValueError("Region name is empty")
        self.__state = state
        self.__regionName = regionName

    def getState(self):
        r'@types: -> AvailabilityZone.State'
        return self.__state

    def getRegionName(self):
        r'@types: -> str'
        return str(self.__regionName)

    def acceptVisitor(self, visitor):
        r'''@types: CanVisitAwsAvailabilityZone -> object
        Introduce interface for visitor expected here
        '''
        return visitor.visitAwsAvailabilityZone(self)

    def __repr__(self):
        return 'aws.AvailabilityZone("%s", "%s", "%s")' % (
                            self.getName(), self.__regionName, self.getState())


class Builder:

    def __buildLocationOsh(self, name, locationType, typeStr):
        r'@types: str, str, str -> ObjectStateHolder'
        osh = ObjectStateHolder('location')
        osh.setAttribute('name', name)
        osh.setAttribute('data_note', typeStr)
        osh.setAttribute('location_type', locationType)
        return osh

    def buildUndefinedLocationOsh(self, name, typeStr):
        return self.__buildLocationOsh(name, 'undefined', typeStr)

    def visitAwsAccount(self, account):
        r'@types: aws.Account -> ObjectStateHolder'
        osh = ObjectStateHolder('amazon_account')
        osh.setAttribute('name', account.getId())
        return osh

    def visitAwsAvailabilityZone(self, availabilityZone):
        r'@types: aws.AvailabilityZone -> ObjectStateHolder'
        return self.buildUndefinedLocationOsh(availabilityZone.getName(),
                                              'Availability Zone')

    def visitAwsRegion(self, region):
        r'@types: aws.Region -> ObjectStateHolder'
        return self.buildUndefinedLocationOsh(region.getName(), 'Region')


class Reporter:
    def __init__(self, locationBuilder):
        r'@types: aws.Builder'
        self.__builder = locationBuilder

    def _createOshVector(self):
        return ObjectStateHolderVector()

    def reportAccount(self, account):
        r'''@types: aws.Account -> ObjectStateHolder
        @raise ValueError: AWS Account is not specified
        '''
        if not account:
            raise ValueError("AWS Account is not specified")
        return account.build(self.__builder)

    def reportRegion(self, region):
        r'''@types: aws.Region -> ObjectStateHolderVector
        @raise ValueError: Region is not specified
        '''
        if not region:
            raise ValueError("Region is not specified")
        vector = ObjectStateHolderVector()
        vector.add(region.build(self.__builder))
        return vector

    def reportAvailabilityZoneByName(self, name):
        r'''@types: str -> ObjectStateHolder
        @raise ValueError: Zone name is not specified
        '''
        return self.__builder.buildUndefinedLocationOsh(name,
                                                        'Availability Zone')

    def reportAvailabilityZone(self, zone):
        r'''@types: aws.AvailabilityZone -> ObjectStateHolder
        @raise ValueError: Zone is not specified
        '''
        if not zone:
            raise ValueError("Zone is not specified")
        return zone.build(self.__builder)

    def reportAvailabilityZoneInRegion(self, region, zone):
        r'''@types: aws.Regtion, aws.AvailabilityZone -> ObjectStateHolderVector
        @raise ValueError: Region is not specified or not built
        @raise ValueError: Zone is not specified
        '''
        if not (region and region.getOsh()):
            raise ValueError("Region is not specified or not built")
        if not zone:
            raise ValueError("Zone is not specified")
        vector = self._createOshVector()
        regionOsh = region.getOsh()
        vector.add(regionOsh)
        vector.add(zone.build(self.__builder))
        vector.add(modeling.createLinkOSH('containment', regionOsh,
                                          zone.getOsh()))
        return vector
