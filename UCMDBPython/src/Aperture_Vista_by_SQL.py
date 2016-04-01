#coding=utf-8
##############################################
## Aperture Vista integration through JDBC
## Vinay Seshadri
## UCMDB CORD
## Apr 02, 2009
##############################################

## Local helper imports
import sys
import logger
import modeling
import errormessages

## UCMDB imports
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder

##############################################
## Globals
##############################################
SCRIPT_NAME = "Aperture_Vista_by_SQL.py"
DEBUGLEVEL = 0 ## Set between 0 and 5 (Default should be 0), higher numbers imply more log messages

##############################################
##############################################
## Helpers
##############################################
##############################################

##############################################
## Logging helper
##############################################
def debugPrint(*debugStrings):
	try:
		logLevel = 1
		logMessage = '[Aperture_Vista_by_SQL logger] '
		if type(debugStrings[0]) == type(DEBUGLEVEL):
			logLevel = debugStrings[0]
			for index in range(1, len(debugStrings)):
				logMessage = logMessage + str(debugStrings[index])
		else:
			logMessage = logMessage + ''.join(map(str, debugStrings))
		for spacer in range(logLevel):
			logMessage = '  ' + logMessage
		if DEBUGLEVEL >= logLevel:
			logger.debug(logMessage)
		#if DEBUGLEVEL > logLevel:
		#	print logMessage
	except:
		excInfo = logger.prepareJythonStackTrace('')
		logger.warn('[debugPrint] Exception: <%s>' % excInfo)
		pass

##############################################
## Concatenator
##############################################
def concatenate(*args):
	return ''.join(map(str, args))

##############################################
## Add contents of OSH dictionary to the OSHV
##############################################
def addOshFromDictToOshv(oshDict, oshVector):
	try:
		for OSH in oshDict.keys():
			oshVector.add(oshDict[OSH])
	except:
		excInfo = logger.prepareJythonStackTrace('')
		logger.debug('[' + SCRIPT_NAME + ':addOshFromDictToOshv] Exception: <%s>' % excInfo)
		pass

##############################################
## Build OSHs using a name-value pair dictionary
##############################################
def populateOSH(theOSH, attrDict):
	try:
		for attrName in attrDict.keys():
			debugPrint(4, '[populateOSH] Got attrName <%s> with value <%s>' % (attrName, attrDict[attrName]))
			if attrDict[attrName] is None or attrDict[attrName] == '':
				debugPrint(4, '[populateOSH] Got empty value for attribute <%s>' % attrName)
				continue
			else:
				theOSH.setAttribute(attrName, attrDict[attrName])
		return None
	except:
		excInfo = logger.prepareJythonStackTrace('')
		logger.debug('[' + SCRIPT_NAME + ':populateOSH] Exception: <%s>' % excInfo)
		pass

##############################################
## Build DATACENTER OSH
##############################################
def buildDatacenterOSH(datacenterName, datacenterOshDict):
	try:
		if datacenterName in datacenterOshDict.keys():
			debugPrint(3, '[buildDatacenterOSH] Already processed DATACENTER <%s>! Skipping...' % datacenterName)
		else:
			debugPrint(2, '[buildDatacenterOSH] DATACENTER <%s> found' % datacenterName)
			datacenterOSH = ObjectStateHolder('datacenter')
			populateOSH(datacenterOSH, {'name':datacenterName})
			datacenterOshDict[datacenterName] = datacenterOSH
			return datacenterOSH
	except:
		excInfo = logger.prepareJythonStackTrace('')
		logger.debug('[' + SCRIPT_NAME + ':buildDatacenterOSH] Exception: <%s>' % excInfo)
		pass


