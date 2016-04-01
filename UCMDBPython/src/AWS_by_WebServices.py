#coding=utf-8
# Discovery of Amazon Cloud using Web Services
# ============================================
"""
Created on Aug 18, 2011
@author: Vladimir Vitvitskiy

Discovery can be configured to cover several AWS services, for instance

  * EC2 (Elastic Cloud Service)
  * RDS (Relational Database Service)
"""

from java.util import ArrayList
from java.util import Properties
from java.lang import Exception as JException, Boolean
import re
import logger
import aws
import ec2
from appilog.common.system.types.vectors import ObjectStateHolderVector
import errormessages
import errorobject
import errorcodes
import aws_store
import iteratortools
import aws_rds
import db
import netutils
import db_platform
import db_builder
from com.hp.ucmdb.discovery.library.clients import MissingSdkJarException


# Module entry point
# ------------------
def DiscoveryMain(framework):
    # === Declaration ===

    # Discovery infrastructure has predefined protocol and client for the AWS,
    # called _awsprotocol_ which is used for different discoveries.
    protocolName = 'awsprotocol'
    # As module serves for discoveries using multiple services we need a single
    # point where we can handle discovery input date, result and errors in a
    # single way.

    # Configuration of discoveries per Amazon Service allows us to declare
    # possible flows:
    CONNECTIONS = (
                # * Perform **EC2** discovery in case if job parameter
                # _ec2DiscoveryEnabled_ is set to "true". Here we have
                # specific method to connect service and list of discoveries
                # where this connection will be used.
               _Connection(_connectToEc2Service,
                          (_Discovery('ec2DiscoveryEnabled',
                                      _discoverEc2Topology,
                                      'EC2 Discovery'
                                      ),
                          )
               ),
                # * Perform **RDS** discovery in case if job parameter
                # _rdsDiscoveryEnabled_ is set to "true"
               _Connection(_connectToRdsService,
                          (_Discovery('rdsDiscoveryEnabled',
                                      _discoverRdsTopology,
                                      'RDS Discovery'),))
    )
    # Having declared flows we have a mechanism to determine which one should
    # be run. Framework can provide information about job parameters and
    # discovery object has corresponding configuration

    def isEnabledDiscovery(discovery, framework=framework):
        if discovery.jobParameter in ('ec2DiscoveryEnabled',
                                      'rdsDiscoveryEnabled'):
            return 1
        jobParameter = framework.getParameter(discovery.jobParameter)
        return Boolean.parseBoolean(jobParameter)

    # Containers for the errors and warnings per discovery life cycle
    discoveryErrors = []
    discoveryWarnings = []
    # For the whole Job run we need to know whether there is one successful
    # discovery
    oneDiscoveryHappened = 0

    # === Connection attempt ===

    # We have to find all registered credentials for different accounts
    # to iterate over them for further discovery
    credentials = framework.getAvailableProtocols(None, protocolName)
    for credentialsId in credentials:
        # Establish connection to the IAM and get account ID
        logger.info('establish connection to IAM service')
        try:
            aimService = _connectToIamService(framework, credentialsId)
        except MissingSdkJarException, e:
            # Missed AWS SDK jars no need to continue discovery report error
            discoveryErrors.append(errorobject.createError(
                                        errorcodes.MISSING_JARS_ERROR,
                                        ['AWS SDK jars are missed. '
                                         'Refer documentation for details'],
                                                           str(e))
                                   )
            break
        except (JException, Exception), e:
            # In case if connection failed we try another credentials, maybe for
            # the same account
            msg = str(e)
            logger.warnException(msg)
            if ((msg.find('Status Code: 401') != -1)
                or re.match('.*?Attribute.*?has no value', msg.strip(), re.I)):
                warning = errorobject.createError(errorcodes.INVALID_USERNAME_PASSWORD, [protocolName], str(e))
            elif msg.find('Unable to execute HTTP request') != -1:
                warning = errorobject.createError(errorcodes.DESTINATION_IS_UNREACHABLE, [protocolName], str(e))
            else:
                warning = errorobject.createError(errorcodes.CONNECTION_FAILED, [protocolName], msg)
            discoveryWarnings.append(warning)
        else:
            try:
                # Build and report discovered account for further usage
                discoverer = IamDiscoverer(aimService)
                account = aws.Account(discoverer.getAccountId(aimService))
                accountOsh = aws.Reporter(aws.Builder()).reportAccount(account)
                framework.sendObject(accountOsh)
            except Exception:
                # As account is a application system failed discovery of such
                # cannot be continued we try other credentials
                logger.debugException("Failed to create account")
                warning = errorobject.createError(errorcodes.FAILED_GETTING_INFORMATION,
                                                                [protocolName],
                            'Failed to get information about Amazon account')
                discoveryWarnings.append(warning)
                # Every fail has to be remembered for reporting to the UI
            else:
                # Now we have account time to use it in discovery
                for connection in CONNECTIONS:
                    # Apply filtering mechanism to find out what discoveries
                    # are enabled
                    discoveries = filter(isEnabledDiscovery, connection.discoveries)
                    # Possible none of them are enabled so we have to check this
                    # case too
                    if discoveries:
                        # If we have enabled - we perform connection to the
                        # service only once for, possible, multiple discovery flows
                        # that are based on the same service.
                        try:
                            service = connection(framework, credentialsId)
                        except (JException, Exception), e:
                            logger.debugException(str(e))
                        else:
                            # === Run enabled discoveries ===

                            # Each discovery has one attemp to execute its flow
                            # successfully return some topology as ObjectStateHolderVector
                            for discovery in discoveries:
                                try:
                                    # Opened question whether we have to return some
                                    # object that will describe various interesting
                                    # information for client (reported to the UI)
                                    # In any case now it is a vector and it will
                                    # be sent immediately
                                    vector = discovery(framework, service, account)
                                    # === Sending data to the UCMDB
                                    framework.sendObjects(vector)
                                    # At this point we have one successful discovery
                                    oneDiscoveryHappened = 1
                                except (JException, Exception), e:
                                    logger.debugException(str(e))
                                    warning = errorobject.createError(
                                                    errorcodes.INTERNAL_ERROR ,
                                                    None,
                                            "%s failed" % discovery.description)
                                    discoveryWarnings.append(warning)
    # === Error cases handling ===

    # Discovery finished and we have to show reasons in the UI:
    #
    # * No credentials found for _aws_ protocol
    if not credentials:
        msg = errormessages.makeErrorMessage(protocolName, pattern=errormessages.ERROR_NO_CREDENTIALS)
        errobj = errorobject.createError(errorcodes.NO_CREDENTIALS_FOR_TRIGGERED_IP, [ protocolName ], msg)
        logger.reportErrorObject(errobj)
    # * Among enabled flows no successful discovery
    elif not oneDiscoveryHappened:
        errobj = errorobject.createError(errorcodes.FAILED_RUNNING_DISCOVERY, ['Amazon Cloud'], 'Failed to make discovery')
        logger.reportErrorObject(errobj)

    # * Other, like connection troubles or failed discovery
    map(logger.reportErrorObject, discoveryErrors)
    map(logger.reportWarningObject, discoveryWarnings)
    return ObjectStateHolderVector()

