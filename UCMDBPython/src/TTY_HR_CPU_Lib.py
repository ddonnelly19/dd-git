#coding=utf-8
from org.jdom.input import SAXBuilder
from java.io import StringReader
import modeling

import re
from appilog.common.system.types.vectors import ObjectStateHolderVector
import logger
from java.util import HashSet
from hostresource_win_wmi import CpuDiscovererBySocketDesignationProperty, CpuDiscoverer
from wmiutils import getWmiProvider


def collapseWhitespaces(input_):
    return re.sub('\s\s*', ' ', input_)


def makeCPUOSH(hostId, cid, vendor='', speed='', usage='', data_name='',
               coreNumber=0, descr='', is_virtual = False):
    hostOsh = modeling.createOshByCmdbIdString('host', hostId)
    cpuOsh = modeling.createCpuOsh(cid, hostOsh, speed, coreNumber, vendor,
                                   descr, data_name)
    if is_virtual:
        cpuOsh.setBoolAttribute('isvirtual', 1)
    return cpuOsh


class AixCpuDiscoverer:

    GET_CPUS_COMMAND = 'prtconf | grep "proc"'
    GET_CPU_INFO_COMMAND = 'lsattr -El %s%s'
    GET_SYSPLANAR_CPUS_COMMAND = 'lscfg -vpl sysplanar0 | grep PROC'

    def __init__(self, client, lang_bund):
        self.client = client
        self.processor_type_str = lang_bund.getString('aix_lsattr_str_processor_type')
        self.processor_type_reg = lang_bund.getString('aix_lsattr_reg_processor_type')
        self.lang_bund = lang_bund

    def get_cpus_from_sysplanar(self):
        '''
        Return Physical CPU available on IBM POWER Frame.
        sysplanar0 contains CPU correct info about cores count
        @types:  -> list[TTY_HR_CPU_Lib._Cpu]
        @raise ValueError: when command output cannot be parsed
        '''
        r = self.client.execCmd(self.GET_SYSPLANAR_CPUS_COMMAND)
        lines = (line.strip() for line in r.splitlines()
                 if line and line.strip())
        cpus = []
        cpu_index = 0
        for line in lines:
            m = re.match(r"(\d+).+WAY\s+PROC", line) or re.match(r"(\d*)PROCESSOR PLANAR", line)
            if m:
                cpu = _Cpu('CPU%d' % cpu_index)
                cpu.id = 'CPU%d' % cpu_index
                cpu.name = 'CPU%d' % cpu_index
                cpu.coresCount = m.group(1) and int(m.group(1)) or None
                cpus.append(cpu)
                cpu_index = cpu_index + 1
        if not cpus:
            raise ValueError('Unrecognized output')
        return cpus

    def get_cpu_cores(self, cpu_description):
        '''
        On Aix system Physical CPU is equal to CORE.
        discovery approach:
        1.POWER5 and POWER6 are always 2 cores CPU
        2.POWER7 is 4 or 6 or 8 cores CPU.
        Returns 4 Cores as default value and will try later get CPU cores
        from sysplanar0
        @types: string -> int
        '''
        CPU_VERSION_TO_CORE_NUMBER_MAP = {'PowerPC_POWER5': 2,
                                          'PowerPC_POWER6': 2,
                                          'PowerPC_POWER7': 4}
        core_count = CPU_VERSION_TO_CORE_NUMBER_MAP.get(cpu_description) or 1
        return core_count

    def get_cpu_vendor(self):
        '''
        Discovers CPU vendor
        @types: -> string
        '''
        command = 'uname -M'
        r = self.client.execCmd(command)#V@@CMD_PERMISION tty protocol execution
        if r == None:
            r = ''
        m = re.match('([\w-]+)', r)
        if (m):
            proc_vendor = m.group(1)
        else:
            proc_vendor = ''
        return proc_vendor

    def get_cpu_speed(self, cpu_name):
        '''
        Get Processor speed by cpuName
        @types: string -> string
        '''
        proc_speed = None
        proc_speedStr = ''
        command = self.GET_CPU_INFO_COMMAND % (cpu_name, ' | grep "frequency"')
        r = self.client.execCmd(command)#V@@CMD_PERMISION tty protocol execution
        if r == None:
            r = ''
        m = re.match('.*frequency\s+(\d+)\s+', r)
        if(m):
            proc_speed = long(m.group(1)) / 1000000
            proc_speedStr = str(proc_speed)
        else:
            proc_speedStr = ''
        return proc_speedStr

    def get_cpu_type(self, cpu_name):
        '''
        Get Processor type by cpuName
        @types: string -> string
        '''
        proc_desc = None
        command = self.GET_CPU_INFO_COMMAND % (
                            cpu_name, ' | grep ' + self.processor_type_str)
        r = self.client.execCmd(command)
        if r == None:
            r = ''
        m = re.search(self.processor_type_reg, r)
        if(m):
            proc_desc = m.group(1)
        else:
            proc_desc = ''
        return proc_desc

    def get_cpus(self):
        '''
        On Aix system Physical CPU is equal to CORE.
        discovery approach:
        -discovery of cores available on dstination
        -discovery CPU info: CPU vendor, type, speed
        -discovery of cores count for physical CPU

        @types: -> list[TTY_HR_CPU_Lib._Cpu]
        '''
        core_list = []
        cpu_list = []
        r = self.client.execCmd(self.GET_CPUS_COMMAND, 120000)
        if r:
            cpu_vendor = self.get_cpu_vendor()
            reg = self.lang_bund.getString('aix_prtconf_reg_proc_name')
            compiled = re.compile(reg)
            matches = compiled.findall(r)
            cpuNumber = 0
            if matches:
                core_count = self.get_cpu_cores(self.get_cpu_type(matches[0][0]))
                try:
                    core_count = self.get_cpus_from_sysplanar()[0].coresCount or core_count
                except:
                    logger.debug('Failed to get CPU cores count from sysplanar')
                for match in matches:
                    cpuName = match[0]  # proc2
                    #cpuNumber = match[1]
                    cpuId = 'CPU%s' % cpuNumber
                    cpu = _Cpu(cpuId)
                    cpu.id = cpuId
                    cpu.name = cpuId
                    cpu.vendor = cpu_vendor
                    cpu.coresCount = core_count
                    cpu.speed = self.get_cpu_speed(cpuName)
                    cpu.description = self.get_cpu_type(cpuName)
                    cpu.model = cpu.description
                    core_list.append(cpu)
                    cpuNumber = cpuNumber + 1
            if core_list:
                if core_count is None:
                    core_count = 1
                if len(core_list) >= core_count:
                    core_index = 0
                    while core_index < len(core_list):
                        cpu_list.append(core_list[core_index])
                        core_index = core_index + core_count
                else:
                    cpu_list = core_list
        return cpu_list

    def get_frame_cpus(self):
        '''
        - Discovers physical CPUs and cores number per CPU on IBM HMC Frame from current virtual box shell.
        - Discovers logical CPUs (model and speed) on current virtual box
        - It is not possible to link physical CPUs for IBM HMC Frame and logical CPUs for current virtual box
        So we assume that:
        1. IBM HMC Frame has same CPU type for all CPUs
        2. model and speed are the same for physical CPUs(on IBM HMC Frame) and logical CPUs (on current virtual box)
        This CPU info is taken from lpar or VIO server
        Returns:
        1. Physical CUPs (from IBM HMC Frame) with core count per CPU.
        2. If discovery of physical CPUs(on IBM HMC Frame) will fail then reports logical CPUs(legacy behavior). Cores per CPU in this
        case is unavailable
        @types: -> list[TTY_HR_CPU_Lib._Cpu]
        '''
        cpu_list = self.get_cpus_from_sysplanar()
        if cpu_list:
            cpu_vendor = self.get_cpu_vendor()
            cpu_speed = self.get_cpu_speed('proc0')
            cpu_description = self.get_cpu_type('proc0')
            for cpu in cpu_list:
                cpu.vendor = cpu_vendor
                cpu.speed = cpu_speed
                cpu.description = cpu_description
                cpu.model = cpu_description
        if not cpu_list:
            cpu_list = self.get_cpus()
        return cpu_list