##############################################
## Build RACK OSH
##############################################
def buildRackOSH(rackName, rackAssetNumber, rackSerialNumber, rowName, gridLocation, spaceName, floorName, buildingName, rackOshDict, datacenterOshDict):
	try:
		rackDictKey = '%s ** %s ** %s ** %s ** %s ** %s ** %s ** %s' % (rackName, rackAssetNumber, rackSerialNumber, rowName, gridLocation, spaceName, floorName, buildingName)
		if rackDictKey in rackOshDict.keys():
			debugPrint(3, '[buildRackOSH] Already processed RACK <%s>! Skipping...' % rackName)
			return rackOshDict[rackDictKey]
		else:
			debugPrint(2, '[buildRackOSH] RACK <%s> found' % rackName)
			rackOSH = modeling.createCompleteHostOSH('rack', '')
			#rackOSH = modeling.createCompleteHostOSH('rack', str(hash(rackDictKey)))
			populateOSH(rackOSH, {'name':rackName, 'serial_number':rackSerialNumber, 'floor':floorName, 'space_name':spaceName, 'grid_location':gridLocation, 'row_name':rowName})
			rackOSH.setContainer(datacenterOshDict[buildingName])
			rackOshDict[rackDictKey] = rackOSH
			return rackOSH
	except:
		excInfo = logger.prepareJythonStackTrace('')
		logger.debug('[' + SCRIPT_NAME + ':buildRackOSH] Exception: <%s>' % excInfo)
		pass


##############################################
## Build PDU OSH
##############################################
def buildPduOSH(deviceName, deviceAssetNumber, deviceSerialNumber, rowName, gridLocation, spaceName, floorName, buildingName, pduOshDict, datacenterOshDict):
	try:
		pduDictKey = '%s ** %s ** %s ** %s ** %s ** %s ** %s' % (deviceName, deviceAssetNumber, deviceSerialNumber, gridLocation, spaceName, floorName, buildingName)
		if pduDictKey in pduOshDict.keys():
			debugPrint(3, '[buildPduOSH] Already processed PDU <%s>! Skipping...' % deviceName)
		else:
			debugPrint(2, '[buildPduOSH] PDU <%s> found' % deviceName)
			pduOSH = ObjectStateHolder('power_distribution_unit')
			populateOSH(pduOSH, {'name':deviceName, 'serial_number':deviceSerialNumber, 'floor':floorName, 'space_name':spaceName, 'grid_location':gridLocation, 'row_name':rowName})
			pduOSH.setContainer(datacenterOshDict[buildingName])
			pduOshDict[pduDictKey] = pduOSH
	except:
		excInfo = logger.prepareJythonStackTrace('')
		logger.debug('[' + SCRIPT_NAME + ':buildPduOSH] Exception: <%s>' % excInfo)
		pass


##############################################
## Build RPP OSH
##############################################
def buildRppOSH(deviceName, deviceAssetNumber, deviceSerialNumber, rowName, gridLocation, spaceName, floorName, buildingName, rppOshDict, datacenterOshDict):
	try:
		rppDictKey = '%s ** %s ** %s ** %s ** %s ** %s ** %s' % (deviceName, deviceAssetNumber, deviceSerialNumber, gridLocation, spaceName, floorName, buildingName)
		if rppDictKey in rppOshDict.keys():
			debugPrint(3, '[buildRppOSH] Already processed RPP <%s>! Skipping...' % deviceName)
		else:
			debugPrint(2, '[buildRppOSH] RPP <%s> found' % deviceName)
			rppOSH = ObjectStateHolder('remote_power_panel')
			populateOSH(rppOSH, {'name':deviceName, 'serial_number':deviceSerialNumber, 'floor':floorName, 'space_name':spaceName, 'grid_location':gridLocation, 'row_name':rowName})
			rppOSH.setContainer(datacenterOshDict[buildingName])
			rppOshDict[rppDictKey] = rppOSH
	except:
		excInfo = logger.prepareJythonStackTrace('')
		logger.debug('[' + SCRIPT_NAME + ':buildRppOSH] Exception: <%s>' % excInfo)
		pass


