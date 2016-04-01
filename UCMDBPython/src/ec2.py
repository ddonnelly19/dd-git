#coding=utf-8
'''
Created on Aug 26, 2011

@author: vvitvitskiy
'''
import entity
from appilog.common.system.types.vectors import ObjectStateHolderVector
import modeling
import netutils
from appilog.common.system.types import ObjectStateHolder
import aws
from java.lang import Boolean
import aws_store


class Address:
    def __init__(self, hostname, ipAddress):
        r'''@types: str, str
        @raise ValueError: hostname is empty
        @raise ValueError: Invalid IP address
        '''
        if not hostname:
            raise ValueError("hostname is empty")
        if not (ipAddress and netutils.isValidIp(ipAddress)):
            raise ValueError("Invalid IP address")
        self.__hostname = hostname
        self.__ipAddress = ipAddress

    def getHostname(self):
        r'@types: -> str'
        return str(self.__hostname)

    def getIpAddress(self):
        r'@types: -> str'
        return str(self.__ipAddress)

    def __repr__(self):
        return r'ec2.Address("%s", "%s")' % (self.__hostname, self.__ipAddress)


class Image(entity.HasName, aws.HasId):
    r'''Abstract class for different types of Amazon Image
    Image is identified with name and ID
    '''
    class Type:
        MACHINE = 'machine'
        KERNEL = 'kernel'
        RAMDISK = 'ramdisk'

    class VisiblityType:
        PUBLIC = 'public'
        PRIVATE = 'private'

    def __init__(self, name, id_):
        r'''@types: str, str
        @raise ValueError: Id is empty
        @raise ValueError: Name is empty
        '''
        entity.HasName.__init__(self, name)
        # image id of format ami-3e3ecd57
        aws.HasId.__init__(self, id_)
        self.description = None
        # restrict format
        self.__architecture = None
        # getKernelId: aki-a3d737ca
        # getState: available
        # getVirtualizationType: paravirtual

        # Image.VisiblityType
        self.__visibility = None

    def withVisibility(self, isPublic):
        r'@types: str'
        self.__visibility = (Boolean.valueOf(isPublic)
                             and Image.VisiblityType.PUBLIC
                             or Image.VisiblityType.PRIVATE)
        return self

    def getVisibility(self):
        r'@types: -> Image.VisiblityType'
        return self.__visibility


class Instance(aws.HasId):
    r'''
    Image instance
    '''

    def __init__(self, id_, imageId):
        r'''@types: str, str
        @raise ValueError: Instance ID is empty
        @raise ValueError: Image ID is empty
        '''
        aws.HasId.__init__(self, id_)
        #  AMI id the instance was launched with
        if not imageId:
            raise ValueError("Image ID is empty")
        self.__imageId = imageId

    def getImageId(self):
        r'@types: -> str'
        return str(self.__imageId)


class Ami(Image):
    r''' Amazon Machine Image
    '''
    def __init__(self, name, id_, isPublic=None, description=None):
        r'''@types: str, str, bool
        @raise ValueError: Id is empty
        @raise ValueError: Name is empty
        '''
        Image.__init__(self, name, id_)
        self.withVisibility(isPublic)
        self.description = description

    def __repr__(self):
        return 'ec2.Ami("%s", "%s")' % (self.getName(), self.getId())

    class Instance(Instance, entity.HasOsh):
        class Type:
            '''t1.micro, m1.small, m1.large, m1.xlarge, m2.xlarge, m2.2xlarge,
             m2.4xlarge, c1.medium, c1.xlarge, cc1.4xlarge, cg1.4xlarge'''

        def __init__(self, id_, imageId, type=None, publicAddress=None,
                     privateAddress=None,
                     launchIndex=None,
                     keyPairName=None,
                     availabilityZoneName=None):
            r'@types: str, str, ec2.Address, ec2.Address, Number, str, str'
            Instance.__init__(self, id_, imageId)
            entity.HasOsh.__init__(self)
            self.publicAddress = publicAddress
            self.privateAddress = privateAddress
            self.type = type
            self.launchIndex = entity.WeakNumeric(int)
            if launchIndex is not None:
                self.launchIndex.set(launchIndex)
            self.__keyPairName = keyPairName
            self.__mappedDevices = []
            self.availabilityZoneName = availabilityZoneName

        def addMappedDevice(self, device):
            r'''@types: aws_store.MappedVolume
            @raise ValueError: Invalid mapped device
            '''
            if not (device and isinstance(device, aws_store.MappedVolume)):
                raise ValueError("Invalid mapped device")
            self.__mappedDevices.append(device)

        def getMappedDevices(self):
            r'@types: -> list(aws_store.MappedVolume)'
            return self.__mappedDevices[:]

        def getKeyPairName(self):
            r'@types: -> str or None'
            return self.__keyPairName and str(self.__keyPairName)

        def acceptVisitor(self, visitor):
            return visitor.visitEc2AmiInstance(self)

        def __repr__(self):
            return 'ec2.Ami.Instance("%s", "%s", "%s")' % (self.getId(),
                                                           self.getImageId(),
                                                           self.type)