# Discovery details
# -----------------


def _discoverEc2Topology(framework, ec2Service, account):
    r'@types: Framework, Ec2Service, aws.Account'

    logger.info('Discover REGIONS')
    # first of all get information about available Regions and Availability Zones
    regions = _discoverRegionsWithZones(ec2Service)

    # get information about running instances in our account
    vector = ObjectStateHolderVector()
    for region in regions:
        # Discovery collects instances information from each available region.
        # So we establish connection to
        # each of them.
        ec2Service.setEndpoint(region.getEndpointHostName())
        instances = _discoverRunningEc2AmiInstances(ec2Service)

        # every instance has mapped devices (currently we are interested in EBS)
        # to get more detailed information about volumes we have to gather all
        # their uniq IDs
        def getInstanceEbsIds(instance):
            r'@types: ec2.Ami.Instance -> list[str]'
            return map(lambda e: e.getVolume().getId(), instance.getMappedDevices())

        ids = _applySet(_toItself, iteratortools.flatten(map(getInstanceEbsIds, instances)))
        # get VOLUMES by IDs
        volumes = ids and _discoverVolumesByIds(ec2Service, ids) or ()
        logger.debug(str(volumes))
        # having volumes on hands we can get information about corresponding

        # snapshots by IDs so again - gather unique IDs
        ids = filter(None, _applySet(aws_store.Ebs.getSnapshotId, volumes))
        snapshots = ids and map(_partialFunc(_discoverVolumeSnapshotById, ec2Service, _), ids) or ()
        snapshots = filter(None, snapshots)
        logger.debug(str(snapshots))
        logger.info("Discovered %s snapshots" % len(snapshots))

        # Get images for the running instances by IDs
        # gather unique IDs
        ids = _applySet(ec2.Ami.Instance.getImageId, instances)

        # discover AMIs by IDs
        amis = ids and _discoverEc2AmisByIds(ec2Service, ids) or ()
        # for further lookup create mapping of AMI to ID
        amiById = _applyMapping(ec2.Ami.getId, amis)
        instancesByAmiId = _groupBy(ec2.Ami.Instance.getImageId, instances)
        # Discover available elastic IPs and group them by instance id to which they
        # belong. Before grouping performing filtering by non-empty instance ID
        ec2Discoverer = Ec2Discoverer(ec2Service)
        elasticIpsByInstanceId = _groupBy(ec2.ElasticIp.getInstanceId,
                                  filter(ec2.ElasticIp.getInstanceId,
                                    warnException(ec2Discoverer.getElasticIps,
                                        (), message="Failed to get elastic IPs")()))

        logger.info('REPORT DATA')

        try:
            # First of all we have to prepare reporters for each domain
            awsReporter = aws.Reporter(aws.Builder())
            ec2Reporter = ec2.Reporter(ec2.Builder())
            storeReporter = aws_store.Reporter(aws_store.Builder())
            # report Account information
            vector.add(awsReporter.reportAccount(account))
            # mapping of built availability zone to its name
            zoneByName = {}
            # Regions and corresponding availability zones
            try:
                vector.addAll(awsReporter.reportRegion(region))
            except Exception:
                logger.warnException("Failed to report %s" % region)
            else:
                for zone in region.getZones():
                    try:
                        vector.addAll(awsReporter.reportAvailabilityZoneInRegion(region, zone))
                        zoneByName[zone.getName()] = zone
                    except Exception:
                        logger.warnException("Failed to report %s" % zone)

            volumeById = _applyMapping(aws_store.Ebs.getId, volumes)
            # group snapshots by volume ID
            snapshotsById = _groupBy(aws_store.Ebs.Snapshot.getId, snapshots)
            # report running Instances with mapped devices, IPs and configurations
            # report only instances which AMI detailed information available
            for amiId in filter(amiById.has_key, instancesByAmiId.keys()):
                for instance in instancesByAmiId.get(amiId):
                    try:
                        # report AMI instances
                        ami = amiById.get(amiId)
                        vector.addAll(ec2Reporter.reportAmiInstance(account, ami, instance))
                        # report link to the availability zone
                        zone = zoneByName.get(instance.availabilityZoneName)
                        if zone and zone.getOsh():
                            vector.addAll(ec2Reporter.linkAmiInstanceToAvailabilityZone(instance, zone.getOsh()))
                        else:
                            logger.warn("Failed to find zone %s for %s" % (
                                                instance.availabilityZoneName,
                                                instance))
                        # report mapped devices
                        devices = instance.getMappedDevices()
                        logger.info("Report mapped devices (%s) for instance %s" %
                                    (len(devices), instance.getId()))
                        containerOsh = ec2Reporter.buildInstanceNode(instance)

                        # report elastic IP as usual public IP address in AWS account
                        for elasticIp in elasticIpsByInstanceId.get(instance.getId(), ()):
                            vector.addAll(ec2Reporter.reportPublicIpAddress(account, elasticIp.getIp(), containerOsh))

                        for mappedVolume in devices:
                            volume = volumeById.get(mappedVolume.getVolume().getId())
                            if volume:
                                mappedVolume = aws_store.MappedVolume(mappedVolume.getName(), volume)
                            volumeOsh = storeReporter.reportMappedVolume(mappedVolume, containerOsh)
                            vector.add(volumeOsh)
                            # report link between availability zone and EBS
                            zoneName = mappedVolume.getVolume().getAvailabilityZoneName()
                            if zoneByName.has_key(zoneName):
                                zoneOsh = zoneByName[zoneName].getOsh()
                                vector.add(storeReporter.linkMappedVolumeToAvailabilityZone(volumeOsh, zoneOsh))
                            # report related snapshots if exist
                            volumeSnapshots = snapshotsById.get(volume.getSnapshotId()) or ()
                            logger.info("Report %s snapshots for the mapped volume %s" %
                                        (len(volumeSnapshots), volume.getId()))
                            for snapshot in volumeSnapshots:
                                snapshotOsh = storeReporter.reportSnapshot(snapshot, account.getOsh())
                                vector.add(snapshotOsh)
                                vector.add(storeReporter.linkSnapshotAndMappedVolume(snapshotOsh, volumeOsh))
                    except Exception:
                        logger.warnException("Failed to report %s" % instance)
        except (JException, Exception):
            logger.warnException("Failed to report topology")
    return vector