##############################################
## Build CHASSIS OSH
##############################################
def buildChassisOSH(deviceAssetClass, deviceAssetSubClass, deviceName, deviceAssetNumber, deviceSerialNumber, deviceManufacturer, deviceModel, deviceModelInfo, hostOshDict, datacenterOshDict):
	try:
		chassisOSH = None
		chassisDictKey = '%s ** %s ** %s' % (deviceName, deviceAssetNumber, deviceSerialNumber)
		## Check if this CHASSIS was already processed
		if chassisDictKey in hostOshDict.keys():
			debugPrint(3, '[buildChassisOSH] Already processed CHASSIS <%s>! Skipping...' % deviceName)
			chassisOSH = hostOshDict[chassisDictKey]
		## If not build a new OSH
		else:
			## Determine CI Type for CHASSIS
			chassisCitName = 'chassis'
			if deviceAssetSubClass and deviceAssetSubClass == 'BLADE':
				chassisCitName = 'node'
				if deviceModel.lower().find('netra') >= 0:
					chassisCitName = 'unix'
				if deviceModelInfo.lower().find('bladecenter') >= 0:
					chassisCitName = 'enclosure'
			elif deviceAssetSubClass and deviceAssetSubClass == 'PATCH PANEL':
				debugPrint(3, '[buildChassisOSH] Skipping CHASSIS <%s> because it is a patch panel' % deviceName)
				return None
			debugPrint(4, '[buildChassisOSH] Creating CHASSIS with CIT <%s>' % chassisCitName)
			## Check if serial number is unique
			if deviceSerialNumber:
				for hostDictKey in hostOshDict.keys():
					serialNumber = hostDictKey.split(' ** ')[2]
					if serialNumber and deviceSerialNumber.lower() == serialNumber.lower():
						deviceSerialNumber = None
						logger.warn('Duplicate Serial Number <%s> found on <%s> <%s>! Discarding serial number...' % (serialNumber, chassisCitName, deviceName))
						break
			## Build CHASSIS
			debugPrint(2, '[buildChassisOSH] CHASSIS <%s> found' % deviceName)
			chassisOSH = modeling.createCompleteHostOSH(chassisCitName, '')
			populateOSH(chassisOSH, {'name':deviceName, 'serial_number':deviceSerialNumber, 'discovered_model':'%s (%s)'%(deviceModel, deviceModelInfo), 'discovered_vendor':deviceManufacturer})
			if chassisCitName in ['chassis', 'bladecenter']:
				populateOSH(chassisOSH, {'chassis_model':'%s %s'%(deviceModel, deviceModelInfo), 'chassis_id':deviceAssetNumber, 'chassis_vendor':deviceManufacturer})
			if not deviceSerialNumber:
				populateOSH(chassisOSH, {'host_key':str(hash(chassisDictKey)), 'data_note':'Serial Number not available in Aperture VISTA. Duplication of this CI is possible'})
			hostOshDict[chassisDictKey] = chassisOSH
		return chassisOSH
	except:
		excInfo = logger.prepareJythonStackTrace('')
		logger.debug('[' + SCRIPT_NAME + ':buildChassisOSH] Exception: <%s>' % excInfo)
		pass


##############################################
## Build NODE OSH
##############################################
def buildNodeOSH(deviceAssetClass, deviceAssetSubClass, deviceName, deviceAssetNumber, deviceSerialNumber, deviceManufacturer, deviceModel, deviceModelInfo, hostOshDict, datacenterOshDict):
	try:
		nodeOSH = None
		nodeDictKey = '%s ** %s ** %s' % (deviceName, deviceAssetNumber, deviceSerialNumber)
		## Check if this NODE was already processed
		if nodeDictKey in hostOshDict.keys():
			debugPrint(3, '[buildNodeOSH] Already processed NODE <%s>! Skipping...' % deviceName)
			nodeOSH = hostOshDict[nodeDictKey]
		## If not, build a new OSH
		else:
			## Determine CI Type for NODE
			nodeCitName = 'host_node'
			if deviceAssetClass == 'ARRAY':
				nodeCitName = 'storagearray'
			elif deviceAssetClass == 'ROUTER':
				nodeCitName = 'router'
			elif deviceAssetClass == 'NETWORK SWITCH':
				nodeCitName = 'switch'
			if deviceManufacturer and deviceManufacturer.lower() == 'sun':
				nodeCitName = 'unix'
			debugPrint(4, '[buildNodeOSH] Creating NODE with CIT <%s>' % nodeCitName)
			## Check if serial number is unique
			if deviceSerialNumber:
				for hostDictKey in hostOshDict.keys():
					serialNumber = hostDictKey.split(' ** ')[2]
					if serialNumber and deviceSerialNumber.lower() == serialNumber.lower():
						deviceSerialNumber = None
						logger.warn('Duplicate Serial Number <%s> found on <%s> <%s>! Discarding serial number...' % (serialNumber, nodeCitName, deviceName))
						break
			##  Build NODE
			debugPrint(2, '[buildNodeOSH] NODE <%s> found' % deviceName)
			nodeOSH = modeling.createCompleteHostOSH(nodeCitName, '')
			populateOSH(nodeOSH, {'name':deviceName, 'serial_number':deviceSerialNumber, 'discovered_model':'%s (%s)'%(deviceModel, deviceModelInfo), 'discovered_vendor':deviceManufacturer})
			if not deviceSerialNumber:
				populateOSH(nodeOSH, {'host_key':str(hash(nodeDictKey)), 'data_note':'Serial Number not available in Aperture VISTA. Duplication of this CI is possible'})
			hostOshDict[nodeDictKey] = nodeOSH
		return nodeOSH
	except:
		excInfo = logger.prepareJythonStackTrace('')
		logger.debug('[' + SCRIPT_NAME + ':buildNodeOSH] Exception: <%s>' % excInfo)
		pass