class VioCpuDiscoverer(AixCpuDiscoverer):
    GET_CPUS_COMMAND = 'prtconf | grep "proc"'
    GET_CPU_INFO_COMMAND = 'lsdev -dev %s -attr%s'
    GET_SYSPLANAR_CPUS_COMMAND = 'lsdev -dev sysplanar0 -vpd | grep PROC'


def disAIX(host_obj, client, Framework, langBund, host_is_virtual = False):
    myVec = ObjectStateHolderVector()
    aix_cpu_discoverer = AixCpuDiscoverer(client, langBund)
    cpu_list = aix_cpu_discoverer.get_cpus()
    for cpu in cpu_list:
        myVec.add(makeCPUOSH(host_obj, cpu.id, cpu.vendor, cpu.speed, '',
                             cpu.description, cpu.coresCount, is_virtual=host_is_virtual))
    return myVec


def disFreeBSD(host_obj, client, Framework, langBund=None, host_is_virtual = False):
    myVec = ObjectStateHolderVector()

    cpuDescription = None
    cpuCount = 0
    cpuSpeed = None
    vendor = ''

    result = client.execCmd('sysctl hw.model hw.ncpu hw.clockrate')#V@@CMD_PERMISION tty protocol execution
    if result:
        regexStr = 'hw\.model: (.*?)\s*\nhw\.ncpu: (\d+)\s*\nhw\.clockrate: (\d+)'
        matcher = re.search(regexStr, result)
        if matcher:
            cpuDescription = collapseWhitespaces(matcher.group(1))
            cpuCount = int(matcher.group(2))
            cpuSpeed = matcher.group(3)

            if re.search('Intel', cpuDescription):
                vendor = 'Intel'

    if cpuCount == 0:
        result = client.execCmd('dmesg | grep -A 1 "CPU:"')#V@@CMD_PERMISION tty protocol execution
        if result:
            regexStr = 'CPU:\s*([^\n]*)\((\d+)\.\d+-MHz.*?\)\s*?\n.*?Origin\s*?=\s*?"(.*?)\"'
            matcher = re.search(regexStr, result)
            if matcher:
                cpuDescription = collapseWhitespaces(matcher.group(1))
                cpuSpeed = matcher.group(2)
                vendor = matcher.group(3)

                cpuCount = 1
                cpuCountResult = client.execCmd('dmesg | grep "cpu\|Multiprocessor"')#V@@CMD_PERMISION tty protocol execution
                if cpuCountResult:
                    cpuCountMatcher = re.search("Multiprocessor (System Detected|motherboard): (\d+) CPUs", cpuCountResult)
                    if cpuCountMatcher:
                        cpuCount = int(cpuCountMatcher.group(2))
                    else:
                        cpuEntries = re.findall("(?i)cpu\d+ \(\w+?\):\s+?APIC ID:\s+?\d+", cpuCountResult)
                        if cpuEntries:
                            #filter out duplicates from multiple sessions
                            set_ = HashSet()
                            for entry in cpuEntries:
                                set_.add(entry)
                            cpuCount = set_.size()

    if cpuCount > 0:
        for i in range(cpuCount):
            cid = 'CPU' + str(i)
            myVec.add(makeCPUOSH(host_obj, cid, vendor, cpuSpeed, '', cpuDescription, is_virtual=host_is_virtual))

    return myVec


