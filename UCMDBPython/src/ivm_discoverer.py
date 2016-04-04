import re
import logger
import netutils
from ivm import Hypervisor, VirtualServerConfig, VirtualServer


class InsufficientPermissionsException(Exception): pass
class IncompleteObjectException(Exception): pass
class EmptyCommandOutputException(Exception): pass
class UnknownCommandException(Exception): pass

def _stripLastLoginInformation(output):
    ''' Strip information about the last successful / unsuccessful login
    @types: str -> str
    @note: If on HP-UX (11.31) DISPLAY_LAST_LOGIN in smh->security attributes configuration->system defaults is set to 1
    you?ll get the information about the last successful / unsuccessful login if a command has to run with sodo.

    output starts with lines:
    Last successful login:       Wed Sep  1 10:28:11 MESZ 2010 domain2.example.com
    Last authentication failure: Fri Aug 27 07:33:54 MESZ 2010 domain2.example.com
    ...
    '''
    loginInfoRegexp = '(Last successful login|Last authentication failure):'
    output = output and output.strip()
    if output:
        lines = output.split('\n')
        index = 0
        for line in lines:
            if line and not re.search(loginInfoRegexp, line):
                break
            index += 1
        result = '\n'.join(lines[index:])
    return result

def getCommandOutput(command, shell, timeout=0, path = "/usr/sbin/"):
    ''' Execute command and handle additional cases with privileges
    @types: str, shellutils.UnixShell, int, str -> str
    @param path: Path to command that is not in $PATH system variable
    @raise ValueError: Command is empty
    @raise ValueError: Command execution failed
    @raise InsufficientPermissionsException:
    @raise EmptyCommandOutputException: Command did not return an output
    '''
    if not command: raise ValueError, "command is empty"

    result = shell.execCmd(command, timeout)#@@CMD_PERMISION shell protocol execution
    result = result and result.strip()
    if result:
        if shell.getLastCmdReturnCode() == 0:
            return _stripLastLoginInformation(result)
        elif (re.search(r"Superuser privileges required.", result, re.I) or __isCommandUnrecognized(result)) and path and not command.find(path) == 0:
            result = getCommandOutput(path + command, shell, timeout, None)
            return _stripLastLoginInformation(result)
        else:
            if result and re.search(r"Superuser privileges required.", result, re.I):
                raise InsufficientPermissionsException, command
            elif __isCommandUnrecognized(result):
                raise UnknownCommandException, command
            raise ValueError, "Command execution failed: %s." % command
    else:
        raise EmptyCommandOutputException, "Command did not return an output: %s." % command


def gbToMb(gb):
    return long(float(gb)*1024)

def convertGbStringToMb(gbString):
    """
    This method expects string like '80.0 GB' or just '80.0' as a parameter
    """
    if gbString:
        match = re.match("(.*)\s+GB", gbString)
        if match:
            return gbToMb(match.group(1))
        else:
            try:
                return gbToMb(gbString)
            except:
                pass


__COMMAND_UNRECOGNIZED_KEYWORDS = ["is not recognized", "not found", "cannot find", "no such file", "no such command", "Running inside an HPVM guest."]
def __isCommandUnrecognized(output):
    ''' str -> bool
    '''
    lowerOutput = output.lower()
    for keyword in __COMMAND_UNRECOGNIZED_KEYWORDS:
        if lowerOutput.find(keyword) >= 0:
            return 1
    return 0

class IvmBaseDiscoverer:
    def __init__(self, shell):
        self._shell = shell

    def getCommandOutput(self, command, timeout=0, path = "/usr/sbin/"):
        return getCommandOutput(command, self._shell, timeout, path)