# === Connect methods ===

# First of all each service has different connect mechanism that is extracted
# to specific method.


def _connectToRdsService(framework, credentialsId):
    """Connection method for the **Relational Database Service**
     @types: Framework, str -> RdsClient
    """
    from com.hp.ucmdb.discovery.library.clients.cloud.aws import ServiceType
    from com.hp.ucmdb.discovery.library.clients.cloud.aws import Client

    properties = Properties()
    properties.setProperty(Client.AWS_SERVICE_TYPE_PROPERTY, ServiceType.RDS.name()) #@UndefinedVariable
    properties.setProperty('credentialsId', credentialsId)
    return framework.createClient(properties).getService()


def _connectToEc2Service(framework, credentialsId):
    """Connection method for the **Elastic Cloud Service**
     @types: Framework, str -> Ec2Client
    """
    from com.hp.ucmdb.discovery.library.clients.cloud.aws import ServiceType
    from com.hp.ucmdb.discovery.library.clients.cloud.aws import Client

    properties = Properties()
    properties.setProperty(Client.AWS_SERVICE_TYPE_PROPERTY, ServiceType.EC2.name()) #@UndefinedVariable
    properties.setProperty('credentialsId', credentialsId)
    return framework.createClient(properties).getService()


def _connectToIamService(framework, credentialsId):
    """Connection method for the **Identity and Access Management**
     @types: Framework, str -> IamClient
    """
    from com.hp.ucmdb.discovery.library.clients.cloud.aws import ServiceType
    from com.hp.ucmdb.discovery.library.clients.cloud.aws import Client

    properties = Properties()
    properties.setProperty('credentialsId', credentialsId)
    properties.setProperty(Client.AWS_SERVICE_TYPE_PROPERTY, ServiceType.IAM.name()) #@UndefinedVariable
    return framework.createClient(properties).getService()


# === Aim Discoverer ===