def disVMKernel(host_obj, client, Framework, langBund=None, host_is_virtual = False):
    resVec = ObjectStateHolderVector()

    xml = client.execCmd('esxcfg-info -F xml -w | sed -n \'/<cpu-info>/,/<\/cpu-info>/p\'')
    builder = SAXBuilder(0)
    document = builder.build(StringReader(xml))
    rootElement = document.getRootElement()
    cpu_value_items = rootElement.getChildren('value')

    cpuModel = ''
    cpuCount = 1
    for cpu_item in cpu_value_items:
        if cpu_item.getAttributeValue('name') == 'num-packages':
            cpuCount = int(cpu_item.getText())
        elif cpu_item.getAttributeValue('name') == 'num-cores':
            numCores = int(cpu_item.getText())
        elif cpu_item.getAttributeValue('name') == 'cpu-model-name':
            cpuModel = cpu_item.getText()

    cpu_packages = rootElement.getChild('cpupackages')

    if cpu_packages:
        #For ESXi 4.0
        cpu_packages = cpu_packages.getChildren('cpupackage')
        for cpu_package in cpu_packages:
            cpuId = ''
            coresPerCPU = ''
            cpuVendor = ''
            cpuSpeed = ''

            cpu_package_values = cpu_package.getChildren('value')
            for value in cpu_package_values:
                if value.getAttributeValue('name') == 'num-cores':
                    coresPerCPU = int(value.getText())
                elif value.getAttributeValue('name') == 'id':
                    cpuId = 'CPU' + value.getText()

            cpu_impl_values = cpu_package.getChild('cpu-cores').getChild('cpuimpl').getChildren('value')
            for value in cpu_impl_values:
                if value.getAttributeValue('name') == 'name':
                    cpuVendor = value.getText()
                elif value.getAttributeValue('name') == 'cpu-speed':
                    cpuSpeed = value.getText()
                    cpuSpeed = cpuSpeed and cpuSpeed.isdigit() and (int(cpuSpeed) / 1000000) or cpuSpeed
            resVec.add(makeCPUOSH(host_obj, cpuId, cpuVendor, cpuSpeed, '', cpuModel, coresPerCPU))

    else:
        #For ESX 3.5
        coresPerCPU = numCores / cpuCount
        cpus = rootElement.getChild('cpus')
        for cpuId in range(cpuCount):
            cpuVendor = ''
            cpuSpeed = ''
            cpuIdStr = 'CPU' + str(cpuId)

            cpu_impl_values = cpus.getChildren('cpuimpl')[cpuId * coresPerCPU].getChildren('value')
            for value in cpu_impl_values:
                if value.getAttributeValue('name') == 'name':
                    cpuVendor = value.getText()
                elif value.getAttributeValue('name') == 'cpu-speed':
                    cpuSpeed = value.getText()
                    cpuSpeed = cpuSpeed and cpuSpeed.isdigit() and (int(cpuSpeed) / 1000000) or cpuSpeed
            resVec.add(makeCPUOSH(host_obj, cpuIdStr, cpuVendor, cpuSpeed, '', cpuModel, coresPerCPU))

    return resVec


def _parseCpuinfo(buffer):
    'str -> iterable(_Cpu)'
    idToCpu = {}
    idToCoreIds = {}
    #split on blocks per processor entry
    logger.info('Start parsing /proc/cpuinfo content')
    #hack for IBM/S390 platform
    #since nothing except vendor and number of processors can be found from the buffer
    if re.search('vendor_id\s+:\s+IBM/S390', buffer):
        vendorMatch = re.search('vendor_id\s+:\s+(.*)\s', buffer)
        cpuNumberMatch = re.search('#\s*processors\s+:\s+(\d+)', buffer)
        cpuList = []
        if cpuNumberMatch and vendorMatch:
            for cpuId in xrange(int(cpuNumberMatch.group(1))):
                cpu = _Cpu(str(cpuId))
                cpu.id = cpuId
                cpu.vendor = vendorMatch.group(1)
                cpu.coresCount = 1
                cpuList.append(cpu)
        return cpuList

    blocks = re.split('processor\s+:', buffer)
    for block in blocks:
        if not block.strip():
            continue
        lines = block.split('\n')
        number = lines[0].strip()
        line = None
        try:
            cpu = _Cpu(number)
            for line in lines[1:]:
                if not line:
                    continue
                # split(':) is not used
                # because value part may contain semicolon too
                idx = line.find(':')
                key, value = line[:idx].strip(), line[idx + 1:].strip()
                if key == 'physical id':
                    cpu.id = value
                elif key == 'cpu cores':
                    cpu.coresCount = value and int(value)
                elif key == 'vendor_id':
                    cpu.vendor = value
                elif key == 'model name':
                    #remove big spaces between words
                    cpu.model = collapseWhitespaces(value)
                    if not cpu.coresCount:
                        matcher = re.search('\s*(\w+)\-Core', line)
                        if matcher:
                            coreStr = matcher.group(1).strip()
                            if coreStr.upper() == 'QUAD':
                                cpu.coresCount = 4
                            elif coreStr.upper() == 'DUAL':
                                cpu.coresCount = 2
                elif key == 'cpu MHz':
                    cpu.speed = value and float(value)
                elif key == 'core id':
                    cpu.coreId = value
            #case when "cpu cores" data missed
            if not cpu.coresCount:
                if cpu.coreId:
                    coreIds = idToCoreIds.get(cpu.id)
                    if not coreIds or cpu.coreId not in coreIds:
                        idToCoreIds.setdefault(cpu.id, []).append(cpu.coreId)
                else:
                    #Linux OS does not show "cpu cores" & "core id" when CPU has 1 Core
                    cpu.coresCount = 1
            if not cpu.id:
                cpu.id = int(cpu.idStr)
            idToCpu.setdefault(cpu.id, cpu)
        except:
            logger.warnException('Unexpected processor information format in line "%s"' % line)
    #align CPU core information
    for id_, coreIds in idToCoreIds.items():
        idToCpu[id_].coresCount = len(coreIds)
    return idToCpu.values()


def disLinux(hostId, shell, Framework, langBund=None, host_is_virtual = False):
    '''str, shellutils.Shell, Framework, bundle -> ObjectStateHolderVector
    @raise Exception: if /proc/cpuinfo reading failed
    @command: cat /proc/cpuinfo'''

    myVec = ObjectStateHolderVector()
    buffer = shell.safecat('/proc/cpuinfo')
    if not buffer.strip():
        logger.warn("Failed getting information about CPU by parsing /proc/cpuinfo")
        return myVec
    cpus = _parseCpuinfo(buffer)
    for cpu in cpus:
        cpuId = 'CPU%s' % cpu.id
        myVec.add(makeCPUOSH(hostId, cpuId, cpu.vendor, cpu.speed, '',
                             cpu.model, cpu.coresCount, is_virtual=host_is_virtual))
    return myVec


class _Cpu:
    def __init__(self, idStr):
        'str -> _Cpu'
        self.idStr = idStr
        self.id = None
        self.name = None
        self.speed = None  # float, in MHz
        self.family = None
        self.model = None
        self.vendor = None
        self.coresCount = None
        self.description = None
        self.coreId = None

    def __eq__(self, other):
        return other and isinstance(other, _Cpu) and self.idStr == other.idStr

    def __ne__(self, other):
        return not self == other

    def __str__(self):
        return "CPU: " + str(self.__dict__)


#    PA 8900 CPU Module  3.2
def _parsePAModels(output):
    'str -> list'
    models = []
    reg = '\s*(PA\s*\-?\s*\d\d\d\d\s*(LC)?)\s*'
    compiled = re.compile(reg)
    for line in output.split('\n'):
        matches = compiled.match(line)
        if matches:
            models.append(matches.group(0).strip())
    return models