##############################################
##############################################
## Get Devices
##############################################
##############################################
def getDevices(localFramework, localsqlClient, datacenterOshDict, rackOshDict, pduOshDict, rppOshDict, hostOshDict):
	try:
		resultVector = ObjectStateHolderVector()

		###########################
		## JDBC SQL stuff
		###########################
		## Run query
		deviceQuery = '''SELECT device_name, device_asset_number, device_serial_number, device_asset_class, device_asset_sub_class,
								device_manufacturer, device_model, device_model_info,
								rack_name, rack_asset_number, rack_serial_number,
								row_name, grid_location, space_name, floor, building_name,
								parent_name, parent_asset_number, parent_serial_number, parent_asset_class, parent_asset_sub_class
						FROM vista.dbo.vip_dal_dv_devices
						WHERE device_asset_class IN ('ARRAY', 'SERVER', 'CHASSIS', 'RACK', 'CABINET')
								and device_serial_number != 'TBD'
								and device_serial_number != 'NA'
								and device_serial_number != 'N/A'
								and device_serial_number != 'NEEDED'
								and device_serial_number != 'UNKNOWN'
								and device_serial_number IS NOT NULL
								and device_name != 'NOT DISPLAYED'
								and rack_name IS NOT NULL
						GROUP BY device_name, device_asset_number, device_serial_number, device_asset_class, device_asset_sub_class,
								device_manufacturer, device_model, device_model_info,
								rack_name, rack_asset_number, rack_serial_number,
								row_name, grid_location, space_name, floor, building_name,
								parent_name, parent_asset_number, parent_serial_number, parent_asset_class, parent_asset_sub_class'''
		debugPrint(3, '[getDevices] Device query is <%s>' % deviceQuery)
		deviceQueryResultSet = localsqlClient.executeQuery(deviceQuery)

		## Do we have query results?
		if deviceQueryResultSet is None:
				debugPrint(1, '[getDevices] Empty result set for device query')
				localFramework.reportWarning('Unable to get a list of devices')
				return None

		## We have query results!
		while deviceQueryResultSet.next():
			deviceName = (deviceQueryResultSet.getString(1) or ' ').strip()
			deviceAssetNumber = (deviceQueryResultSet.getString(2) or ' ').strip()
			deviceSerialNumber = (deviceQueryResultSet.getString(3) or ' ').strip()
			deviceAssetClass = (deviceQueryResultSet.getString(4) or ' ').strip()
			deviceAssetSubClass = (deviceQueryResultSet.getString(5) or ' ').strip()
			deviceManufacturer = (deviceQueryResultSet.getString(6) or ' ').strip()
			deviceModel = (deviceQueryResultSet.getString(7) or ' ').strip()
			deviceModelInfo = (deviceQueryResultSet.getString(8) or ' ').strip()
			rackName = (deviceQueryResultSet.getString(9) or ' ').strip()
			rackAssetNumber = (deviceQueryResultSet.getString(10) or ' ').strip()
			rackSerialNumber = (deviceQueryResultSet.getString(11) or ' ').strip()
			rowName = (deviceQueryResultSet.getString(12) or ' ').strip()
			gridLocation = (deviceQueryResultSet.getString(13) or ' ').strip()
			spaceName = (deviceQueryResultSet.getString(14) or ' ').strip()
			floorName = (deviceQueryResultSet.getString(15) or ' ').strip()
			buildingName = (deviceQueryResultSet.getString(16) or ' ').strip()
			parentName = (deviceQueryResultSet.getString(17) or ' ').strip()
			parentAssetNumber = (deviceQueryResultSet.getString(18) or ' ').strip()
			parentSerialNumber = (deviceQueryResultSet.getString(19) or ' ').strip()
			#parentAssetClass = (deviceQueryResultSet.getString(20) or ' ').strip()
			#parentAssetSubClass = (deviceQueryResultSet.getString(21) or ' ').strip()

			## Remove nameless items that are not modules or cards
			if not deviceName and (deviceAssetClass != 'CARD' or (deviceAssetClass == 'CARD' and (deviceAssetSubClass == 'BLADE' or deviceAssetSubClass == 'BLADE SERVER'))):
				debugPrint(4, '[getDevices] Skipping nameless device...')
				continue
			
			## Build DATACENTER OSH
			if buildingName:
				buildDatacenterOSH(buildingName, datacenterOshDict)

			## Build RACK OSH
			if deviceAssetClass in ['RACK', 'CABINET']:
				buildRackOSH(deviceName, deviceAssetNumber, deviceSerialNumber, rowName, gridLocation, spaceName, floorName, buildingName, rackOshDict, datacenterOshDict)
			## Build PDU OSH
			elif deviceAssetClass == 'PDU':
				buildPduOSH(deviceName, deviceAssetNumber, deviceSerialNumber, rowName, gridLocation, spaceName, floorName, buildingName, pduOshDict, datacenterOshDict)
			## Build RPP OSH
			elif deviceAssetClass == 'RPP':
				buildRppOSH(deviceName, deviceAssetNumber, deviceSerialNumber, rowName, gridLocation, spaceName, floorName, buildingName, rppOshDict, datacenterOshDict)
			## Build CHASSIS OSH
			elif deviceAssetClass == 'CHASSIS':
				## Build host
				chassisOSH = buildChassisOSH(deviceAssetClass, deviceAssetSubClass, deviceName, deviceAssetNumber, deviceSerialNumber, deviceManufacturer, deviceModel, deviceModelInfo, hostOshDict, datacenterOshDict)
				## Check if a the rack in which this chassis is located is known
				if chassisOSH and rackName:
					containerRackOSH = buildRackOSH(rackName, rackAssetNumber, rackSerialNumber, rowName, gridLocation, spaceName, floorName, buildingName, rackOshDict, datacenterOshDict)
					debugPrint(3, '[getDevices] Adding CONTAINMENT link between RACK <%s> and CHASSIS <%s>' % (rackName, deviceName))
					resultVector.add(modeling.createLinkOSH('containment', containerRackOSH, chassisOSH))
			## Build NODE OSH
			elif deviceAssetClass in ['ARRAY', 'SERVER', 'ROUTER', 'NETWORK SWITCH'] or (deviceAssetClass == 'CARD' and (deviceAssetSubClass == 'BLADE' or deviceAssetSubClass == 'BLADE SERVER')):
				## Build NODE
				nodeOSH = buildNodeOSH(deviceAssetClass, deviceAssetSubClass, deviceName, deviceAssetNumber, deviceSerialNumber, deviceManufacturer, deviceModel, deviceModelInfo, hostOshDict, datacenterOshDict)
				## Check if a the rack in which this host is located is known
				if nodeOSH and rackName:
					containerRackOSH = buildRackOSH(rackName, rackAssetNumber, rackSerialNumber, rowName, gridLocation, spaceName, floorName, buildingName, rackOshDict, datacenterOshDict)
					debugPrint(3, '[getDevices] Adding CONTAINMENT link between RACK <%s> and NODE <%s>' % (rackName, deviceName))
					resultVector.add(modeling.createLinkOSH('containment', containerRackOSH, nodeOSH))
				## Check if this NODE has a parent (usually a CHASSIS or ENCLOSURE)
				if nodeOSH and parentName:
					parentsNodeDictKey = '%s ** %s ** %s' % (parentName, parentAssetNumber, parentSerialNumber)
					if parentsNodeDictKey in hostOshDict.keys():
						debugPrint(3, '[getDevices] Adding DEPENDENCY link between NODE (ENCLOSURE or CHASSIS) <%s> and NODE <%s>' % (parentName, deviceName))
						resultVector.add(modeling.createLinkOSH('dependency', hostOshDict[parentsNodeDictKey], nodeOSH))

		# Add all results to the OSHV
		addOshFromDictToOshv(datacenterOshDict, resultVector)
		addOshFromDictToOshv(pduOshDict, resultVector)
		addOshFromDictToOshv(rppOshDict, resultVector)
		addOshFromDictToOshv(rackOshDict, resultVector)
		addOshFromDictToOshv(hostOshDict, resultVector)

		return resultVector
	except:
		excInfo = logger.prepareJythonStackTrace('')
		logger.debug('[' + SCRIPT_NAME + ':getDevices] Exception: <%s>' % excInfo)
		pass