class IamDiscoverer:
    """ Discoverer that play role of single point of access to the Identity and
     Accessibility Management
    """

    def __init__(self, service):
        self._service = service

    def getAccountId(self, iamService):
        """ Get account ID using ARN
        You specify the resource using the following Amazon Resource Name (ARN)
        format: arn:aws:<vendor>:<region>:<namespace>:<relative-id>

        * **vendor** identifies the AWS product (e.g., sns)
        * **region** is the AWS Region the resource resides in (e.g., us-east-1), if any
        * **namespace** is the AWS account ID with no hyphens (e.g., 123456789012)
        * **relative-id** is the service specific portion that identifies the specific resource

        @types: AimService -> str
        @raise ValueError: Wrong ARN format
        """
        result = iamService.getUser()
        # get Amazon Resource Name (ARN)
        # arn:aws:iam::846188145964:root
        arn = result.getUser().getArn()
        tokens = arn.split(':')
        # 4th token is ID
        if len(tokens) > 3:
            return tokens[4]
        raise ValueError("Wrong ARN format")


# === EC2 Discoverer ===

class Ec2Discoverer:
    def __init__(self, service):
        self._service = service

    def _convertToRegion(self, item):
        r'@types: com.amazonaws.services.ec2.model.Region -> aws.Region'
        return aws.Region(item.getRegionName(), item.getEndpoint())

    def getRegions(self):
        r'@types: -> list[aws.Region]'
        results = self._service.describeRegions().getRegions()
        return map(self._convertToRegion, results)

    def _convertToAvailabilityZone(self, item):
        r'@types: com.amazonaws.services.ec2.model.AvailabilityZone -> aws.AvailabilityZone'
        return aws.AvailabilityZone(item.getZoneName(),
                             item.getRegionName(),
                             item.getState())

    def getAvailabilityZones(self):
        r'@types: -> list[aws.AvailabilityZone]'
        results = self._service.describeAvailabilityZones().getAvailabilityZones()
        return map(self._convertToAvailabilityZone, results)

    def convertToEc2Ami(self, item):
        r'@types: com.amazonaws.services.ec2.model.Image -> ec2.Ami'
        ami = ec2.Ami(item.getName(), item.getImageId(),
                      description=item.getDescription())
        return ami.withVisibility(item.getPublic())

    def getAmisByIds(self, ids):
        r'@types: list[str] -> ec2.Ami'
        from com.amazonaws.services.ec2.model import DescribeImagesRequest
        request = DescribeImagesRequest().withImageIds(_toArrayList(ids))
        items = self._service.describeImages(request).getImages() or ()
        return map(self.convertToEc2Ami, items)

    def _convertToAwsEbs(self, item):
        r'@types: com.amazonaws.services.ec2.model.Volume -> aws_store.Ebs'
        return aws_store.Ebs(item.getVolumeId())

    def _convertToMappedVolume(self, item):
        r'@types: InstanceBlockDeviceMapping -> aws_store.MappedVolume'
        return aws_store.MappedVolume(
                                  item.getDeviceName(),
                                  self._convertToAwsEbs(item.getEbs())
                )

    def _convertToEc2AmiInstance(self, item):
        r'@types: com.amazonaws.services.ec2.model.Instance -> ec2.Ami.Instance'
        logger.debug("Convert Instance ( %s ) to DO" % item.getInstanceId())
        placement = item.getPlacement()
        availabilityZoneName = placement and placement.getAvailabilityZone()
        publicAddress = privateAddress = None
        # public address
        if item.getPublicDnsName() and item.getPublicIpAddress():
            publicAddress = ec2.Address(item.getPublicDnsName(),
                                        item.getPublicIpAddress())
        # private address
        if item.getPrivateDnsName() and item.getPrivateIpAddress():
            privateAddress = ec2.Address(item.getPrivateDnsName(),
                                        item.getPrivateIpAddress())
        instance = ec2.Ami.Instance(item.getInstanceId(),
                                    item.getImageId(),
                                    item.getInstanceType(),
                                    publicAddress,
                                    privateAddress,
                                    launchIndex=item.getAmiLaunchIndex(),
                                    keyPairName=item.getKeyName(),
                                    availabilityZoneName=availabilityZoneName
                                    )
        # process mapped devices, if root device is EBS it will be
        # in list of mapped devices, otherwise - it is instance-store
        # it does not have name so is useless for discovery
        _apply(instance.addMappedDevice, map(self._convertToMappedVolume,
                            item.getBlockDeviceMappings()))
        return instance

    def _getInstancesByFilters(self, filters):
        r'''@types: list[com.amazonaws.services.ec2.model.Filter] -> list[ec2.Ami.Instance]'''
        # get only running instances
        from com.amazonaws.services.ec2.model import DescribeInstancesRequest
        filters = _toArrayList(filters)
        request = DescribeInstancesRequest().withFilters(filters)
        result = self._service.describeInstances(request)
        reservations = result.getReservations()
        # each reservation has list of instances we want to process
        instances = []
        for r in reservations:
            instances.extend(filter(None, map(self._convertToEc2AmiInstance, r.getInstances())))
        return instances

    def getInstancesByStatus(self, status):
        r'''@types: str -> list[ec2.Ami.Instance]'''
        from com.amazonaws.services.ec2.model import Filter
        values = _toArrayList([status])
        return self._getInstancesByFilters([Filter('instance-state-name').
                                            withValues(values)])

    def getRunningInstances(self):
        r'''@types: -> list[ec2.Ami.Instance]'''
        return self.getInstancesByStatus("running")

    def convertToEc2Ebs(self, item):
        r'@types: com.amazonaws.services.ec2.model.Volume -> aws_store.Ebs'
        sizeInGb = item.getSize()
        sizeInMb = sizeInGb and str(sizeInGb).isnumeric() and int(sizeInGb) * 1024
        return aws_store.Ebs(item.getVolumeId(),
                         sizeInMb=sizeInMb,
                         snapshotId=item.getSnapshotId(),
                         state=item.getState(),
                         availabilityZoneName=item.getAvailabilityZone()
                         )

    def convertToVolumeSnapshot(self, item):
        r'@types: com.amazonaws.services.ec2.model.Snapshot -> aws_store.Ebs.Snapshot'
        ebsVolume = None
        if item.getVolumeId():
            sizeInGb = item.getVolumeSize()
            sizeInMb = sizeInGb and str(sizeInGb).isnumeric() and int(sizeInGb) * 1024
            ebsVolume = aws_store.Ebs(item.getVolumeId(), sizeInMb)
        return aws_store.Ebs.Snapshot(item.getSnapshotId(),
                              volume=ebsVolume,
                              description=item.getDescription(),
                              startTime=item.getStartTime())

    def convertToEc2ElasticIp(self, item):
        r'@types: com.amazonaws.services.ec2.model.Address -> ec2.ElasticIp'
        return ec2.ElasticIp(item.getPublicIp(),
                             instanceId=item.getInstanceId())

    def getVolumeSnapshotById(self, id):
        r'''@types: str -> aws_store.Ebs.Snapshot
        @raise ValueError: No IDs specified to find corresponding snapshot
        '''
        if not id:
            raise ValueError("No ID specified to find corresponding snapshot")
        from com.amazonaws.services.ec2.model import DescribeSnapshotsRequest
        request = DescribeSnapshotsRequest().withSnapshotIds(_toArrayList([id]))
        resultItems = self._service.describeSnapshots(request).getSnapshots() or ()
        return map(self.convertToVolumeSnapshot, resultItems)[0]

    def getVolumesByIds(self, ids):
        r'''@types: list[str] -> list[aws_store.Ebs]
        @raise ValueError: No IDs specified to find corresponding volumes
        '''
        if not ids:
            raise ValueError("No IDs specified to find corresponding volumes")
        from com.amazonaws.services.ec2.model import DescribeVolumesRequest
        request = DescribeVolumesRequest().withVolumeIds(_toArrayList(ids))
        resultItems = self._service.describeVolumes(request).getVolumes() or ()
        return map(self.convertToEc2Ebs, resultItems)

    def getElasticIps(self):
        r'''@types: -> list[ec2.ElasticIp]'''
        return map(self.convertToEc2ElasticIp, self._service.describeAddresses().getAddresses() or ())