def _normalizePAModel(model):
    '''str - > str
    @raise ValueError: if model None or empty
    '''
    if not model:
        raise ValueError('Model value should not be None or empty')
    return re.sub('\s|\-', '', model)


def _getMachinfoNumberOfCpus(output):
    'str -> str or None'
    matchObj = re.search('Number of CPUs\s*=\s*(\d+)', output)
    return matchObj and matchObj.group(1)


def _getMachinfoClockSpeed(output):
    'str -> str or None'
    matchObj = re.search('Clock speed\s*=\s*(\d+)\s+MHz', output)
    return matchObj and matchObj.group(1)


def _getMachinfoVendorInformation(output):
    'str -> str or None'
    matchObj = re.search('vendor information =\s*\"(.*)\"', output)
    return matchObj and matchObj.group(1)


def _getMachinfoProcessorFamily(output):
    'str -> str or None'
    matchObj = re.search('family:\s*(\d+\s+.*)', output)
    return matchObj and matchObj.group(1)


def _getMachinfoProcessorModel(output):
    'str -> str or None'
    matchObj = re.search('model:\s*(\d+\s+.*)', output)
    return matchObj and matchObj.group(1)

def _getMachinfoLogicalCpusCount(output):
    'str -> int'
    logicalCpusCount = 0
    matchObj = re.search('(?:\d+)\s+logical\s+processors\s+\((\d+)\s+per\s+socket\)', output, re.I)
    if matchObj:
        logicalCpusCount = int(matchObj.group(1))
    logger.debug('logicalCpusCount:%s' % logicalCpusCount)
    return logicalCpusCount

def _getMachinfoCpuCoresCount(output):
    'str -> int'
    #Some Itanium processors processors are available only with a certain number of cores.
    ITANIUM_CPU_CORE_NUMBERS ={'9310': 2,
                               '9320': 4,
                               '9330': 4,
                               '9340': 4,
                               '9350': 4,
                               '9520': 4,
                               '9540': 8,
                               '9550': 4,
                               '9560': 8,
                               }
    coresPerCpu = 0
    matchObj = re.search("Cores\s+per\s+socket\s+=\s+(\d+)", output, re.I) or re.search('\s*(\d)\scores?.*?per\ssocket', output, re.I)
    if matchObj:
        coresPerCpu = int(matchObj.group(1).strip())
    if not coresPerCpu:
        isItaniumCPU = None
        isItaniumCPU = re.search("itanium.*processor\s(\d{4})", output, re.I)
        if isItaniumCPU:
            coresPerCpu = ITANIUM_CPU_CORE_NUMBERS.get(isItaniumCPU.group(1).strip())
        if not coresPerCpu:
            coreFamilyInfoBuf = re.search("amily:?\s+(\d+)", output)
            if coreFamilyInfoBuf:
                coreFamilyInfo = int(coreFamilyInfoBuf.group(1).strip())
                if coreFamilyInfo == 32:
                    coresPerCpu = 2
                elif coreFamilyInfo == 31:
                    coresPerCpu = 1
    return coresPerCpu

def _parseMachinfoNoBusSpeed(output):
    '''str -> iterable(_Cpu)
    @commandOutput:
   CPU info
   Number of CPUs = 4
   Clock speed    = 1100 MHz
   vendor information =       "GenuineIntel"
      processor family: 532 pa-2.0
      processor model:  20 PA8900
    '''
    cpus = []
    cpuCount = _getMachinfoNumberOfCpus(output)
    if cpuCount and cpuCount.isdigit():
        cpuCount = int(cpuCount)
        clockSpeed = _getMachinfoClockSpeed(output)
        try:
            clockSpeed = float(clockSpeed)
        except:
            logger.warn("Failed to obtain CPU speed from this value: %s" % clockSpeed)

        family = _getMachinfoProcessorFamily(output)
        family = family and family.strip()

        model = _getMachinfoProcessorModel(output)
        model = model and model.strip()

        vendor = _getMachinfoVendorInformation(output)
        vendor = vendor and vendor.strip()

        for i in range(cpuCount):
            cpu = _Cpu('CPU' + str(i))
            cpu.speed = clockSpeed
            cpu.model = model
            cpu.family = family
            cpu.vendor = vendor
            cpus.append(cpu)
    return cpus


def getCpusFromStm(client):
    socketToCpus = {}
    cpusInfo = client.execCmd('echo "sc product cpu;il" | /usr/sbin/cstm | grep \'CPU Number\'')
    if client.getLastCmdReturnCode() == 0:
        reg = r'CPU\s+Number:\s+(\d+)\s*CPU\s+Slot\s+Number:\s+(\d+)'
        for line in cpusInfo.split('\n'):
            foundSoket = re.match(reg, line)
            if foundSoket:
                cpu = foundSoket.group(1).strip()
                socket = foundSoket.group(2).strip()
                cpus = socketToCpus.get(socket) or []
                cpus.append(cpu)
                socketToCpus[socket] = cpus
    if not socketToCpus:
        cpus = []
        cpusInfo = client.execCmd('echo "sc product cpu;il" | /usr/sbin/cstm | grep \'Processor Number\'')
        if client.getLastCmdReturnCode() == 0:
            reg = r'Processor\s+Number:\s+(\d+)'
            for line in cpusInfo.split('\n'):
                foundCpu = re.match(reg, line)
                if foundCpu:
                    cpus.append(foundCpu.group(1).strip())
            if cpus:
                cpusInfo = client.execCmd('echo "sc product cpu;il" | /usr/sbin/cstm | grep \'Slot Number\'')
                if client.getLastCmdReturnCode() == 0:
                    reg = r'^Slot\s+Number:\s+(\d+)'
                    for line in cpusInfo.split('\n'):
                        foundSoket = re.match(reg, line)
                        if foundSoket:
                            coresCount = socketToCpus.get(foundSoket.group(1).strip()) or 0
                            coresCount = coresCount + 1
                            socketToCpus[foundSoket.group(1).strip()] = coresCount
                    if socketToCpus:
                        totalCoresCount = 0
                        for socket in socketToCpus.keys():
                            coresCount = socketToCpus.get(socket)
                            totalCoresCount = totalCoresCount + coresCount
                        if totalCoresCount == len(cpus):
                            for socket in socketToCpus.keys():
                                coresCount = socketToCpus.get(socket) 
                                cpusInSocket = []
                                for cpu in cpus[:coresCount]:
                                    cpusInSocket.append(cpu)
                                    socketToCpus[socket] = cpusInSocket
                                cpus = cpus[coresCount+1:]

    return socketToCpus

