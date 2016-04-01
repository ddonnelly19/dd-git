__author__ = 'wwei3'

import re

UNIX_ERROR_CODE_PATTERN = r'ErrorCode=\[(-?\d*)\]'

INSTALL_ERROR_MAPPING = {"windows": {
	"0": "Success",
	"1601": "The Windows Installer service could not be accessed. Contact your support personnel to verify that the Windows Installer service is properly registered.",
	"1602": "User cancel installation.",
	"1603": "Fatal error during installation.",
	"1604": "Installation suspended, incomplete.",
	"1605": "This action is only valid for products that are currently installed.",
	"1606": "Feature ID not registered.",
	"1607": "Component ID not registered.",
	"1608": "Unknown property.",
	"1609": "Handle is in an invalid state.",
	"1610": "The configuration data for this product is corrupt. Contact your support personnel.",
	"1611": "Component qualifier not present.",
	"1612": "The installation source for this product is not available. Verify that the source exists and that you can access it.",
	"1613": "This installation package cannot be installed by the Windows Installer service. You must install a Windows service pack that contains a newer version of the Windows Installer service. 1614  Product is uninstalled.",
	"1615": "SQL query syntax invalid or unsupported.",
	"1616": "Record field does not exist.",
	"1618": "Another installation is already in progress. Complete that installation before proceeding with this install.",
	"1619": "This installation package could not be opened. Verify that the package exists and that you can access it, or contact the application vendor to verify that this is a valid Windows Installer package.",
	"1620": "This installation package could not be opened. Contact the application vendor to verify that this is a valid Windows Installer package.",
	"1621": "There was an error starting the Windows Installer service user interface. Contact your support personnel.",
	"1622": "Error opening installation log file. Verify that the specified log file location exists and is writable.",
	"1623": "This language of this installation package is not supported by your system.",
	"1625": "This installation is forbidden by system policy. Contact your system administrator.",
	"1626": "Function could not be executed.",
	"1627": "Function failed during execution.",
	"1628": "Invalid or unknown table specified.",
	"1629": "Data supplied is of wrong type.",
	"1630": "Data of this type is not supported.",
	"1631": "The Windows Installer service failed to start. Contact your support personnel.",
	"1632": "The temp folder is either full or inaccessible. Verify that the temp folder exists and that you can write to it.",
	"1633": "This installation package is not supported on this platform. Contact your application vendor.",
	"1634": "Component not used on this machine.",
	"1624": "Error applying transforms. Verify that the specified transform paths are valid.",
	"1635": "This patch package could not be opened. Verify that the patch package exists and that you can access it, or contact the application vendor to verify that this is a valid Windows Installer patch package.",
	"1636": "This patch package could not be opened. Contact the application vendor to verify that this is a valid Windows Installer patch package.",
	"1637": "This patch package cannot be processed by the Windows Installer service. You must install a Windows service pack that contains a newer version of the Windows Installer service.",
	"1638": "Another version of this product is already installed. Installation of this version cannot continue. To configure or remove the existing version of this product, use Add/Remove Programs on the Control Panel.",
	"1639": "Invalid command line argument. Consult the Windows Installer SDK for detailed command line help.",
	"3010": "A restart is required to complete the install. This does not include installs where the ForceReboot action is run. Note that this error will not be available until future version of the installer. ",
	"default": "Install Agent Failed",
	"success": ["0"],
	"inprogress": ['']
}, "others": {
	"0": "Success",
	"1": "general error",
	"2": "wrong parameter",
	"3": "not root user/permission denied",
	"4": "file creation error",
	"5": "wrong platform",
	"6": "install package error",
	"7": "directory missing",
	"8": "file missing",
	"9": "file not executable",
	"10": "link startup script error",
	"11": "startup script error",
	"12": "UD Agent installed already",
	"13": "system package manager error",
	"14": "run agent with non-root user error",
	"15": "The agent process is running, DDMi may be installed",
	"default": "Unknown error",
	"success": ["0"],
	"inprogress": ['-1', '']
}}