def _discoverRegionsWithZones(service):
    r'@types: AmazonEC2 -> list(aws.Region)'
    logger.info('Discover REGIONS and ZONES')
    discoverer = Ec2Discoverer(service)
    regionByName = {}
    try:
        regionByName = _applyMapping(aws.Region.getName, discoverer.getRegions())
    except JException, je:
        logger.warnException("Failed to discover regions: %s" % je )
    try:
        # map availability zones to corresponding regions
        for zone in discoverer.getAvailabilityZones():
            region = regionByName.get(zone.getRegionName())
            if region:
                region.addZone(zone)
    except JException:
        logger.warnException("Failed to discover zones")
    logger.info("Discovered %s zones" % len(regionByName))
    return regionByName.values()


def _discoverEc2AmisByIds(service, ids):
    r'''List and describe registered AMIs and AMIs you have launch permissions for.
    The AMI parameters, if specified, are the AMIs to describe.
    The  result  set  of  AMIs  described are the intersection of the AMIs specified,
    AMIs owned by the owners specified and AMIs with launch permissions as specified
    by the executable by options.

    @types: AmazonEC2, list[str] -> list[ec2.Ami]
    '''
    logger.info('Discover AMIs by such IDs %s' % ids)
    discoverer = Ec2Discoverer(service)
    images = warnException(discoverer.getAmisByIds, [])(ids)
    logger.info("Discovered AMIs: %s" % len(images))
    return images


def _apply(fn, iterable):
    r'Combinator similar to map but ignoring fn result'
    for i in iterable:
        fn(i)


def warnException(fn, defaultValue, ex=(Exception, JException), message=None):
    r'''
    @types: callable[I, O], O, tuple, str  -> Option[O]
    '''
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ex, e:
            logger.warnException(message or str(e))
        return defaultValue
    return wrapped


def _discoverRunningEc2AmiInstances(service):
    r'''
    @types: AmazonEC2  -> list(ec2.Ami.Instance)
    '''
    logger.info("Discover running instances")
    discoverer = Ec2Discoverer(service)
    instances = warnException(discoverer.getRunningInstances, [],
                              "Failed to discover instances")()
    # filter instances with public and private addresses
    instances = filter(lambda i: i.publicAddress or i.privateAddress, instances)
    logger.info("Discovered %s instances" % len(instances))
    return instances