def gethyperThreadingStatus(client):
    'client -> bool'
    hyperThreadingStatus = None
    setbotOutput = client.execCmd('setboot -v')
    reg = r'Hyperthreading\s*:\s*(\w+)'
    if client.getLastCmdReturnCode() == 0:
        hyperThreadingStatus = 0
        for line in setbotOutput.split('\n'):
            foundHyperThreadingStatus = re.search(reg, line, re.I)
            if foundHyperThreadingStatus:
                hyperThreadingStatusStr = foundHyperThreadingStatus.group(1).lower()
                if hyperThreadingStatusStr == 'on':
                    hyperThreadingStatus = 1
    return hyperThreadingStatus

DEFAULT_PA_VENDOR = 'Hewlett Packard'


def disHPUX(host_obj, client, Framework=None, langBund=None, host_is_virtual = False):
    # Getting the CPU speed
    # command : /usr/bin/echo itick_per_usec/D | /usr/bin/adb /stand/vmunix /dev/kmem | /usr/bin/tail -n 1
    # res       : itick_per_usec: 650

    myVec = ObjectStateHolderVector()

    newAppr = 0
    #Check if machinfo exists in default location
    machinfoExist = client.execCmd('ls /usr/contrib/bin/machinfo')
    if machinfoExist and machinfoExist.strip() == '/usr/contrib/bin/machinfo':
        newAppr = 1

    if newAppr == 0:
        #Discovering vendor and model name
        fruInformation = client.execCmd('echo "sc product cpu;il" | /usr/sbin/cstm | grep \'CPU Module\'')#V@@CMD_PERMISION tty protocol execution
        cpuModels = _parsePAModels(fruInformation)
        vendor = DEFAULT_PA_VENDOR
        soketToCpus = getCpusFromStm(client) or {}
        cpuSpeedRes = client.execCmd('/usr/bin/echo itick_per_usec/D | /usr/bin/adb /stand/vmunix /dev/kmem | /usr/bin/tail -n 1')#V@@CMD_PERMISION tty protocol execution
        if cpuSpeedRes == None:
            cpuSpeedRes = ''

        compiled = re.compile('itick_per_usec\:\s(\d+)')
        matches = compiled.findall(cpuSpeedRes)
        logger.debug('soketToCpus %s' % soketToCpus)
        if soketToCpus:
            coresCount = 0
            for cpu_index in soketToCpus.keys():
                if coresCount < len(soketToCpus.get(cpu_index)):
                    #Not all cores can be active
                    coresCount = len(soketToCpus.get(cpu_index))
            i = 0
            speed = matches[i]
            for cpu_index in soketToCpus.keys():
                cid = 'CPU' + str(i)
                cpuModel = ''
                if i in range(len(cpuModels)) and cpuModels[i]:
                    cpuModel = _normalizePAModel(cpuModels[i])
                else:
                    logger.warn('Cpu model not found for cpu %s' % cid)
                #if will needed to report only active cores
                #coresCount = len(soketToCpus.get(cpu_index))
                myVec.add(makeCPUOSH(host_obj, cid, vendor, speed, '', cpuModel, coresCount, is_virtual=host_is_virtual) )
                i = i + 1
                logger.debug('cores count %s' % coresCount)
        else:
            num_cpus = len(matches)
            for i in range(num_cpus):
                cid = 'CPU' + str(i)
                cpuModel = ''
                if i in range(len(cpuModels)) and cpuModels[i]:
                    cpuModel = _normalizePAModel(cpuModels[i])
                else:
                    logger.warn('Cpu model not found for cpu %s' % cid)
                speed = matches[i]
                myVec.add( makeCPUOSH(host_obj, cid, vendor, speed, '', cpuModel, is_virtual=host_is_virtual) )

    else:
