#coding=utf-8
'''
Created on Jan 23, 2012

@author: vvitvitskiy
'''
import entity
import sap
from appilog.common.system.types import ObjectStateHolder


class ProductEnum:
    class Type(entity.Immutable):
        def __init__(self, name, instanceProductName):
            self.name = name
            self.instanceProductName = instanceProductName

        def __repr__(self):
            return self.name

        def __eq__(self, other):
            return (isinstance(other, self.__class__)
                    and self.name == other.name)

        def __ne__(self, other):
            return not self.__eq__(other)

    TREX = Type('TREX', 'SAP TREX Instance')
    BIA = Type('BIA', 'SAP BIA Instance')

    def values(self):
        return [self.TREX, self.BIA]

Product = ProductEnum()


class DefaultProfile(sap.DefaultProfile):
    r'Contains additional information about product type: BIA or TREX'

    def __init__(self, system, productType):
        r'@types: sap.System, Product.Type -> '
        if not productType in Product.values():
            raise ValueError("Invalid product name")
        sap.DefaultProfile.__init__(self, system)
        self.__productType = productType

    def getProductType(self):
        r'@types: -> Product.Type'
        return self.__productType


class NameServerModeEnum:
    FIRST_MASTER = '1st master'
    MASTER = 'master'
    SLAVE = 'slave'

    def values(self):
        return (self.FIRST_MASTER, self.MASTER, self.SLAVE)

NameServerMode = NameServerModeEnum()


class Builder:

    def buildTrexSystem(self, sapSystem):
        r'@types: sap.System -> ObjectStateHolder[sap_trex_system]'
        if not sapSystem:
            raise ValueError("SAP System is not specified")
        osh = ObjectStateHolder('sap_trex_system')
        osh.setStringAttribute('name', sapSystem.getName())
        osh.setStringAttribute('vendor', sap.VENDOR)
        return osh

    def buildInstance(self, instance):
        r'@types: sap.Instance -> ObjectStateHolder[sap_trex_instance]'
        if not instance:
            raise ValueError("Instance is not specified")
        osh = ObjectStateHolder('sap_trex_instance')
        osh.setStringAttribute('number', instance.getNumber())
        osh.setStringAttribute('name', instance.getName())
        osh.setStringAttribute('vendor', sap.VENDOR)
        return osh

    def updateInstanceNumber(self, instanceOsh, number):
        r'@types: ObjectStateHolder, str -> ObjectStateHolder'
        if not instanceOsh:
            raise ValueError("Instance OSH is not specified")
        if not (number and sap.isCorrectSapInstanceNumber(number)):
            raise ValueError("Instance number is not correct")
        instanceOsh.setAttribute('number', number)
        return instanceOsh

    def updateNameServerMode(self, instanceOsh, mode):
        r'@types: ObjectStateHolder[sap_trex_instance], str -> ObjectStateHolderVector'
        if not instanceOsh:
            raise ValueError("Instance OSH is not correct")
        if not (mode and mode in NameServerMode.values()):
            raise ValueError("Name server mode value is not correct")

        instanceOsh.setStringAttribute('name_server_mode', mode)
        return instanceOsh


class Reporter(sap._HasBuilder):

    def reportSystem(self, sapSystem):
        r'@types: sap.System -> ObjectStateHolder'
        if not sapSystem:
            raise ValueError("TREX System is not specified")
        return self._getBuilder().buildTrexSystem(sapSystem)

    def reportInstance(self, instance, containerOsh):
        r'@types: sap.Instance, ObjectStateHolder -> ObjectStateHolder'
        if not instance:
            raise ValueError("Instance is not specified")
        if not containerOsh:
            raise ValueError("Container OSH is not specified")
        osh = self._getBuilder().buildInstance(instance)
        osh.setContainer(containerOsh)
        return osh


class HostBuilder:

    def buildHostByHostname(self, hostname):
        r'@types: str -> ObjectStateHolder[node]'
        if not (hostname and hostname.strip()):
            raise ValueError("Hostname is not specified or empty")
        osh = ObjectStateHolder('node')
        osh.setStringAttribute('name', hostname)
        return osh


class HostReporter(sap._HasBuilder):

    def reportHostByHostname(self, hostname):
        r'@types: str, list[str] -> ObjectStateHolder'
        return self._getBuilder().buildHostByHostname(hostname)