class RdsDiscoverer:
    def __init__(self, service):
        self._service = service

    def _convertToTcpEndpoint(self, item):
        r'@types: com.amazonaws.services.rds.model.Endpoint -> netutils.Endpoint'
        return netutils.Endpoint(item.getPort(),
                                 netutils.ProtocolType.TCP_PROTOCOL,
                                 item.getAddress())

    def _convertToParameterGroupStatus(self, item):
        r'''@types: com.amazonaws.services.rds.model.DBParameterGroupStatus -> aws_rds.ParameterGroupStatus
        '''
        return aws_rds.ParameterGroup(item.getDBParameterGroupName(),
                                            status = item.getParameterApplyStatus())

    def _convertToSecurityGroupMembership(self, item):
        r'''@types: com.amazonaws.services.rds.model.DBSecurityGroupMembership -> aws_rds.SecurityGroupMembership
        '''
        return aws_rds.SecurityGroup(item.getDBSecurityGroupName(),
                                               status = item.getStatus())

    def _converttoDbInstance(self, item):
        r'''@types: com.amazonaws.services.rds.model.DBInstance -> aws_rds.Instance

        getDBParameterGroups()#rovides the list of DB Parameter Groups applied to this DB Instance.
            com.amazonaws.services.rds.model.DBParameterGroupStatus
            getDBParameterGroupName() # The name of the DP Parameter Group.
            getParameterApplyStatus() # The status of parameter updates.
        getDBSecurityGroups() # Provides List of DB Security Group elements containing only DBSecurityGroup.Name and DBSecurityGroup.Status subelements.
            com.amazonaws.services.rds.model.DBSecurityGroupMembership
            getDBSecurityGroupName()
            getStatus()
        '''

        dbName = item.getDBName()
        platform = db_platform.findPlatformBySignature(item.getEngine())
        vendor = platform and platform.vendor
        databases = dbName and [db.Database(dbName)]
        endpoint = self._convertToTcpEndpoint(item.getEndpoint())
        server = db.DatabaseServer(endpoint.getAddress(),
                                   endpoint.getPort(),
                                   databases=databases,
                                   vendor=vendor,
                                   version=item.getEngineVersion(),
                                   platform=platform)

        sizeInGb = item.getAllocatedStorage()
        sizeInMb = ((sizeInGb and str(sizeInGb).isnumeric)
                        and sizeInGb * 1024
                        or None)
        return aws_rds.Instance(item.getDBInstanceIdentifier(),
                                server,
                                type=item.getDBInstanceClass(),
                                status=item.getDBInstanceStatus(),
                                licenseModel=item.getLicenseModel(),
                                sizeInMb=sizeInMb,
                                availabilityZoneName=item.getAvailabilityZone(),
                                creationTime=item.getInstanceCreateTime(),
                                engineName=item.getEngine(),
                                parameterGroups=map(self._convertToParameterGroupStatus,
                                                      item.getDBParameterGroups()),
                                securityGroups=map(self._convertToSecurityGroupMembership,
                                                     item.getDBSecurityGroups())
                                )

    def _convertToDbEngine(self, item):
        r'@types: com.amazonaws.services.rds.model.DBEngineVersion -> aws_rds.Engine'
        return aws_rds.Engine(item.getEngine(),
                              version=item.getEngineVersion(),
                              versionDescription=item.getDBEngineVersionDescription(),
                              description=item.getDBEngineDescription())

    def _convertToParameterGroup(self, item):
        r'@types: com.amazonaws.services.rds.model.DBParameterGroup -> aws_rds.ParameterGroup'
        return aws_rds.ParameterGroup(item.getDBParameterGroupName(),
                                      description=item.getDescription(),
                                      family=item.getDBParameterGroupFamily())

    def _convertToSecurityGroup(self, item):
        r'@types: com.amazonaws.services.rds.model.DBSecurityGroup -> aws_rds.SecurityGroup'
        return aws_rds.SecurityGroup(item.getDBSecurityGroupName(),
                                     description=item.getDBSecurityGroupDescription(),
                                     ownerId=item.getOwnerId()
                                     )

    def _convertToDbSnapshot(self, item):
        r'@types: com.amazonaws.services.rds.model.DBSnapshot -> aws_rds.Snapshot'
        sizeInGb = item.getAllocatedStorage()
        sizeInMb = ((sizeInGb and str(sizeInGb).isnumeric)
                        and sizeInGb * 1024
                        or None)
        # create database server
        platform = db_platform.findPlatformBySignature(item.getEngine())
        vendor = platform and platform.vendor
        server = db.DatabaseServer(port=item.getPort(), vendor=vendor,
                                   versionDescription=item.getEngineVersion())
        # create DB Instance based on server
        instance = aws_rds.Instance(item.getDBInstanceIdentifier(), server,
                         licenseModel=item.getLicenseModel(),
                         sizeInMb=sizeInMb,
                         availabilityZoneName=item.getAvailabilityZone(),
                         creationTime=item.getInstanceCreateTime())
        # create DB Snapshot based on instance
        return aws_rds.Snapshot(item.getDBSnapshotIdentifier(), instance,
                                creationTime=item.getSnapshotCreateTime(),
                                status=item.getStatus()
                                )

    def getDbInstances(self):
        r'@types: -> list[aws_rds.Instance]'
        return map(self._converttoDbInstance, self._service.describeDBInstances().getDBInstances() or ())

    def getEngines(self):
        r'@types: -> list[aws_rds.Engine]'
        return map(self._convertToDbEngine, self._service.describeDBEngineVersions().getDBEngineVersions() or ())

    def getParameterGroups(self):
        r'@types: -> list[aws_rds.ParameterGroup]'
        return map(self._convertToParameterGroup, self._service.describeDBParameterGroups().getDBParameterGroups() or ())

    def getSecurityGroups(self):
        r'@types: -> list[aws_rds.SecurityGroup]'
        return map(self._convertToSecurityGroup, self._service.describeDBSecurityGroups().getDBSecurityGroups() or ())

    def getSnapshots(self):
        r'@types: -> list[db.Snapshot]'
        return map(self._convertToDbSnapshot, self._service.describeDBSnapshots().getDBSnapshots() or ())