#        CPU info:
#          4 Intel(R) Itanium 2 processors (1.6 GHz, 6 MB)
#          400 MT/s bus, CPU version A2
#
#          Vendor identification:        GenuineIntel
#          Processor version info:       0x000000001f020204
#                  Family 31, model 2, stepping 2
#          Processor capabilities:       0x0000000000000001
#                  Implements long branch
#          Bus features supported:       0xbdf0000060000000
#          Bus features enabled:         0x0000000040000000
#                  Bus Lock Signal masked
#          L1 Instruction cache:      16 KB, 4-way
#          L1 Data cache:             16 KB, 4-way
#          L2 Unified cache:         256 KB, 8-way
#          L3 Unified cache:           6 MB, 12-way

        full_cpuInfo = client.execCmd('/usr/contrib/bin/machinfo -v')
        if full_cpuInfo == None:
            return myVec
        ver = 0
        m = re.match(r".*PA-RISC\s+(\d+)\s+processor.*?(\d+)\s+MHz.*(\d+)\s+cores.*processor count:\s+(\d+)", full_cpuInfo, re.DOTALL)
        if m:
            numberOfCpus = int(m.group(4))
            coresPerCpu = m.group(3)
            speed = m.group(2)
            model = m.group(1)

            for i in xrange(numberOfCpus):
                cpuId = "CPU%d" % i;
                myVec.add(makeCPUOSH(host_obj, cpuId, DEFAULT_PA_VENDOR, str(speed), '', "PA-RISC %s" % model, coresPerCpu, is_virtual=host_is_virtual))
            return myVec
        m = re.match(r".*PA-RISC\s+(\d+)\s+processor.*?(\d+\.\d+)\s+GHz.*(\d+)\s+cores.*?Active processor count:\s+(\d+)\s+sockets", full_cpuInfo, re.DOTALL)
        if m:
            coresPerCpu = int(m.group(3))
            numberOfCpus = int(m.group(4))

            speed = int(float(m.group(2)) * 1000)
            model = m.group(1)

            for i in xrange(numberOfCpus):
                cpuId = "CPU%d" % i;
                myVec.add(makeCPUOSH(host_obj, cpuId, DEFAULT_PA_VENDOR, str(speed), '', "PA-RISC %s" % model, coresPerCpu, is_virtual=host_is_virtual))

            return myVec
        if re.search('identification', full_cpuInfo):
            if re.search("Active\s+processor\s+count:\r?\n\s*(\d+)", full_cpuInfo):
                compiled = re.compile('\s*CPU info\s*:\s*\r?\n\s*(.*?)\r?\n\s*(.*?)\r?\n\s*(.*?)\r?\n.*?Active processor count:\r?\n.*?(\d+).*?\r?\n.*?(?:(\d+)\s+per\s+socket\))?\r?\n.*?Vendor\s*identification\s*:\s*([\w-]+)\r?\n.*?Processor\s*version\s*info.*?\r?\n\s*(.*?)\r?\n', re.S)
                ver = 2
            else:
                compiled = re.compile('''\s*CPU info\s*:\s*\n'''
                                      '''\s*(\d+)\s*(.*?)\r?\n'''
                                      '''\s*(.*?)\r?\n'''
                                      '''.*?Vendor\s*identification\s*:\s*([\w-]+)\r?\n'''
                                      '''.*?Processor\s*version\s*info.*?\n'''
                                      '''\s*(.*?)\r?\n''', re.S)
        elif re.search('family', full_cpuInfo):
            if re.search('Bus speed', full_cpuInfo):
                compiled = re.compile('\s*CPU info\s*:\s*.*?(\d+).*?Clock speed = (.*MHz)\r\n\s*?Bus speed\s*= (.*MT/s)\r\n\s+.*vendor information =\s*\"?(.*)\".*\r\n\s+processor family:\s*\d+\s+(.*?)\r\n', re.S)
                ver = 1
            else:
                #Hadling case when no bus info provided and "-v" invalid option(-v option is supported only since HP-UX 11i v3)
                cpus = _parseMachinfoNoBusSpeed(full_cpuInfo)
                if cpus:
                    for cpu in cpus:
                        name = '%s %s' % (cpu.family, cpu.model)
                        cpuOsh = makeCPUOSH(host_obj, cpu.idStr, speed = str(cpu.speed), data_name = name, is_virtual=host_is_virtual)
                        myVec.add(cpuOsh)
                return myVec
        else:
            compiled = re.compile('\s*CPU info\s*:\s*.*?(\d+)\r\n\s*?Clock speed = (.*MHz)\r\n\s*?Bus speed\s*= (.*MT/s)\r\n\s+.*vendor information =\s*\"?(.*?)\"+\r\n?', re.S)
            ver = 1
        matches = compiled.findall(full_cpuInfo)
        res = len(matches)

        if res == 0:
            logger.warn("Cannot detect CPU on this OS version.")
            return myVec

        coresPerCpu = _getMachinfoCpuCoresCount(full_cpuInfo)
        if not coresPerCpu:
            try:
                soketToCpus = getCpusFromStm(client) or {}
            except:
                logger.debugException('Failed to get CPU info from Stm')
            else:
                coresCount = 0
                for soket_index in soketToCpus.keys():
                    if coresCount < len(soketToCpus.get(soket_index)):
                        coresCount = len(soketToCpus.get(soket_index))
                coresPerCpu = coresCount
        if not coresPerCpu:
            logicalCpusPerSocket = _getMachinfoLogicalCpusCount(full_cpuInfo)
            if logicalCpusPerSocket:
                try:
                    hyperThreading = gethyperThreadingStatus(client)
                except:
                    logger.debugException('Failed to get hyper threading status from setboot')
                else:
                    if hyperThreading == 0:
                        coresPerCpu = logicalCpusPerSocket
                    elif hyperThreading == 1:
                        coresPerCpu = logicalCpusPerSocket/2

        enabledSockets = None
        enabledSocketsMatch = re.search("Number\s+of\s+enabled\s+sockets\s*=\s*(\d+)", full_cpuInfo)
        if enabledSocketsMatch:
            enabledSockets = int(enabledSocketsMatch.group(1).strip())

        cpuVendor = None

        for match in matches:
            if enabledSockets:
                num_cpus = enabledSockets
            elif ver == 2:
                num_cpus = int(match[3])
            else:
                num_cpus = int(match[0])
            if ver == 1:
                if (not enabledSockets) and coresPerCpu and num_cpus > 1:
                    num_cpus = int(num_cpus / coresPerCpu)
                if len(match) == 5:
                    cpuName = match[4] + " " + match[1] + " " + match[2]
                else:
                    cpuName = match[3] + " " + match[1] + " " + match[2]
                    cpuVendor = match[3]
                speed = "(" + str(match[1])
            elif ver == 2:
                cpuName = match[0].strip() + match[2].strip()
                speed = match[0]
                cpuVendor = match[5]
            else:
                cpuName = match[1].strip() + match[2].strip()
                cpuVendor = match[3]
                speed = match[1]
            speedMatch = re.match('.*\((\d+\.\d+)\s*GHz', speed)
            if speedMatch:
                cpuSpeed = int(float(speedMatch.group(1)) * 1000)
            else:
                speedMatch = re.match('.*\((\d+\.*\d*)\s*MHz', speed)
                cpuSpeed = int(float(speedMatch.group(1)))
            for i in xrange(num_cpus):
                cpuId = 'CPU' + str(i)
                myVec.add(makeCPUOSH(host_obj, cpuId, cpuVendor,
                                     str(cpuSpeed), '', cpuName, coresPerCpu, is_virtual=host_is_virtual))
    return myVec


def getSolarisZoneName(client):
    zonename = None
    try:
        output = client.execCmd("/usr/bin/zonename")
        if client.getLastCmdReturnCode() != 0:
            output = None
        output = output and output.strip()
        zonename = output or None
    except:
        logger.debug("Failed getting zone name via 'zonename'")

    if not zonename:
        output = None
        try:
            output = client.execCmd("ps -o zone")
            if client.getLastCmdReturnCode() != 0:
                output = None
            output = output and output.strip()
        except:
            logger.debug("Failed getting zone name via 'ps'")
        if output:
            lines = output.split('\n')
            lines = [line.strip() for line in lines if line]
            lines = lines[1:]
            if lines:
                zonename = lines[0]

    return zonename


def expandCpuRanges(rangeStr):
    cpuIds = {}
    if rangeStr:
        elements = []
        if re.search(",", rangeStr):
            elements = re.split(r",\s*", rangeStr)
        else:
            elements = re.split(r"\s+", rangeStr)

        elements = [e.strip() for e in elements if e and e.strip()]

        for element in elements:
            matcher = re.match(r"(\d+)\s*-\s*(\d+)", element)
            if matcher:
                start = int(matcher.group(1))
                end = int(matcher.group(2))
                for i in range(start, end + 1):
                    cpuIds[i] = None
                continue
            matcher = re.match(r"\d+$", element)
            if matcher:
                id_ = int(element)
                cpuIds[id_] = None
            else:
                raise ValueError("invalid element in CPU range: " % element)
    return cpuIds