##############################################
##############################################
## Get Devices
##############################################
##############################################
def getPowerRoutes(localFramework, localsqlClient, datacenterOshDict, rackOshDict, pduOshDict, rppOshDict, hostOshDict):
	try:
		resultVector = ObjectStateHolderVector()

		###########################
		## JDBC SQL stuff
		###########################
		## Build query
		powerRouteQuery = '''SELECT Downstream_Device_Name, Downstream_Device_Asset_Number, Downstream_Device_Serial_Number,
								Upstream_Device_Name, Upstream_Device_Asset_Number, Upstream_Device_Serial_Number, Upstream_Grid_Location, Upstream_Space_Name, Upstream_Floor, Upstream_Building_Name
							FROM vista.dbo.VIP_DAL_PWR_Device_Power_Sources'''
		debugPrint(3, '[getPowerRoutes] Power route query is <%s>' % powerRouteQuery)
		powerRouteQueryResultSet = localsqlClient.executeQuery(powerRouteQuery)

		## Do we have query results?
		if powerRouteQueryResultSet is None:
				debugPrint(1, '[getPowerRoutes] Empty result set for Rower Route query')
				localFramework.reportWarning('Unable to get a list of Power Routes')
				return None

		# Add all results to the OSHV
		addOshFromDictToOshv(datacenterOshDict, resultVector)

		## We have query results!
		while powerRouteQueryResultSet.next():
			deviceName = (powerRouteQueryResultSet.getString(1) or ' ').strip()
			deviceAssetNumber = (powerRouteQueryResultSet.getString(2) or ' ').strip()
			deviceSerialNumber = (powerRouteQueryResultSet.getString(3) or ' ').strip()
			pduName = (powerRouteQueryResultSet.getString(4) or ' ').strip()
			pduAssetNumber = (powerRouteQueryResultSet.getString(5) or ' ').strip()
			pduSerialNumber = (powerRouteQueryResultSet.getString(6) or ' ').strip()
			pduGridLocation = (powerRouteQueryResultSet.getString(7) or ' ').strip()
			pduSpaceName = (powerRouteQueryResultSet.getString(8) or ' ').strip()
			pduFloorName = (powerRouteQueryResultSet.getString(9) or ' ').strip()
			pduBuildingName = (powerRouteQueryResultSet.getString(10) or ' ').strip()

			## Build keys
			deviceKey = '%s ** %s ** %s' % (deviceName, deviceAssetNumber, deviceSerialNumber)
			pduKey = '%s ** %s ** %s ** %s ** %s ** %s ** %s' % (pduName, pduAssetNumber, pduSerialNumber, pduGridLocation, pduSpaceName, pduFloorName, pduBuildingName)
			## Make sure that the device is in the dictionary
			if deviceKey not in hostOshDict.keys():
				debugPrint(2, '[getPowerRoutes] HOST with key <%s> not in dictionary! Skipping...' % deviceKey)
				continue
			## Make sure that the PDU is in the dictionary
			if pduKey not in pduOshDict.keys() and pduKey not in rppOshDict.keys():
				debugPrint(2, '[getPowerRoutes] PDU/RPP with key <%s> not in dictionary! Skipping...' % pduKey)
				continue
			debugPrint(2, '[getPowerRoutes] Creating USAGE link between HOST <%s> and PDU/RPP <%s>' % (deviceKey, pduKey))
			## Add USAGE link indicating power supply to OSHV
			pduOSH = pduOshDict[pduKey] or rppOshDict[pduKey]
			isPoweredByLink = modeling.createLinkOSH('usage', hostOshDict[deviceKey], pduOSH)
			isPoweredByLink.setAttribute('name', 'Is Powered By')
			resultVector.add(isPoweredByLink)
		return resultVector
	except:
		excInfo = logger.prepareJythonStackTrace('')
		logger.debug('[' + SCRIPT_NAME + ':getPowerRoutes] Exception: <%s>' % excInfo)
		pass