def _discoverRdsTopology(framework, service, account):
    r''' Discover topology of Amazon Relational Database Service
    @types: Framework, AwsRdsService, aws.Account
    @param service:  Client for accessing AmazonRDS. All service calls made using
    this client are blocking, and will not return until the service call completes
    '''
    logger.info('RDS TOPOLOGY DISCOVERY')
    # Using RdsDiscoverer we have possibility to communication with RDS service
    discoverer = RdsDiscoverer(service)
    # Discovery starts with getting DB instances owned by current account
    # in case if this information cannot be got - discovery fails)
    logger.info("Get DB instances")
    try:
        instances = discoverer.getDbInstances()
        logger.info("Got %s instances" % len(instances))
    except (Exception, JException), e:
        logger.warnException(str(e))
        raise Exception("Failed to get DB instances")
    # Each DB instance has information about server where it resides
    # To fill-in additional information about runtime environment - we use engines
    # Engins holds general information about supported DB vendors
    logger.info("Get DB engine information")
    engines = warnException(discoverer.getEngines, [],
                            message="Failed to get DB engine versions")()
    logger.debug("Got %s engines" % len(engines))
    # To enrich information about DB instance parameter groups where only name and
    # status are available we make additional request to get all db parameters
    # in this account
    logger.info("Get parameter groups")
    parameterGroups = warnException(discoverer.getParameterGroups, [],
                                    message="Failed to get parameter groups")()
    # Grouping DB parameter groups by name for further reporting needs
    paramGroupByName = _applyMapping(aws_rds.ParameterGroup.getName, parameterGroups)
    logger.debug("Got %s parameter groups" % len(parameterGroups))
    # The same additional information for security groups.
    logger.info("Get security groups")
    securityGroups = warnException(discoverer.getSecurityGroups, [],
                                   message="Failed to get security groups")()
    # Group DB security groups by name for further reporting needs
    securityGroupByName = _applyMapping(aws_rds.SecurityGroup.getName, securityGroups)
    logger.debug("Got %s security groups" % len(securityGroups))

    logger.info("Get DB snapshots")
    # User can make snapshots of existing instances. Get information about snapshots
    snapshots = warnException(discoverer.getSnapshots, [],
                              message="Failed to get DB snapshots")()
    logger.debug("Got %s DB snapshots" % len(snapshots))
    # group snapshots by instance ID
    snapshotsByInstanceId = _groupBy(aws_rds.Snapshot.getInstanceId, snapshots)

    logger.info("RDS TOPOLOGY REPORTING")
    awsReporter = aws.Reporter(aws.Builder())
    endpointReporter = netutils.EndpointReporter(netutils.UriEndpointBuilder())
    # Report account OSH
    vector = ObjectStateHolderVector()
    accountOsh = awsReporter.reportAccount(account)
    vector.add(accountOsh)

    # more functional approach can be ...
    # _reportDbInstance = _partialFunc(reportDbInstance, _, awsReporter, accountOsh)
    # map(vector.addAll, map(_reportDbInstance, instances))

    for instance in instances:
        dbServer = instance.getServer()
        # get more information about server using engine information
        # we get engine by its name and version
        for engine in engines:
            if (engine.getName() == instance.getEngineName()
                and engine.getVersion() == dbServer.getVersion()):
                # recreate server with additional information
                dbServer = db.DatabaseServer(dbServer.address,
                                             dbServer.getPort(),
                                             dbServer.instance,
                                             dbServer.getDatabases(),
                                             dbServer.vendor,
                                             engine.getVersionDescription(),
                                             dbServer.getPlatform(),
                                             dbServer.getVersion(),
                                             engine.getDescription())
                break

        # determine builder using vendor of instance DB software
        platform = (dbServer.getPlatform()
                    or db_platform.findPlatformBySignature(dbServer.vendor))
        dbReporter = db.TopologyReporter(db_builder.getBuilderByPlatform(platform))

        rdsReporter = aws_rds.Reporter(aws_rds.Builder())
        # report instance node
        nodeOsh = rdsReporter.reportInstanceNode(instance)
        vector.add(nodeOsh)
        vector.add(rdsReporter.linkAccountWithInstanceNode(accountOsh, nodeOsh))
        # report instance (node as container)
        instanceOsh = dbReporter.reportServer(dbServer, nodeOsh)
        vector.add(instanceOsh)
        # membership link between instance node + availability zone
        zoneName = instance.getAvailabilityZoneName()
        if zoneName:
            zoneOsh = awsReporter.reportAvailabilityZoneByName(zoneName)
            vector.add(zoneOsh)
            vector.add(rdsReporter.linkZoneWithInstanceNode(zoneOsh, nodeOsh))
        # report endpoint
        endpoint = netutils.Endpoint(dbServer.getPort(),
                                     netutils.ProtocolType.TCP_PROTOCOL,
                                     dbServer.address)

        vector.add(endpointReporter.reportEndpoint(endpoint, instanceOsh))
        # reporting of parameter and security groups
        # link with parameter groups
        for group in instance.getParameterGroups():
            if paramGroupByName.has_key(group.getName()):
                group = paramGroupByName.get(group.getName())
            else:
                logger.warn("Failed to find %s for %s" % (group, instance))
            configOsh = rdsReporter.reportParameterGroupConfig(group, accountOsh)
            vector.add(configOsh)
            vector.add(rdsReporter.linkInstanceWithGroupConfig(instanceOsh, configOsh))
        # link with security groups
        for group in instance.getSecurityGroups():
            if securityGroupByName.has_key(group.getName()):
                group = securityGroupByName.get(group.getName())
            else:
                logger.warn("Failed to find %s for %s" % (group, instance))

            configOsh = rdsReporter.reportSecurityGroupConfig(group, accountOsh)
            vector.add(configOsh)
            vector.add(rdsReporter.linkInstanceWithGroupConfig(instanceOsh, configOsh))

        # report DB snapshot
        for snapshot in snapshotsByInstanceId.get(instance.getId(), ()):
            dbSnapshot = db.Snapshot(snapshot.getId(), ownerName=account.getId())
            vector.add(dbReporter.reportSnapshot(dbSnapshot, instanceOsh))
    return vector