def _parsePsrinfoForSolaris10(output, vcpuByIds={}):
    results = re.split(r"The physical processor has (\d+) virtual processors? \(([\d\s\-,]+?)\)", output)
    if not results or len(results) < 4:
        raise ValueError("Failed getting CPU information via 'psrinfo', "
                         "unrecognized output")

    results = results[1:]

    cpuByIds = {}
    counter = 0
    for i in range(0, len(results), 3):
#        vcpuCount = results[i]
        vcpuRanges = results[i + 1]
        cpuStr = results[i + 2]
        cpuStr = cpuStr and cpuStr.strip()

        cpuLines = cpuStr.split('\n')
        implementation = cpuStr
        brand = None
        if cpuLines and len(cpuLines) > 1:
            implementation = cpuLines[0] and cpuLines[0].strip()
            brand = cpuLines[1] and cpuLines[1].strip()

        if not brand and implementation:
            brand = implementation
            matcher = re.match(r"(\S+)\s+\(", implementation)
            if matcher:
                brand = matcher.group(1)

        speed = None
        matcher = re.search(r"clock\s+(\d+)\s+MHz", cpuStr)
        if matcher:
            speed = int(matcher.group(1))

        cpuType = None
        vcpuIds = expandCpuRanges(vcpuRanges)
        anyVcpuId = None
        if vcpuIds is not None and len(vcpuIds.keys()) > 0:
            anyVcpuId = vcpuIds.keys()[0]
        if vcpuByIds and anyVcpuId is not None:
            vcpu = vcpuByIds.get(anyVcpuId)
            if vcpu is not None:
                if not speed:
                    speed = vcpu.speed
                cpuType = vcpu.name

        vendor = None
        if not vendor and cpuType == 'sparcv9':
            vendor = "Sun_Microsystems"

        if not vendor:
            if re.search(r"Intel", cpuStr, re.I):
                vendor = "Intel"
            elif re.search(r"AuthenticAMD", cpuStr, re.I):
                vendor = "AMD"

        cpuIdStr = "CPU%s" % counter
        cpu = _Cpu(cpuIdStr)
        cpu.speed = speed
        cpu.description = implementation
        cpu.name = brand
        cpu.vendor = vendor
        cpuByIds[counter] = cpu
        counter += 1

    return cpuByIds


def _parsePsrinfoForSolaris9(output, vcpuByIds={}):
    results = re.findall(r"The (\S+) physical processor has (\d+) virtual processors? \(([\d\s\-,]+?)\)", output)
    if not results:
        raise ValueError("Failed getting CPU information via 'psrinfo',"
                         " unrecognized output")

    cpuByIds = {}
    counter = 0
    for row in results:
        brand = row[0]
        #vcpuCount = row[1]
        vcpuRanges = row[2]

        speed = None
        cpuType = None
        vcpuIds = expandCpuRanges(vcpuRanges)
        anyVcpuId = None
        if vcpuIds is not None and len(vcpuIds.keys()) > 0:
            anyVcpuId = vcpuIds.keys()[0]
        if vcpuByIds and anyVcpuId is not None:
            vcpu = vcpuByIds.get(anyVcpuId)
            if vcpu is not None:
                speed = vcpu.speed
                cpuType = vcpu.name

        vendor = None
        if not vendor and cpuType == 'sparcv9':
            vendor = "Sun_Microsystems"

        cpuIdStr = "CPU%s" % counter
        cpu = _Cpu(cpuIdStr)
        cpu.name = brand
        cpu.description = brand
        cpu.speed = speed
        cpu.vendor = vendor
        cpuByIds[counter] = cpu
        counter += 1

    return cpuByIds


def getSolarisPhysicalCpusViaPsrinfo(client, version):
    output = client.execCmd("/usr/sbin/psrinfo -pv")
    output = output and output.strip()
    if not output or client.getLastCmdReturnCode() != 0:
        raise ValueError("Failed getting CPU information via 'psrinfo'")

    vcpusByIds = {}
    try:
        vcpusByIds = getSolarisVirtualCpus(client)
    except ValueError, ex:
        logger.warn(str(ex))

    if version == '5.9':
        return _parsePsrinfoForSolaris9(output, vcpusByIds)
    else:
        return _parsePsrinfoForSolaris10(output, vcpusByIds)