class ElasticIp:
    r'''
    Elastic IP addresses are static IP addresses designed for dynamic cloud
    computing. An Elastic IP address is associated with your account not
    a particular instance, and you control that address until you choose to
    explicitly release it. Unlike traditional static IP addresses, however,
    Elastic IP addresses allow you to mask instance or Availability Zone
    failures by programmatically remapping your public IP addresses
    to any instance in your account.
    '''
    def __init__(self, publicIp, instanceId=None):
        r'''@types: str, str
        @raise ValueError: Invalid IP
        '''
        if not (publicIp and netutils.isValidIp(publicIp)):
            raise ValueError("Invalid IP")
        self.__publicIp = publicIp
        self.__instanceId = instanceId

    def getIp(self):
        r'@types: -> str'
        return self.__publicIp

    def getInstanceId(self):
        r'@types: -> str or None'
        return self.__instanceId

    def __repr__(self):
        return "%s(%s, %s)" % (self.__class__, self.__publicIp,
                               self.__instanceId)


class Builder:

    class Ec2InstanceNode(entity.HasOsh):
        r'PDO intended to build node'
        def __init__(self, amiInstance):
            r'@types: ec2.Ami.Instance'
            self.amiInstance = amiInstance
            entity.HasOsh.__init__(self)

        def acceptVisitor(self, visitor):
            return visitor.visitEc2AmiInstanceNode(self)

    class Ec2AmiInstanceConfig(entity.HasOsh):
        r'PDO intended to build virtual host resource'
        def __init__(self, ami, instance):
            r'@types: ec2.Ami'
            self.ami = ami
            self.instance = instance
            entity.HasOsh.__init__(self)

        def acceptVisitor(self, visitor):
            return visitor.visitEc2AmiInstanceConfig(self)

    def visitEc2AmiInstanceConfig(self, ec2AmiInstanceConfig):
        r'@types: ec2.Ami.Instance -> ObjectStateHolder'
        ami = ec2AmiInstanceConfig.ami
        instance = ec2AmiInstanceConfig.instance
        osh = ObjectStateHolder('amazon_ec2_config')
        osh.setStringAttribute('name', ami.getName())
        osh.setStringAttribute('ami_visibility', str(ami.getVisibility()))
        osh.setStringAttribute('description', ami.description)
        osh.setStringAttribute('type', instance.type)
        osh.setStringAttribute('ami_id', ami.getId())
        index = instance.launchIndex
        if index and index.value() is not None:
            osh.setAttribute('ami_launch_index', index.value())
        if instance.getKeyPairName():
            osh.setAttribute('key_pair_name', instance.getKeyPairName())
        return osh

    def visitEc2AmiInstanceNode(self, ec2InstanceNode):
        r'''@types: ec2.Builder.Ec2InstanceNode -> ObjectStateHolder
        @raise ValueError: Public address is not specified
        '''
        address = ec2InstanceNode.amiInstance.publicAddress
        if not address:
            raise ValueError("Public address is not specified")
        osh = modeling.createHostOSH(address.getIpAddress())
        # description set with instance name value
        # TODO
        # osh.setAttribute('description', "Instance name: %" % ec2InstanceNode.amiInstance.getName())
        # is complete
        osh.setBoolAttribute('host_iscomplete', 1)
        osh.setAttribute("host_key", str(ec2InstanceNode.amiInstance.getId()))
        # PrimaryDnsName
        osh.setAttribute("primary_dns_name", address.getHostname())
        # NodeRole | Is Virtual
        builder = modeling.HostBuilder(osh)
        builder.setAsVirtual(1)
        # Name is extracted from DNS name. we assume that the first part
        # of the DNS name is equal to the host name.
        dnsName = address.getHostname().split('.', 1)[0]
        builder.setAttribute("name", dnsName)
        return builder.build()