def _discoverVolumeSnapshotById(service, id_):
    r'''@types: Ec2Service, str -> Maybe[aws_store.Ebs.Snapshot]
    @raise ValueError: No IDs specified to find corresponding snapshot
    '''
    logger.info("Discover Snapshot by ID: %s" % id_)
    snapshot = None
    try:
        snapshot = Ec2Discoverer(service).getVolumeSnapshotById(id_)
    except JException:
        logger.warnCompactException("Failed to discover snapshot")
    return snapshot


def _discoverVolumesByIds(service, ids):
    r'''@types: Ec2Service, list[str] -> list[aws_store.Ebs]
    @raise ValueError: No IDs specified to find corresponding volumes
    '''
    if not ids:
        raise ValueError("No IDs specified to find corresponding volumes")
    logger.info("Discover Volumes by IDs: %s" % ids)
    volumes = []
    try:
        volumes = Ec2Discoverer(service).getVolumesByIds(ids)
    except JException:
        logger.warnException("Failed to discover volumes")
    logger.info("Discovered %s volumes" % len(volumes))
    return volumes


def _toItself(obj):
    return obj


def _applySet(fn, items):
    r'@types: callable[A, K](A) -> K, list[A] -> list[A]'
    itemToKey = {}
    for item in items:
        itemToKey[fn(item)] = 1
    return itemToKey.keys()


def _applyMapping(fn, items):
    r'@types: callable[A, K](A) -> K, list[A] -> dict[K, list[A]]'
    itemToKey = {}
    for item in items:
        itemToKey.setdefault(fn(item), item)
    return itemToKey


def _groupBy(fn, items):
    r'@types: callable[A, K](A) -> K, list[A] -> dict[K, list[A]]'
    itemToKey = {}
    for item in items:
        itemToKey.setdefault(fn(item), []).append(item)
    return itemToKey


class MissedParam:
    pass

_ = MissedParam()


def _partialFunc(func, *args):
    r'''Creates partially applied function

    For instance we have function

    def sum(a, b, c): return a + b + c

    At some moment you know partially arguments for this function (a and c)
    fn = _partialFunc(sum, a, _, c)
    [(a + b + c), (a + b1 + c), (a + b2 + c)] = map(fn, [b, b1, b2])
    '''
    class PartialFunc:
        def __init__(self, func, args):
            self.func = func
            self.args = args

        def __call__(self, *args):
            # _, 2, 3
            args = list(args)
            finalArgs = []
            for arg in self.args:
                finalArgs += ((arg == _) and (args.pop(),) or (arg,))
            return self.func(*finalArgs)
    return PartialFunc(func, args)


def _toArrayList(items):
    values = ArrayList(len(items))
    _apply(values.add, items)
    return values


class _Connection:
    'Connection configuration and discoveryFunc performed in scope of it'
    def __init__(self, connectionFunc, discoveries):
        self.connectionFunc = connectionFunc
        self.discoveries = discoveries

    def __call__(self, framework, credentialsId):
        r'@types: Framework, str -> AwsService'
        return self.connectionFunc(framework, credentialsId)


class _Discovery:
    'Discovery configuration'
    def __init__(self, jobParameter, discoveryFunc, description):
        self.jobParameter = jobParameter
        self.discoveryFunc = discoveryFunc
        self.description = description

    def __call__(self, framework, service, account):
        r'@types: Framework, AwsService, aws.Account -> OSHV'
        return self.discoveryFunc(framework, service, account)