def getSolarisPhysicalCpusViaKstat(client):
    output = client.execCmd('kstat -p cpu_info')
    output = output and output.strip()
    if not output or client.getLastCmdReturnCode() != 0:
        raise ValueError("Failed getting CPU information via 'kstat'")

    lines = output.splitlines()
    lines = [line.strip() for line in lines if line and line.strip()]
    cpuMap = {}  # map by Id -> map of attributes by name

    for line in lines:
        matcher = re.match(r"cpu_info:(\d+):cpu_info\d+:([\w-]+)\s+(.+)", line)
        if matcher:
            id_ = int(matcher.group(1))
            attributesMap = cpuMap.get(id_)
            if attributesMap is None:
                attributesMap = {}
                cpuMap[id_] = attributesMap
            attrName = matcher.group(2)
            attrValue = matcher.group(3)
            attrValue = attrValue and attrValue.strip()
            if attrName and attrValue:
                attributesMap[attrName] = attrValue

    logger.debug("Virtual CPU count: %s" % len(cpuMap.keys()))

    # map by chip ID -> map of cpu Ids to None (HashSet replacement)
    chipIdToCpuId = {}
    for id_, attributes in cpuMap.items():
        chipId = attributes.get('chip_id')
        if chipId is not None:
            chipId = int(chipId)
            cpuIds = chipIdToCpuId.get(chipId)
            if cpuIds is None:
                cpuIds = {}
                chipIdToCpuId[chipId] = cpuIds
            cpuIds[id_] = None
        else:
            raise ValueError("One of the virtual CPUs does not have chip_id set, cannot parse the output")

    logger.debug("Physical CPU count: %s" % len(chipIdToCpuId.keys()))

    # map by chip ID -> map of core Ids to None (HashSet replacement)
    chipIdToCoreId = {}
    for chipId, cpuIds in chipIdToCpuId.items():
        for cpuId in cpuIds.keys():
            attributes = cpuMap[cpuId]
            coreId = attributes.get('core_id')
            if coreId:
                coreId = int(coreId)
                coreIds = chipIdToCoreId.get(chipId)
                if coreIds is None:
                    coreIds = {}
                    chipIdToCoreId[chipId] = coreIds
                coreIds[coreId] = None

    #TODO: 3 additional attributes are available (but only for non-sparc cpus)
    #ncore_per_chip 2
    #ncpu_per_chip 2
    #pkg_core_id 0

    cpuByIds = {}
    counter = 0
    chipIds = chipIdToCpuId.keys()
    chipIds = sorted(chipIds)
    for chipId in chipIds:
        cpuStr = "CPU%s" % counter
        counter += 1
        cpu = _Cpu(cpuStr)
        cpuIds = chipIdToCpuId.get(chipId)
        cpuId = cpuIds.keys()[0]

        attributes = cpuMap[cpuId]

        implementation = attributes.get('implementation')
        brand = attributes.get('brand')
        clock = attributes.get('clock_MHz')
        cpuType = attributes.get('cpu_type')
        vendor = attributes.get('vendor_id')

        if implementation:
            cpu.description = implementation

        cpu.name = brand
        if not cpu.name and implementation:
            cpu.name = implementation
            matcher = re.match(r"(\S+)\s+\(", implementation)
            if matcher:
                cpu.name = matcher.group(1)

        if clock:
            try:
                cpu.speed = int(clock)
            except:
                pass

        if not cpu.speed and implementation:
            matcher = re.search(r"clock\s+(\d+)\s+MHz", implementation)
            try:
                cpu.speed = int(matcher.group(1))
            except:
                pass

        if vendor:
            if re.search(r"Intel", vendor, re.I):
                vendor = "Intel"
            elif re.search(r"AuthenticAMD", vendor, re.I):
                vendor = "AMD"
        if not vendor and cpuType == 'sparcv9':
            vendor = "Sun_Microsystems"

        if vendor:
            cpu.vendor = vendor

        coreIds = chipIdToCoreId.get(chipId)
        coreCount = None
        #in case core_id is not present in output all collections will be empty
        if coreIds:
            coreCount = len(coreIds.keys())

        if coreCount is None and len(chipIdToCpuId) == len(cpuMap):
            coreCount = 1

        if coreCount is not None:
            cpu.coresCount = coreCount

        cpuByIds[chipId] = cpu

    return cpuByIds


def getSolarisPhysicalCpus(client, version):

    cpuByIds = {}
    try:
        cpuByIds = getSolarisPhysicalCpusViaKstat(client)
    except ValueError, ex:
        logger.warn(str(ex))

    if not cpuByIds and version in ('5.10', '5.9'):
        cpuByIds = getSolarisPhysicalCpusViaPsrinfo(client, version)

    return cpuByIds


def getSolarisVirtualCpus(client):
    output = client.execCmd('/usr/sbin/psrinfo -v')#V@@CMD_PERMISION tty protocol execution
    output = output and output.strip()
    if not output or client.getLastCmdReturnCode() != 0:
        raise ValueError("Failed getting CPU information via 'psrinfo'")

    vcpuById = {}
    results = re.findall(r"Status of virtual processor (\d+) as of[\:\w\d\s\/.-]+The (.*?) processor operates at (\d+) MHz", output)
    if results:
        for row in results:
            vcpuId = int(row[0])
            vcpuName = row[1]
            vcpuSpeed = int(row[2])
            cpu = _Cpu("CPU%s" % vcpuId)
            cpu.id = vcpuId
            cpu.name = vcpuName
            cpu.speed = vcpuSpeed
            vcpuById[vcpuId] = cpu
    return vcpuById


def disSunOS(host_obj, client, Framework, langBund, host_is_virtual = False):
#add check for non-global zone and ldom.

    cpuTypesToCores = {"SPARC.?IV": 2, #UltraSPARC-IV and UltraSPARC-IV+
                       "SPARC.?II": 1, #UltraSPARC-II, UltraSPARC-III,
                                       #UltraSPARC-IIIi, UltraSPARC-III+
                       "SPARC.?T2": 8, #UltraSPARC-T2
                       "SPARC.?T4": 8  #UltraSPARC-T4
                       }

    myVec = ObjectStateHolderVector()

    version = client.getOsVersion()
    version = version and version.strip()
    logger.debug("Solaris version is '%s'" % version)

    physicalCpusById = getSolarisPhysicalCpus(client, version)

    # Identifying number of cores basing on the description
    cpuNoCores = filter(lambda cpu: cpu.coresCount is None and cpu.description,
                        physicalCpusById.values())
    for cpu in cpuNoCores:
        for pattern, coresCount in cpuTypesToCores.items():
            if re.search(pattern, cpu.description, re.I):
                cpu.coresCount = coresCount
                break

    for cpu in physicalCpusById.values():
        cpuOsh = makeCPUOSH(host_obj, cpu.idStr, cpu.vendor, cpu.speed, '',
                            cpu.name, cpu.coresCount, cpu.description, is_virtual=host_is_virtual)
        myVec.add(cpuOsh)

    return myVec


def _getOsCaption(wmiProvider):
    ''' Get OS caption string
    WmiAgentProvider -> str
    @raise Exception: if WMI query execution failed
    @command: wmic path Win32_OperatingSystem get Caption /value < %SystemRoot%\win.ini
    TODO: export to corresponding discoverer
    '''
    builder = wmiProvider.getBuilder('Win32_OperatingSystem')
    builder.addWmiObjectProperties("Caption")
    systems = wmiProvider.getAgent().getWmiData(builder)
    for os in systems:
        return os.Caption
    raise Exception, "Failed to get OS caption"


def disWinOS(hostCmdbId, shell, Framework, langBund, host_is_virtual = False):
    ''' Discover CPUs for windows by shell
    str, WinShell, Framework, bundle -> OSH vector
    @param Framework and langBund: are not used
    @deprecated: use hostresources modules instead
    '''
    hostOsh = modeling.createOshByCmdbIdString('host', hostCmdbId)
    wmiProvider = getWmiProvider(shell)
    cpuDiscoverer = CpuDiscoverer(wmiProvider)
    try:
        resources = cpuDiscoverer.discover()
    except:
        logger.debug('Failed to discover CPU info from win32_Processor. '
                     'Trying to discover physical CPU on base '
                     'of SocketDesignation property ')
        cpuDiscoverer = CpuDiscovererBySocketDesignationProperty(wmiProvider)
        resources = cpuDiscoverer.discover()
    resources.build(hostOsh)
    return resources.report()