class IvmHypervisorDiscoverer(IvmBaseDiscoverer):
    '''
    Discovers hypervisor related data
    '''
    HPVMINFO_PATH = '/opt/hpvm/bin/hpvminfo'

    def __init__(self, shell):
        IvmBaseDiscoverer.__init__(self, shell)

    def _parseVersion(self, output):
        if not output:
            raise ValueError('Version buffer is empty')

        match = re.search(r"Version\s*(.*)", output, re.I)
        if match:
            version = match.group(1)
            return Hypervisor(version = match.group(1).strip())
        raise ValueError('Failed to parse IVM version.')

    def _getHypervisor(self):
        output = self.getCommandOutput(IvmHypervisorDiscoverer.HPVMINFO_PATH + ' -v')
        return self._parseVersion(output)

    def discover(self):
        hypervisor = self._getHypervisor()
        return hypervisor

    def isIvmSystem(self):
        logger.debug("Checking if hpvminfo is installed")
        output = self._shell.execCmd(IvmHypervisorDiscoverer.HPVMINFO_PATH)
        if output:
            if __isCommandUnrecognized(output):
                raise ValueError("Failed to determine if discovering IVM system")
        if self._shell.getLastCmdReturnCode() == 0:
            return True


class VirtualServerDiscoverer(IvmBaseDiscoverer):
    '''
        Discovers VM running 
    '''
    HPVMSTATUS_PATH = '/opt/hpvm/bin/hpvmstatus'
    DISCOVERED_OS_MAP = {'HPUX' : 'HP-UX',}
    def __init__(self, shell):
        IvmBaseDiscoverer.__init__(self, shell)

    def _buildPropertiesDict(self, buffer):
        result = {}
        for line in re.split('[\r\n]+', buffer):
            m = re.match('(.+):(.+)', line)
            if m:
                result[m.group(1).strip()] = m.group(2).strip()
        return result

    def _parseVm(self, buffer):

        properties = self._buildPropertiesDict(buffer)
        name = properties.get('Virtual Machine Name')
        vm_number = properties.get('Virtual Machine ID')
        if not (name or vm_number):
            return None

        state = properties.get('State')
        if state and state.lower() =='off':
            logger.debug('Skipping VM %s, since it is down' % name)
            return None

        uuid = properties.get('Virtual Machine UUID')
        serial_number = properties.get("VM's Serial Number")
        devs_number = properties.get('Number of devices')

        nets_number = properties.get('Number of networks')
        os_type = properties.get('Operating System')
        machine_type = properties.get('Virtual Machine Type')
        discovered_os_name = VirtualServerDiscoverer.DISCOVERED_OS_MAP.get(os_type)
        start_type = properties.get('Start type')
        vcpus_number = properties.get('Number of virtual CPUs')
        config_version = properties.get("VM's Config Version")

        memory = properties.get('Memory')
        m = re.match('([\d\.]+)\s+(MB|GB)', memory, re.I)
        if m:
            if m.group(2).lower() == 'gb':
                memory = convertGbStringToMb(m.group(1))
            else:
                memory = m.group(1)

        return VirtualServerConfig(name, vm_number, devs_number, nets_number,
                                   os_type, state, vcpus_number, uuid,
                                   machine_type, start_type, config_version, memory, serial_number, discovered_os_name)

    def _parseVms(self, output):
        if not output:
            raise ValueError('VM configuration command output appeared to be empty')

        match = re.search('\[Virtual Machines\]\s+(.+)', output, re.DOTALL)
        if match:
            elements = re.split('Virtual Machine Name', match.group(1))
            vms = [self._parseVm('Virtual Machine Name' + buffer) for buffer in elements if buffer]
            return filter(None, vms)
        raise ValueError('No information for VMs available.')

    def getVms(self):
        output = self.getCommandOutput(VirtualServerDiscoverer.HPVMSTATUS_PATH + ' -V')
        return self._parseVms(output)

    def _parseVmInterfaces(self, output):
        if output:
            rawMacs = re.findall(',0x([\da-fA-F]+):', output)
            return [mac for mac in rawMacs if netutils.isValidMac(mac)]

    def getVmInterfaces(self, vmName):
        output = self.getCommandOutput('%s %s "%s"' % (VirtualServerDiscoverer.HPVMSTATUS_PATH, '-d -P ', vmName))
        return self._parseVmInterfaces(output)

    def discover(self):
        result = []
        vms = self.getVms()
        for vm in vms:
            macs = self.getVmInterfaces(vm.name)
            vServer = VirtualServer(vm, macs)
            result.append(vServer)
        return result

def isIvmSystem(shell):
    return IvmHypervisorDiscoverer(shell).isIvmSystem()