class Reporter:

    def __init__(self, builder):
        r'@types: ec2.Builder'
        self.__builder = builder

    def _createOshVector(self):
        return ObjectStateHolderVector()

    def reportPublicIpAddress(self, account, ipAddress, hostOsh):
        r'@types: aws.Account, str, OSH -> OSHV'
        vector = self._createOshVector()
        ipOsh = modeling.createIpOSH(ipAddress)
        ipOsh.setAttribute('ip_domain', account.getId())
        vector.add(ipOsh)
        vector.add(modeling.createLinkOSH('containment', hostOsh, ipOsh))
        return vector

    def reportPrivateIpAddress(self, ipAddress, hostOsh):
        r'@types: str, OSH -> OSHV'
        vector = self._createOshVector()
        ipOsh = modeling.createIpOSH(ipAddress)
        vector.add(ipOsh)
        vector.add(modeling.createLinkOSH('containment', hostOsh, ipOsh))
        return vector

    def buildInstanceNode(self, instance):
        r'@types: ec2.Ami.Instance -> ObjectStateHolder'
        nodePdo = self.__builder.Ec2InstanceNode(instance)
        return nodePdo.build(self.__builder)

    def reportAmiInstance(self, account, ami, instance):
        r'''@types: aws.Account, ec2.Ami, ec2.Ami.Instance -> ObjectStateHolderVector
        @raise ValueError: AWS Account is not specified or not built
        @raise ValueError: AMI instance is not specified
        '''
        if not (account and account.getOsh()):
            raise ValueError("AWS Account is not specified or not built")
        if not ami:
            raise ValueError("AMI is not specified")
        if not instance:
            raise ValueError("AMI instance is not specified")
        vector = self._createOshVector()
        # use synthetic PDO to build node (Account as container),
        # container for the Instance
        nodeOsh = self.buildInstanceNode(instance)
        vector.add(nodeOsh)
        vector.add(modeling.createLinkOSH('containment', account.getOsh(),
                                          nodeOsh))
        # report ec2 config
        configPdo = self.__builder.Ec2AmiInstanceConfig(ami, instance)
        vector.add(configPdo.build(self.__builder))
        configPdo.getOsh().setContainer(nodeOsh)
        # report IPs
        address = instance.publicAddress
        if address:
            vector.addAll(self.reportPublicIpAddress(account,
                                             address.getIpAddress(), nodeOsh))
        address = instance.privateAddress
        if address:
            vector.addAll(self.reportPrivateIpAddress(address.getIpAddress(),
                                                      nodeOsh))
        return vector

    def linkAmiInstanceToAvailabilityZone(self, instance, zoneOsh):
        r'@types: ec2.Ami.Instance, aws.AvailabilityZone -> ObjectStateHolderVector'
        if not instance:
            raise ValueError("AMI instance is not specified")
        if not zoneOsh:
            raise ValueError("Availability zone OSH is not specified")
        vector = self._createOshVector()
        nodePdo = self.__builder.Ec2InstanceNode(instance)
        vector.add(nodePdo.build(self.__builder))
        vector.add(zoneOsh)
        vector.add(modeling.createLinkOSH('membership', zoneOsh,
                                          nodePdo.getOsh()))
        return vector