UNINSTALL_ERROR_MAPPING = {"windows": {
	"0": "Success",
	"1601": "The Windows Installer service could not be accessed. Contact your support personnel to verify that the Windows Installer service is properly registered.",
	"1602": "User cancel installation.",
	"1603": "Fatal error during installation.",
	"1604": "Installation suspended, incomplete.",
	"1605": "This action is only valid for products that are currently installed.",
	"1606": "Feature ID not registered.",
	"1607": "Component ID not registered.",
	"1608": "Unknown property.",
	"1609": "Handle is in an invalid state.",
	"1610": "The configuration data for this product is corrupt. Contact your support personnel.",
	"1611": "Component qualifier not present.",
	"1612": "The installation source for this product is not available. Verify that the source exists and that you can access it.",
	"1613": "This installation package cannot be installed by the Windows Installer service. You must install a Windows service pack that contains a newer version of the Windows Installer service. 1614  Product is uninstalled.",
	"1615": "SQL query syntax invalid or unsupported.",
	"1616": "Record field does not exist.",
	"1618": "Another installation is already in progress. Complete that installation before proceeding with this install.",
	"1619": "This installation package could not be opened. Verify that the package exists and that you can access it, or contact the application vendor to verify that this is a valid Windows Installer package.",
	"1620": "This installation package could not be opened. Contact the application vendor to verify that this is a valid Windows Installer package.",
	"1621": "There was an error starting the Windows Installer service user interface. Contact your support personnel.",
	"1622": "Error opening installation log file. Verify that the specified log file location exists and is writable.",
	"1623": "This language of this installation package is not supported by your system.",
	"1625": "This installation is forbidden by system policy. Contact your system administrator.",
	"1626": "Function could not be executed.",
	"1627": "Function failed during execution.",
	"1628": "Invalid or unknown table specified.",
	"1629": "Data supplied is of wrong type.",
	"1630": "Data of this type is not supported.",
	"1631": "The Windows Installer service failed to start. Contact your support personnel.",
	"1632": "The temp folder is either full or inaccessible. Verify that the temp folder exists and that you can write to it.",
	"1633": "This installation package is not supported on this platform. Contact your application vendor.",
	"1634": "Component not used on this machine.",
	"1624": "Error applying transforms. Verify that the specified transform paths are valid.",
	"1635": "This patch package could not be opened. Verify that the patch package exists and that you can access it, or contact the application vendor to verify that this is a valid Windows Installer patch package.",
	"1636": "This patch package could not be opened. Contact the application vendor to verify that this is a valid Windows Installer patch package.",
	"1637": "This patch package cannot be processed by the Windows Installer service. You must install a Windows service pack that contains a newer version of the Windows Installer service.",
	"1638": "Another version of this product is already installed. Installation of this version cannot continue. To configure or remove the existing version of this product, use Add/Remove Programs on the Control Panel.",
	"1639": "Invalid command line argument. Consult the Windows Installer SDK for detailed command line help.",
	"3010": "A restart is required to complete the install. This does not include installs where the ForceReboot action is run. Note that this error will not be available until future version of the installer. ",
	"default": "Uninstall Agent Failed",
	"success": ["0"],
	"inprogress": ['']
}, "others": {
	"0": "Success",
	"1": "general error",
	"2": "wrong parameter",
	"3": "not root user/permission denied",
	"4": "file creation error",
	"5": "wrong platform",
	"6": "install package error",
	"7": "directory missing",
	"8": "file missing",
	"9": "file not executable",
	"10": "link startup script error",
	"11": "startup script error",
	"12": "UD Agent installed already",
	"13": "system package manager error",
	"14": "run agent with non-root user error",
	"15": "The agent process is running, DDMi may be installed",
	"default": "Unknown error",
	"success": ["0"],
	"inprogress": ['-1', '']
}}

class _AgentErrorCode:
	def __init__(self, errorCode, platform, errorMapping):
		self.platform = platform.strip()

		processor = ErrorCodeProcessorFactory().getProcessor(platform)
		self.errorCode = processor().process(str(errorCode).strip())

		self.errorMapping = errorMapping

	def isSuccess(self):
		codeMap = {}
		if self.platform in self.errorMapping.keys():
			codeMap = self.errorMapping[self.platform]
		else:
			codeMap = self.errorMapping["others"]

		if self.errorCode in codeMap["success"]:
			return 1
		else:
			return 0

	def getMessage(self):
		if self.platform in self.errorMapping.keys():
			codeMap = self.errorMapping[self.platform]
		else:
			codeMap = self.errorMapping["others"]

		if self.errorCode in codeMap.keys():
			return codeMap[self.errorCode]
		else:
			return codeMap["default"]

	def isInProgress(self):
		if self.platform in self.errorMapping.keys():
			codeMap = self.errorMapping[self.platform]
		else:
			codeMap = self.errorMapping["others"]

		if self.errorCode in codeMap["inprogress"]:
			return 1
		else:
			return 0

class InstallErrorCode(_AgentErrorCode):
	def __init__(self, errorCode, platform):
		_AgentErrorCode.__init__(self, errorCode, platform, INSTALL_ERROR_MAPPING)


class UninstallErrorCode(_AgentErrorCode):
	def __init__(self, errorCode, platform):
		_AgentErrorCode.__init__(self, errorCode, platform, UNINSTALL_ERROR_MAPPING)

class ErrorCodeProcessorFactory:
	def __init__(self):
		self.platformToProcessor = {
			"windows": _WindowsErrorCodeProcessor,
			"default": _ErrorCodeProcessor
		}

	def getProcessor(self, platform):
		if platform in self.platformToProcessor.keys():
			return self.platformToProcessor[platform]
		else:
			return self.platformToProcessor["default"]

class _ErrorCodeProcessor:
	def process(self, errorCode):
		if errorCode:
			m = re.search(UNIX_ERROR_CODE_PATTERN, errorCode)
			if m:
				return m.group(1)
		return errorCode

class _WindowsErrorCodeProcessor(_ErrorCodeProcessor):
	def process(self, errorCode):
		matchObj = re.search(r'success or error status: (\d+).', errorCode)
		if matchObj:
			errorCode = matchObj.group(1)

		if not matchObj:
			matchObj = re.search(r'MainEngineThread is returning (\d+)', errorCode)

		if matchObj:
			errorCode = matchObj.group(1)

		if not errorCode:
			errorCode = ''
		return errorCode