##############################################
##############################################
## MAIN
##############################################
##############################################
def DiscoveryMain(Framework):
	debugPrint('[DiscoveryMain] Starting...')
	# General variables
	OSHVResult = ObjectStateHolderVector()
	protocolName = 'SQL'
	sqlClient = None

	# We need dictionaries for each OSH type since results of
	# SQL queries will contain multiple rows with the same info
	datacenterOshDict = {}	# Use building name as key
	rackOshDict = {}		# Use rack+building name as key
	pduOshDict = {}			# Use PDU+building name as key
	rppOshDict = {}			# Use RPP+building name as key
	hostOshDict = {}		# Use serial number as key

	try:
		# JDBC client
		sqlClient = Framework.createClient()

		# Discover...
		OSHVResult.addAll(getDevices(Framework, sqlClient, datacenterOshDict, rackOshDict, pduOshDict, rppOshDict, hostOshDict))
		OSHVResult.addAll(getPowerRoutes(Framework, sqlClient, datacenterOshDict, rackOshDict, pduOshDict, rppOshDict, hostOshDict))
	except Exception, ex:
		strException = str(ex.getMessage())
		errormessages.resolveAndReport(strException, protocolName, Framework)
	except:
		excInfo = str(sys.exc_info()[1])
		errormessages.resolveAndReport(excInfo, protocolName, Framework)

	# Close JDBC stuff
	debugPrint('[DiscoveryMain] Closing JDBC connections...')
	if sqlClient is not None:
		sqlClient.close()

	# Write OSHV to file - only useful for debugging 
	#===========================================================================
	# from java.io import FileWriter, BufferedWriter
	# fileName = 'c:/' + SCRIPT_NAME + '.OSHV.xml'
	# theFile = FileWriter(fileName)
	# fileBuffer = BufferedWriter(theFile)
	# fileBuffer.write(OSHVResult.toXmlString())
	# fileBuffer.flush()
	# fileBuffer.close()
	# warningMessage = 'Discovery results not sent to server; Writing them to file <%s> on the Data Flow Probe system' % fileName
	# Framework.reportWarning(warningMessage)
	# logger.warn(warningMessage)
	#===========================================================================
	## Print CIT counts from OSHV
	#===============================================================================================
	# ciTypeCounts = {} # {'CI Type':Count}
	# for ciTypeIndex in range(OSHVResult.size()):
	#	ciType = OSHVResult.get(ciTypeIndex).getObjectClass()
	#	if ciType in ciTypeCounts.keys():
	#		ciTypeCounts[ciType] = ciTypeCounts[ciType] + 1
	#	else:
	#		ciTypeCounts[ciType] = 1
	# print ciTypeCounts
	#===============================================================================================

#	return None
	return OSHVResult
