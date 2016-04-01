__author__ = 'gongze'
import os
import re
import logger
import modeling
import service_loader
from snmp_model_finder import OID
from snmp_model_finder import JayObject
from snmp_model_finder import SnmpHelper
from snmp_model_finder import is_offspring
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector


snmpModelDiscoversMap = {}
NOT_FOUND_IN_MIB = 'NOT FOUND IN MIB'
NOT_DEFINED_IN_MIB = 'NOT DEFINED IN MIB'
NOT_IN_THE_MIB = 'NOT IN THE MIB'

SNMP_DISCOVERY_PLUGIN_PATTERN = 'snmp_model_discovery_plugin_*.py'

PRIORITY_HIGHER = 20
PRIORITY_HIGH = 10
PRIORITY_DEFAULT = 0
PRIORITY_LOW = -10
PRIORITY_LOWER = -20


def tohexstring(s):
    return s.encode('hex')


def clean_nonprintable_characters(s):
    if not s:
        return ''
    s = s.strip('\x00')
    ch = ['\x1B', '\x01', '\x02', '\x03', '\x04', '\x05', '\x06', '\x07', '\x08', '\x0b', '\x0c', '\x0e', '\x0f', '\x10', '\x11', '\x12', '\x13',
          '\x14', '\x15', '\x16', '\x17', '\x17', '\x19', '\x1a', '\x1c', '\x1d', '\x1e', '\x1f']
    for x in ch:
        s = s.replace(x, '')
    return s


def trim(s):
    return s.strip()


def sizeof(x):
    return len(x)


def strlen(s):
    return len(s)


def substring(s, start, end):
    return s[start:end]


def strcopy(s, init, length=None):
    sl = strlen(s)
    if init <= 0:
        init = 1
    if init > sl:
        init = sl + 1
    if not length:
        length = sl - init + 1
    if length < 0:
        length = 0
    if length + init > sl:
        length = sl - init + 1

    first = init - 1
    second = init + length - 1

    return s[:first], s[first:second], s[second:]


def strncmp(x, y, index):
    if len(x) > index:
        x = x[:index]
    if len(y) > index:
        y = y[:index]

    return cmp(x, y)


def regex(pattern, target):
    m = re.search(pattern, target)
    if m:
        whole = list(m.groups())
        whole.insert(0, m.group(0))
        return tuple(whole)


def strtok(target, sep):
    return target.split(sep)


def keys(jay):
    return jay.keys()


def Supported(*types):
    def proxy(f):
        f.supportedTypes = types
        snmpModelDiscoversMap[f.__name__] = f
        return f

    return proxy


def Required(*types):
    def proxy(f):
        f.requiredTypes = types
        return f

    return proxy


def Priority(priority):
    def proxy(f):
        f.priority = priority
        return f

    return proxy


def Continue():
    def proxy(f):
        f.continueNext = True
        return f

    return proxy


def makeRegistrar():
    registry = []

    def registrar(func):
        registry.append(func.__name__)
        return func

    registrar.all = registry
    return registrar


def remove_method_if_not_seeded(model, address, midx):
    if 0 == model.resource_seeded:
        del model.Method[midx]


def get_storage_type(storage_value):
    # rfc1514
    table = {'1.3.6.1.4.1.23.2.27.2.1.1': 'disk',
             '1.3.6.1.4.1.23.2.27.2.1.2': 'ram',
             '1.3.6.1.4.1.23.2.27.2.1.3': 'ram',
             '1.3.6.1.4.1.23.2.27.2.1.4': 'ram',
             '1.3.6.1.4.1.23.2.27.2.1.5': 'ram',
             '1.3.6.1.4.1.23.2.27.2.1.6': 'ram',
             '1.3.6.1.4.1.23.2.27.2.1.7': 'ram',
             '1.3.6.1.4.1.23.2.27.2.1.8': 'ram',
             '1.3.6.1.4.1.23.2.27.2.1.9': 'ram',
             '1.3.6.1.4.1.23.2.27.2.1.10': 'ram',
             '1.3.6.1.4.1.23.2.27.2.1.11': 'ram',
             '1.3.6.1.2.1.25.2.1.2': 'ram',
             '1.3.6.1.2.1.25.2.1.3': 'vram',
             '1.3.6.1.2.1.25.2.1.4': 'disk',
             '1.3.6.1.2.1.25.2.1.7': 'cd'}
    return table.get(OID(storage_value).value())


def get_label_serial_number(desc):
    entry = JayObject()
    entry.serno = ''
    entry.label = ''
    entry.desc = desc
    sp = strtok(desc, ' ')
    labelid = None
    sernoid = None
    if not sp or 1 >= sizeof(sp):
        return entry
    for i, v in enumerate(sp):
        if regex('Label:', v):
            labelid = i
        if v == 'Serial' and sp[i + 1] == 'Number':
            sernoid = i
            break

    label = ''
    if not labelid is None:
        if strlen(sp[labelid]) > 6:
            m = strcopy(sp[labelid], 7)
            label = m[1]
        else:
            label = ''
        labelend = sizeof(sp)
        if not sernoid is None:
            labelend = sernoid
        for i in range(labelid + 1, labelend):
            label = label + ' ' + sp[i]

    serno = ''
    if not sernoid is None:
        for i in range(sernoid + 2, sizeof(sp)):
            serno = serno + ' ' + sp[i]

    entry.label = trim(label)
    entry.serno = trim(serno)
    max_value = None
    if not labelid is None:
        max_value = labelid
    else:
        if not sernoid is None:
            max_value = sernoid
    if not max_value is None:
        desc = ''
        for i in range(max_value):
            desc = desc + sp[i]
        entry.desc = trim(desc)
    return entry


class ModelDiscover(SnmpHelper):
    requiredTypes = []
    supportedTypes = []
    handlers = makeRegistrar()
    priority = PRIORITY_DEFAULT
    continueNext = False

    def __init__(self, stateHolder=None, snmpQueryHelper=None):
        super(ModelDiscover, self).__init__(stateHolder, snmpQueryHelper)
        if stateHolder:
            self.model = stateHolder.jay

    def __str__(self):
        return '%s:%s' % (self.__class__.__name__, self.supportedTypes)

    @classmethod
    def isApplicable(cls, types):
        t = tuple(types)
        typesSet = set(t)
        return set(cls.requiredTypes).issubset(typesSet) and set(cls.supportedTypes) & typesSet

    def discoverSerialNumber(self):
        raise NotImplementedError

    def discoverMiscInfo(self):
        raise NotImplementedError

    def discoverHostModelInformationList(self):
        raise NotImplementedError

    def discoverMoreModelInfo(self):
        raise NotImplementedError

    def discoverPrinterHostModelInformationList(self):
        raise NotImplementedError

    def add_resource_to_model(self, attribute, type, dvlsn=None):
        model = self.model
        if not model.total_resource:
            model.total_resource = 0
        tr = model.total_resource
        resource = JayObject()
        resource.Child[tr].Type = type
        if attribute.Name:
            resource.Child[tr].Name = attribute.Name
        else:
            resource.Child[tr].Name = ''
        if attribute.Unit and (attribute.Unit != 'percent') and (attribute.Unit != 'utilization'):
            resource.Child[tr].Unit = attribute.Unit
        else:
            resource.Child[tr].Unit = ''
        if (attribute.Max and attribute.Unit and
                (attribute.Unit != 'percent') and (attribute.Unit != 'utilization') ):
            resource.Child[tr].Capacity = attribute.Max
        else:
            resource.Child[tr].Capacity = ''
        if attribute.Description:
            resource.Child[tr].Description = attribute.Description
        else:
            resource.Child[tr].Description = ''
        if attribute.PrinterCpuId:
            resource.Child[tr].PrinterCpuId = attribute.PrinterCpuId
        else:
            resource.Child[tr].PrinterCpuId = ''
        resource.Child[tr].SN = ''
        resource.Child[tr].MountPoint = ''
        if dvlsn:
            resource.Child[tr].SN = dvlsn.serno
            resource.Child[tr].Description = dvlsn.desc
            if dvlsn.label != '':
                resource.Child[tr].Description = dvlsn.label
            if dvlsn.mountpoint:
                resource.Child[tr].MountPoint = dvlsn.mountpoint
                if dvlsn.label == '':
                    if dvlsn.mountpoint == dvlsn.desc:
                        resource.Child[tr].Description = ''
            else:
                if dvlsn.desctomountpoint == 1:
                    tt = strtok(dvlsn.desc, ' ')
                    if sizeof(tt) == 1:
                        resource.Child[tr].MountPoint = dvlsn.desc
                        if dvlsn.label == '':
                            resource.Child[tr].Description = ''

        model.ResourceList.Child[tr] = resource.Child[tr]
        model.total_resource += 1

    def add_lacking_serial_number(self):
        self.model.SerialNumber.Chassis[0].Description = NOT_DEFINED_IN_MIB
        self.model.SerialNumber.Chassis[0].SerialNumber = NOT_DEFINED_IN_MIB

    def add_model_of_printer(self, oid=None):
        model = self.model
        if not oid:
            oid = '1.3.6.1.2.1.25.3.2.1.3.1'
        k = self.snmpGetValue(oid)
        desc = 'PM:' + 'NOT IN THE MIB'
        if k:
            desc = 'PM:' + k

        model.MiscInfo = 'PSM:N/A 2003-02-15;' + desc + ';PNBR:N/A 2003-02-15'

    def add_storage_model(self):
        model = self.model
        mount_points = JayObject()
        mount_points_desc = JayObject()
        Args = JayObject()

        midx = sizeof(model.Method) if model.Method else 0
        fs_storage_idx = self.snmpWalk('1.3.6.1.2.1.25.3.8.1.7')
        needmount_points_desc = 0
        if fs_storage_idx:
            for storage_oid, storage_idx in fs_storage_idx:
                if storage_idx and storage_idx.isdigit() and int(storage_idx) > 0:
                    r = self.snmpGetValue('1.3.6.1.2.1.25.3.8.1.2.' + OID(storage_oid).serials()[11])
                    if r:
                        mount_points[storage_idx] = r
                        mount_points_desc[r] = OID(storage_oid).serials()[11]
                        needmount_points_desc = 1

        aidx = 0
        ramisOK = 0
        storage_types = self.snmpWalk('1.3.6.1.2.1.25.2.3.1.2')
        if storage_types:
            inactive_resources = self.get_ALPHA_inactive_resource_list() if \
                self.snmpStateHolder.hasTypes('COMPAQ_ALPHA') else JayObject()
            for storage_oid, storage_value in storage_types:
                index = OID(storage_oid).serials()[11]
                if inactive_resources[index]:
                    continue
                storage_type = get_storage_type(storage_value)
                if storage_type == 'cd':
                    r = self.snmpGetValue('1.3.6.1.2.1.25.2.3.1.3.' + index)
                    if r:
                        tempattr = JayObject()
                        tempattr.Unit = ''
                        tempattr.Name = 'cd.' + index
                        tempattr.Max = ''
                        dvlsn = get_label_serial_number(r)
                        tempattr.Description = dvlsn.desc
                        if needmount_points_desc == 1 and mount_points_desc[r]:
                            indexnew = mount_points_desc[r]
                        else:
                            indexnew = index
                        if mount_points[indexnew]:
                            dvlsn.mountpoint = mount_points[indexnew]
                        dvlsn.desctomountpoint = 1
                        self.add_resource_to_model(tempattr, 'cd', dvlsn)
                elif storage_type == 'ram':
                    ramisOK = 1
                    r0 = self.snmpGetValue('1.3.6.1.2.1.25.2.3.1.3.' + index)
                    r1 = self.snmpGetValue('1.3.6.1.2.1.25.2.2.0')
                    if r0 and r1:
                        r1 = regex('\d*', r1)[0]
                        max_space = float(r1)
                        if max_space > 0.0:
                            if max_space > 1048576.0:
                                max_space /= 1024.0 * 1024.0
                                model.Method[midx].Attribute[aidx].Unit = 'GB'
                            elif 1024.0 < max_space <= 1048576.0:
                                max_space /= 1024.0
                                model.Method[midx].Attribute[aidx].Unit = 'MB'
                            else:
                                model.Method[midx].Attribute[aidx].Unit = 'KB'
                            model.Method[midx].Attribute[aidx].Name = 'ram.' + index
                            model.Method[midx].Attribute[aidx].StorageType = 'percent0d'
                            model.Method[midx].Attribute[aidx].HistorianMethod = ['Avg', 'PeakValueAndTime']
                            model.Method[midx].Attribute[aidx].Max = max_space
                            model.Method[midx].Attribute[aidx].Scale = max_space / 100.0
                            dvlsn = get_label_serial_number(r0)
                            if dvlsn.label != '':
                                model.Method[midx].Attribute[aidx].Description = dvlsn.desc + ' ' + dvlsn.label
                            else:
                                model.Method[midx].Attribute[aidx].Description = dvlsn.desc
                            Args[aidx] = ['ram.' + index, index]
                            self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'ram', dvlsn)
                            aidx += 1
                        elif max_space < 0.0:
                            logger.warn('Negative ram size reported by agent ip = ', model.Jaywalk.Address)
                elif storage_type == 'vram':
                    if 0 == model.resource_seeded:
                        continue

                    r0 = self.snmpGetValue('1.3.6.1.2.1.25.2.3.1.3.' + index)
                    r1 = self.snmpGetValue('1.3.6.1.2.1.25.2.3.1.4.' + index)
                    r2 = self.snmpGetValue('1.3.6.1.2.1.25.2.3.1.5.' + index)
                    if r0 and r1 and r2:
                        r1 = regex('\d*', r1)[0]
                        max_space = float(r1) * float(r2) / 1024.0 / 1024.0
                        if max_space > 0.0:
                            if max_space > 1024.0:
                                max_space /= 1024.0
                                model.Method[midx].Attribute[aidx].Unit = 'GB'
                            else:
                                model.Method[midx].Attribute[aidx].Unit = 'MB'
                            model.Method[midx].Attribute[aidx].Name = 'vram.' + index
                            model.Method[midx].Attribute[aidx].StorageType = 'percent0d'
                            model.Method[midx].Attribute[aidx].HistorianMethod = ['Avg', 'PeakValueAndTime']
                            model.Method[midx].Attribute[aidx].Max = max_space
                            model.Method[midx].Attribute[aidx].Scale = max_space / 100.0
                            dvlsn = get_label_serial_number(r0)
                            if dvlsn.label != '':
                                model.Method[midx].Attribute[aidx].Description = dvlsn.desc + ' ' + dvlsn.label
                            else:
                                model.Method[midx].Attribute[aidx].Description = dvlsn.desc
                            Args[aidx] = ['vram.' + index, index]
                            self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'vram', dvlsn)
                            aidx += 1
                        else:
                            if max_space < 0.0:
                                logger.warn('Negative virtual ram size reported by agent ip = ', model.Jaywalk.Address)
                elif storage_type == 'disk':
                    if needmount_points_desc == 1:
                        rt = self.snmpGetValue('1.3.6.1.2.1.25.2.3.1.3.' + index)
                        if rt and mount_points_desc[rt]:
                            indexnew = mount_points_desc[rt]
                        else:
                            indexnew = index
                    else:
                        indexnew = index
                    if self.snmpStateHolder.hasTypes('COMPAQ_ALPHA') and model.diskOK == 1:
                        continue
                    rmp = self.snmpGetValue('1.3.6.1.2.1.25.3.8.1.3.' + indexnew)
                    if rmp and not self.snmpStateHolder.hasTypes('CMU_LINUX_AGENT') and \
                            not self.snmpStateHolder.hasTypes('KINNNETICS_buggy_HOST'):
                        r0, r1, r2 = None, None, None
                    elif (self.snmpStateHolder.hasTypes('UCD_LINUX_AGENT') or
                              self.snmpStateHolder.hasTypes('LINUX_NET_SNMP')) and \
                            mount_points[index] and regex('/dev/pts', mount_points[index]):
                        r0, r1, r2 = None, None, None
                    else:
                        r0 = self.snmpGetValue('1.3.6.1.2.1.25.2.3.1.3.' + index)
                        r1 = self.snmpGetValue('1.3.6.1.2.1.25.2.3.1.4.' + index)
                        r2 = self.snmpGetValue('1.3.6.1.2.1.25.2.3.1.5.' + index)
                    if r0 and r1 and r2:
                        if 0 == strncmp(r0, '/proc/', 6):
                            continue
                        r1 = regex('\d*', r1)[0]
                        max_space = float(r1) * float(r2) / 1024.0 / 1024.0
                        if max_space > 0.0:
                            if max_space > 1024.0:
                                max_space /= 1024.0
                                model.Method[midx].Attribute[aidx].Unit = 'GB'
                            else:
                                model.Method[midx].Attribute[aidx].Unit = 'MB'
                            model.Method[midx].Attribute[aidx].Name = 'disk.' + index
                            model.Method[midx].Attribute[aidx].StorageType = 'percent0d'
                            model.Method[midx].Attribute[aidx].HistorianMethod = ['Avg', 'PeakValueAndTime']
                            model.Method[midx].Attribute[aidx].Max = max_space
                            model.Method[midx].Attribute[aidx].Scale = max_space / 100.0
                            model.Method[midx].Attribute[aidx].Description = r0
                            dvlsn = get_label_serial_number(r0)
                            model.Method[midx].Attribute[aidx].Description = dvlsn.desc
                            if mount_points[index]:
                                model.Method[midx].Attribute[aidx].Description = mount_points[index]

                            Args[aidx] = ['disk.' + index, index]
                            dvlsn.desctomountpoint = 1
                            self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'disk', dvlsn)
                            if dvlsn.label != '':
                                model.Method[midx].Attribute[aidx].Description = \
                                    model.Method[midx].Attribute[aidx].Description + ' ' + dvlsn.label
                            aidx += 1
                        elif max_space < 0.0:
                            logger.warn('Negative disk size reported by agent ip = ', model.Jaywalk.Address)

        if aidx > 0:
            model.Method[midx].Name = 'poll_host_storage_rfc1514'
            model.Method[midx].Args = [model.Jaywalk.Address, model.Jaywalk.CommunityRead, Args]
            remove_method_if_not_seeded(model, model.Jaywalk.Address, midx)

        if ramisOK:
            r = self.snmpGetValue('1.3.6.1.2.1.25.2.2.0')
            XAttribute = JayObject()
            if r:
                r = regex('\d*', r)[0]
                max_space = float(r)
                if max_space > 0.0:
                    if max_space > 1048576.0:
                        max_space /= 1024.0 * 1024.0
                        XAttribute.Unit = 'GB'
                    elif 1024.0 < max_space <= 1048576.0:
                        max_space /= 1024.0
                        XAttribute.Unit = 'MB'
                    else:
                        XAttribute.Unit = 'KB'

                    XAttribute.Name = 'ram'
                    XAttribute.Max = max_space
                    XAttribute.Description = 'Physical Memory'
                    self.add_resource_to_model(XAttribute, 'ram')
                elif max_space < 0.0:
                    logger.warn('Negative ram size reported by agent ip = ', model.Jaywalk.Address)

    def get_ALPHA_inactive_resource_list(self):
        inactive_resources = JayObject()
        # host.hrStorage.hrStorageTable.hrStorageEntry.hrStorageSize
        storage_size = self.snmpWalk('1.3.6.1.2.1.25.2.3.1.5')
        for storage_oid, storage_value in storage_size:
            if storage_value == '0':
                index = OID(storage_oid).serials()[11]
                inactive_resources[index] = 1
        return inactive_resources

    def def_method_attr(self, attr_name, attr_stortype, hist, unit, scale,
                        max_space=None, min_space=None, desc=None, midx=0, aidx=0):
        model = self.model
        model.Method[midx].Attribute[aidx].Name = attr_name
        model.Method[midx].Attribute[aidx].StorageType = attr_stortype
        model.Method[midx].Attribute[aidx].HistorianMethod = hist
        model.Method[midx].Attribute[aidx].Unit = unit
        model.Method[midx].Attribute[aidx].Scale = scale
        if max_space:
            model.Method[midx].Attribute[aidx].Max = max_space
        if min_space:
            model.Method[midx].Attribute[aidx].Min = min_space
        model.Method[midx].Attribute[aidx].Description = desc

    def add_cpu_model(self):
        model = self.model
        midx = sizeof(model.Method) if model.Method else 0
        device_types = self.snmpWalk('1.3.6.1.2.1.25.3.2.1.2')
        if device_types:
            cpu_loads = self.snmpWalk('1.3.6.1.2.1.25.3.3.1.2')
            if cpu_loads:
                cpu_num = sizeof(cpu_loads)
            else:
                cpu_num = 0
                for _, device_type in device_types:
                    if device_type == '1.3.6.1.2.1.25.3.1.3':
                        cpu_num += 1

            aidx = 0
            Args = JayObject()
            for j, (device_type_oid, device_type) in enumerate(device_types):
                if device_type == '1.3.6.1.2.1.25.3.1.3':
                    if cpu_loads:
                        index = OID(cpu_loads[aidx][0]).serials()[11]
                    else:
                        index = OID(device_type_oid).serials()[11]
                    Args[aidx] = ['cpu.' + index, index]
                    model.Method[midx].Attribute[aidx].Name = 'cpu.' + index
                    model.Method[midx].Attribute[aidx].StorageType = 'percent0d'
                    model.Method[midx].Attribute[aidx].HistorianMethod = ['Avg', 'PeakValueAndTime']
                    model.Method[midx].Attribute[aidx].Unit = 'percent'
                    model.Method[midx].Attribute[aidx].Scale = 1.0
                    model.Method[midx].Attribute[aidx].Max = 100
                    model.Method[midx].Attribute[aidx].Min = 0
                    index = OID(device_type_oid).serials()[11]
                    name = self.snmpGetValue('1.3.6.1.2.1.25.3.2.1.3.' + index)
                    if name:
                        model.Method[midx].Attribute[aidx].Description = name
                        if cpu_num > 1:
                            model.Method[midx].Attribute[aidx].Description = name + '->' + str(j + 1)
                    else:
                        linux_cpu_name = self.snmpGetValue('1.3.6.1.4.1.1575.1.5.2.1.0')
                        if linux_cpu_name:
                            description = linux_cpu_name
                            bogomips = self.snmpGetValue('1.3.6.1.4.1.1575.1.5.2.2.0')
                            if bogomips:
                                description = description + ',BogoMips=' + bogomips
                            model.Method[midx].Attribute[aidx].Description = description
                    self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'cpu')
                    aidx += 1
                    if aidx >= cpu_num:
                        break

            if aidx > 0:
                model.Method[midx].Name = 'poll_host_cpu_rfc1514'
                model.Method[midx].Args = [model.Jaywalk.Address, model.Jaywalk.CommunityRead, Args]
                remove_method_if_not_seeded(model, model.Jaywalk.Address, midx)


class CommonModelDiscover(ModelDiscover):
    def __init__(self, stateHolder, snmpQueryHelper):
        super(CommonModelDiscover, self).__init__(stateHolder, snmpQueryHelper)

    def discoverSerialNumberV1(self):
        logger.info('Apply discover: Discover SerialNumber by ver1.')
        model = self.model
        oid_entPhysicalClass = '1.3.6.1.2.1.47.1.1.1.1.5'
        oid_entPhysicalSerialNum = '1.3.6.1.2.1.47.1.1.1.1.11'
        oid_entPhysicalModelName = '1.3.6.1.2.1.47.1.1.1.1.13'
        oid_entPhysicalContainedIn = '1.3.6.1.2.1.47.1.1.1.1.4'
        entPhysicalClass = self.snmpWalk(oid_entPhysicalClass)
        if entPhysicalClass:
            module_index = 0
            for i, (key, value) in enumerate(entPhysicalClass):
                value = int(value)
                if value == 3:
                    entity_idx = OID(key).last()
                    entPhysicalSerialNum = self.snmpGetValue(OID(oid_entPhysicalSerialNum, entity_idx).value()) or NOT_FOUND_IN_MIB
                    entPhysicalModelName = self.snmpGetValue(OID(oid_entPhysicalModelName, entity_idx).value()) or NOT_FOUND_IN_MIB
                    model.SerialNumber.Chassis[0].Description = entPhysicalModelName
                    model.SerialNumber.Chassis[0].SerialNumber = entPhysicalSerialNum
                elif value == 9:
                    entity_idx = OID(key).last()
                    entPhysicalSerialNum = self.snmpGetValue(OID(oid_entPhysicalSerialNum, entity_idx).value()) or NOT_FOUND_IN_MIB
                    entPhysicalModelName = self.snmpGetValue(OID(oid_entPhysicalModelName, entity_idx).value()) or NOT_FOUND_IN_MIB
                    model.SerialNumber.Chassis[0].Module[module_index].Description = entPhysicalModelName
                    model.SerialNumber.Chassis[0].Module[module_index].SerialNumber = entPhysicalSerialNum
                    module_index += 1

    def supportV2(self):
        oid1 = '1.3.6.1.2.1.47.1.1.1.1.4'
        oid2 = '1.3.6.1.2.1.47.1.1.1.1.11'
        return self.hasValidOffspringSnmpNext(oid1) and self.hasValidOffspringSnmpNext(oid2)

    def discoverSerialNumberV2(self):
        logger.info('Apply discover: Discover SerialNumber by ver2.')
        if not (self.supportV2()):
            return

        oid_entPhysicalDesc = '1.3.6.1.2.1.47.1.1.1.1.2'
        oid_entPhysicalContainedIn = '1.3.6.1.2.1.47.1.1.1.1.4'
        oid_entPhysicalClass = '1.3.6.1.2.1.47.1.1.1.1.5'
        oid_entPhysicalName = '1.3.6.1.2.1.47.1.1.1.1.7'
        oid_entPhysicalHardwareRev = '1.3.6.1.2.1.47.1.1.1.1.8'
        oid_entPhysicalFirmwareRev = '1.3.6.1.2.1.47.1.1.1.1.9'
        oid_entPhysicalSoftwareRev = '1.3.6.1.2.1.47.1.1.1.1.10'
        oid_entPhysicalSerialNum = '1.3.6.1.2.1.47.1.1.1.1.11'
        oid_entPhysicalModelName = '1.3.6.1.2.1.47.1.1.1.1.13'
        entPhysicalDesc = self.snmpWalkValue(oid_entPhysicalDesc)
        entPhysicalContainedIn = self.snmpWalk(oid_entPhysicalContainedIn)
        entPhysicalClass = self.snmpWalkValue(oid_entPhysicalClass)
        entPhysicalName = self.snmpWalkValue(oid_entPhysicalName)
        entPhysicalHardwareRev = self.snmpWalkValue(oid_entPhysicalHardwareRev)
        entPhysicalFirmwareRev = self.snmpWalkValue(oid_entPhysicalFirmwareRev)
        entPhysicalSoftwareRev = self.snmpWalkValue(oid_entPhysicalSoftwareRev)
        entPhysicalSerialNum = self.snmpWalkValue(oid_entPhysicalSerialNum)
        entPhysicalModelName = self.snmpWalkValue(oid_entPhysicalModelName)
        if len(entPhysicalName) != len(entPhysicalDesc):
            logger.warn('Snmp walk error: get different size of physical name and physical desc.'
                        ' Maybe snmp query timeout, please consider increasing timeout')
            return
        for i in range(0, len(entPhysicalName)):
            if entPhysicalName[i]:
                entPhysicalName[i] = clean_nonprintable_characters(entPhysicalName[i] + ' ' + '(' + entPhysicalDesc[i] + ')')
            else:
                if regex('Hw Serial', entPhysicalDesc[i]):
                    b = strtok(entPhysicalDesc[i], ',')
                    entPhysicalName[i] = clean_nonprintable_characters(b[0])
                else:
                    entPhysicalName[i] = clean_nonprintable_characters(entPhysicalDesc[i])

        PhysicalClass = {'1': 'other',
                         '2': 'unknown',
                         '3': 'chassis',
                         '4': 'backplane',
                         '5': 'container',
                         '6': 'powerSupply',
                         '7': 'fan',
                         '8': 'sensor',
                         '9': 'module',
                         '10': 'port',
                         '11': 'stack'}
        childrenof = JayObject()
        parent_hash = JayObject()
        entity = JayObject()

        for i, (key, value) in enumerate(entPhysicalContainedIn):
            child = OID(key).last()
            parent = value
            parent_hash[str(child)] = parent
            if entPhysicalClass[i]:
                entity[str(child)].entPhysicalClass = PhysicalClass.get(entPhysicalClass[i], entPhysicalClass[i])
            else:
                entity[str(child)].entPhysicalClass = 'misc'
            entity[str(child)].entPhysicalName = entPhysicalName[i]
            entity[str(child)].entPhysicalHardwareRev = entPhysicalHardwareRev[i]
            if '' == entPhysicalHardwareRev[i] and regex('Hw Revision', entPhysicalDesc[i]):
                b = strtok(entPhysicalDesc[i], ':')
                entity[str(child)].entPhysicalHardwareRev = b[2]

            entity[str(child)].entPhysicalFirmwareRev = entPhysicalFirmwareRev[i]
            entity[str(child)].entPhysicalSoftwareRev = entPhysicalSoftwareRev[i]
            if '' == entPhysicalSerialNum[i] and ('3' == entPhysicalClass[i]):
                bv = self.snmpGetValue('1.3.6.1.4.1.9.3.6.3.0')
                if bv:
                    entPhysicalSerialNum[i] = bv
                else:
                    bv = self.snmpGetValue('1.3.6.1.4.1.9.5.1.2.19.0')
                if bv:
                    entPhysicalSerialNum[i] = bv

            entity[str(child)].entPhysicalSerialNum = entPhysicalSerialNum[i]
            if '' == entPhysicalSerialNum[i] and regex('Hw Serial', entPhysicalDesc[i]):
                b = strtok(entPhysicalDesc[i], ':')
                c = strtok(b[1], ',')
                entity[str(child)].entPhysicalSerialNum = c[0]

            entity[str(child)].entPhysicalModelName = clean_nonprintable_characters(entPhysicalModelName[i])
            if not childrenof[parent]:
                size = 0
                childrenof[parent].children[0] = child
            else:
                size = sizeof(childrenof[parent].children)
                childrenof[parent].children[size] = child

        key = keys(parent_hash)
        top = ''

        for i in range(0, len(key)):
            i_ = key[i]
            i__ = parent_hash[i_]
            if not parent_hash[i__]:
                top = i_
                break

        level = 0
        new_sn2 = self.buildup(top, childrenof, entity, level)
        self.model.SerialNumber2 = new_sn2

    def buildup(self, entity_index, childrenof, entity, level):
        new_sn2 = JayObject()
        new_sn2.ent_index = entity_index
        new_sn2.SN = entity[entity_index].entPhysicalSerialNum
        new_sn2.Description = entity[entity_index].entPhysicalModelName
        new_sn2.Type = entity[entity_index].entPhysicalClass
        new_sn2.PN = entity[entity_index].entPhysicalName
        new_sn2.HR = entity[entity_index].entPhysicalHardwareRev
        new_sn2.FR = entity[entity_index].entPhysicalFirmwareRev
        new_sn2.SR = entity[entity_index].entPhysicalSoftwareRev
        e_children = childrenof[entity_index].children
        if e_children and 10 > level:
            level += 1
            number_of_children = sizeof(e_children)
            for i in range(0, number_of_children):
                built_child = self.buildup(str(e_children[i]), childrenof, entity, level)
                if built_child:
                    new_sn2.Child[i] = built_child

        if not new_sn2.Child:
            if new_sn2.Type == 'port':
                if (((not (new_sn2.SN)) or (new_sn2.SN == '' )) and
                        ((not (new_sn2.Description)) or (new_sn2.Description == '')) and
                        ((not (new_sn2.HR)) or (new_sn2.HR == '' )) and
                        ((not (new_sn2.FR)) or (new_sn2.FR == '' )) and
                        ((not (new_sn2.SR)) or (new_sn2.SR == '' )) ):
                    new_sn2 = None
            else:
                if new_sn2.Type == 'container':
                    if (((not (new_sn2.SN)) or (new_sn2.SN == '' )) and
                            ((not (new_sn2.Description)) or (new_sn2.Description == '')) and
                            ((not (new_sn2.HR)) or (new_sn2.HR == '' )) and
                            ((not (new_sn2.FR)) or (new_sn2.FR == '' )) and
                            ((not (new_sn2.SR)) or (new_sn2.SR == '' )) and
                            (not (regex('[sS][lL][oO][tT]', new_sn2.PN))) ):
                        new_sn2 = None

        return new_sn2


    def finalModelVerificationAll(self):
        if self.model.SerialNumber:
            self.formatSerialNumber()
        elif self.model.SerialNumber2:
            self.model.SerialNumber = self.model.SerialNumber2
        cleaned_sn = self.model.SerialNumber
        self.cleanup_sn(self.model, 'SerialNumber')
        self.model.SerialNumber = cleaned_sn
        self.add_resources_to_SerialNumber()

    def add_resources_to_SerialNumber(self):
        model = self.model
        if model.SerialNumber.Child:
            k = keys(model.SerialNumber)
            k.sort()
            max = sizeof(k) - 1
            start = max + 10000

        else:
            start = 1000
        if model.total_resource:
            for i in range(0, model.total_resource):
                model.SerialNumber.Child[start + i] = model.ResourceList.Child[i]

    def formatSerialNumber(self):
        chas_text_nf = ''
        mod_text_nf = ''
        chas_text_nd = ''
        mod_text_nd = ''
        model = self.model
        if model.SerialNumber:
            size_c = len(model.SerialNumber.Chassis)
            new_sn = JayObject()
            if size_c == 1:
                if NOT_FOUND_IN_MIB == model.SerialNumber.Chassis[0].SerialNumber:
                    chas_text_nf = 'the Chassis'
                    new_sn.SN = ''
                elif NOT_DEFINED_IN_MIB == model.SerialNumber.Chassis[0].SerialNumber:
                    chas_text_nd = 'the Chassis'
                    new_sn.SN = ''
                else:
                    new_sn.SN = model.SerialNumber.Chassis[0].SerialNumber

                description = model.SerialNumber.Chassis[0].Description
                if description and 'NOT' in description:
                    new_sn.Description = ''
                else:
                    new_sn.Description = trim(clean_nonprintable_characters(description).strip())
                new_sn.Type = 'chassis'
                new_sn.PN = trim(clean_nonprintable_characters(model.SerialNumber.Chassis[0].PhysicalName))
                new_sn.HR = model.SerialNumber.Chassis[0].HardwareRev
                new_sn.FR = model.SerialNumber.Chassis[0].FirmwareRev
                new_sn.SR = model.SerialNumber.Chassis[0].SoftwareRev
                if model.SerialNumber.Chassis[0].Module:
                    size_m = sizeof(model.SerialNumber.Chassis[0].Module)
                    for j in range(0, size_m):
                        if NOT_FOUND_IN_MIB == model.SerialNumber.Chassis[0].Module[j].SerialNumber:
                            mod_text_nf = mod_text_nf + ' Module:' + str(j + 1)
                            new_sn.Child[j + 1].SN = ''
                        elif NOT_DEFINED_IN_MIB == model.SerialNumber.Chassis[0].Module[j].SerialNumber:
                            mod_text_nd = mod_text_nd + ' Module:' + str(j + 1)
                            new_sn.Child[j + 1].SN = ''
                        else:
                            new_sn.Child[j + 1].SN = model.SerialNumber.Chassis[0].Module[j].SerialNumber

                        description = model.SerialNumber.Chassis[0].Module[j].Description
                        if description and 'NOT' in description:
                            new_sn.Child[j + 1].Description = ''
                        else:
                            new_sn.Child[j + 1].Description = trim(
                                clean_nonprintable_characters(model.SerialNumber.Chassis[0].Module[j].Description))

                        new_sn.Child[j + 1].Type = 'module'
                        new_sn.Child[j + 1].PN = trim(clean_nonprintable_characters(model.SerialNumber.Chassis[0].Module[j].PhysicalName))
                        new_sn.Child[j + 1].HR = model.SerialNumber.Chassis[0].Module[j].HardwareRev
                        new_sn.Child[j + 1].FR = model.SerialNumber.Chassis[0].Module[j].FirmwareRev
                        new_sn.Child[j + 1].SR = model.SerialNumber.Chassis[0].Module[j].SoftwareRev
                if model.SerialNumber.Chassis[0].Sensor:
                    size_s = sizeof(model.SerialNumber.Chassis[0].Sensor)
                    for j in range(0, size_s):
                        new_sn.Child[j + 1].Type = 'sensor'
                        new_sn.Child[j + 1].ent_index = model.SerialNumber.Chassis[0].Sensor[j].EntIndex
                        new_sn.Child[j + 1].PN = trim(clean_nonprintable_characters(model.SerialNumber.Chassis[0].Sensor[j].PhysicalName))
                        new_sn.Child[j + 1].HR = model.SerialNumber.Chassis[0].Sensor[j].HardwareRev
                        new_sn.Child[j + 1].FR = model.SerialNumber.Chassis[0].Sensor[j].FirmwareRev
                        new_sn.Child[j + 1].SR = model.SerialNumber.Chassis[0].Sensor[j].SoftwareRev
                        new_sn.Child[j + 1].Description = trim(clean_nonprintable_characters(model.SerialNumber.Chassis[0].Sensor[j].Description))
                        new_sn.Child[j + 1].SN = model.SerialNumber.Chassis[0].Module[j].SerialNumber
            else:  # Stacked device
                for i in range(0, size_c):
                    new_sn.Type = 'stack'

                    if NOT_FOUND_IN_MIB == model.SerialNumber.Chassis[i].SerialNumber:
                        chas_text_nf = chas_text_nf + ' Chassis:' + str(i + 1)
                        new_sn.Child[i + 1].SN = ''
                    elif NOT_DEFINED_IN_MIB == model.SerialNumber.Chassis[i].SerialNumber:
                        chas_text_nd = chas_text_nd + ' Chassis:' + str(i + 1)
                        new_sn.Child[i + 1].SN = ''
                    else:
                        new_sn.Child[i + 1].SN = model.SerialNumber.Chassis[i].SerialNumber

                    description = model.SerialNumber.Chassis[i].Description
                    if description and 'NOT' in description:
                        new_sn.Child[i + 1].Description = ''
                    else:
                        new_sn.Child[i + 1].Description = trim(clean_nonprintable_characters(model.SerialNumber.Chassis[i].Description))
                    new_sn.Child[i + 1].Type = 'chassis'
                    new_sn.Child[i + 1].PN = trim(clean_nonprintable_characters(model.SerialNumber.Chassis[i].PhysicalName))
                    new_sn.Child[i + 1].HR = model.SerialNumber.Chassis[i].HardwareRev
                    new_sn.Child[i + 1].FR = model.SerialNumber.Chassis[i].FirmwareRev
                    new_sn.Child[i + 1].SR = model.SerialNumber.Chassis[i].SoftwareRev

                    if model.SerialNumber.Chassis[i].Module:
                        size_m = sizeof(model.SerialNumber.Chassis[i].Module)
                        for j in range(0, size_m):
                            if NOT_FOUND_IN_MIB == model.SerialNumber.Chassis[i].Module[j].SerialNumber:
                                mod_text_nf = mod_text_nf + ' Module:' + str(j + 1)
                                new_sn.Child[i + 1].Child[j + 1].SN = ''
                            elif NOT_DEFINED_IN_MIB == model.SerialNumber.Chassis[i].Module[j].SerialNumber:
                                mod_text_nd = mod_text_nd + ' Module:' + str(j + 1)
                                new_sn.Child[i + 1].Child[j + 1].SN = ''
                            else:
                                new_sn.Child[i + 1].Child[j + 1].SN = model.SerialNumber.Chassis[i].Module[j].SerialNumber
                            description = model.SerialNumber.Chassis[i].Module[j].Description
                            if description and 'NOT' in description:
                                new_sn.Child[i + 1].Child[j + 1].Description = ''
                            else:
                                new_sn.Child[i + 1].Child[j + 1].Description = trim(
                                    clean_nonprintable_characters(model.SerialNumber.Chassis[i].Module[j].Description))
                            new_sn.Child[i + 1].Child[j + 1].Type = 'module'
                            new_sn.Child[i + 1].Child[j + 1].PN = trim(
                                clean_nonprintable_characters(model.SerialNumber.Chassis[i].Module[j].PhysicalName))
                            new_sn.Child[i + 1].Child[j + 1].HR = model.SerialNumber.Chassis[i].Module[j].HardwareRev
                            new_sn.Child[i + 1].Child[j + 1].FR = model.SerialNumber.Chassis[i].Module[j].FirmwareRev
                            new_sn.Child[i + 1].Child[j + 1].SR = model.SerialNumber.Chassis[i].Module[j].SoftwareRev
            model.snExcep.modnf = mod_text_nf
            model.snExcep.modnd = mod_text_nd
            model.snExcep.chasnf = chas_text_nf
            model.snExcep.chasnd = chas_text_nd
            model.SerialNumber = new_sn

    def cleanup_sn(self, parent, attr):
        cleaned_sn = parent.getAttr(attr)
        if not cleaned_sn:
            parent.removeAttr(attr)
            return
        if cleaned_sn.Child:
            key = keys(cleaned_sn.Child)
            for x in key:
                self.cleanup_sn(cleaned_sn.Child, x)
        if not cleaned_sn.Child:
            del cleaned_sn.Child
            if not cleaned_sn.SN:
                del cleaned_sn.SN
            if not cleaned_sn.Description:
                del cleaned_sn.Description
            if not cleaned_sn.PN:
                del cleaned_sn.PN
            if not cleaned_sn.HR:
                del cleaned_sn.HR
            if not cleaned_sn.FR:
                del cleaned_sn.FR
            if not cleaned_sn.SR:
                del cleaned_sn.SR
            if not cleaned_sn.SN and not cleaned_sn.Description and not cleaned_sn.PN \
                    and not cleaned_sn.HR and not cleaned_sn.FR and not cleaned_sn.SR:
                parent.removeAttr(attr)

    def sanity_mib_check(self):
        model = self.model
        if model.sanitytestdone:
            if model.exception:
                return False
            return True
        model.sanitytestdone = 1
        id = '1.3.6.1.4.1.666.666.666.666.666.666.666.666'
        id2 = '1.3.6.1.4.1.666'
        id3 = '1.3.6.1.2.1.10.9.1.1.1.1'
        rv = self.snmpGet(id2)
        if rv[0] and not is_offspring(rv[0], id2):
            # warning(address," has a broken agent, returns value on invalid snmpget instead of error! ");
            model.exception = '1010'
            return False

        rv = self.snmpNext(id3)
        if rv[0] and is_offspring(rv[0], id3) and OID(rv[0]).size() > 13:
            # warning(address,' has a broken (ucd) agent, returns value for nonexistent oid. ')
            model.exception = '1010'
            return False

        rv = self.snmpNext(id)
        if not rv[0] or not is_offspring(rv[0], id):
            return True
        # warning(address,' has a broken agent, returns value instead of error! ')
        model.exception = '1010'
        return False


class ModelDiscoverAll(ModelDiscover):
    def __init__(self, stateHolder, snmpQueryHelper):
        super(ModelDiscoverAll, self).__init__(stateHolder, snmpQueryHelper)
        self.__discovers = None
        self.commonModelDiscover = CommonModelDiscover(stateHolder, snmpQueryHelper)

    def getSupportedDiscoverMethods(self, target):
        if not self.__discovers:
            classes = getDiscoversByModelTypes(self.snmpStateHolder.getTypes())
            self.__discovers = [clazz(self.snmpStateHolder, self.snmpQueryHelper) for clazz in classes]
        validDiscovers = []
        for clazz in self.__discovers:
            if hasattr(clazz, target.__name__):
                validDiscovers.append(clazz)
        return validDiscovers

    def discoverSerialNumber(self):
        if self.commonModelDiscover.supportV2():
            self.commonModelDiscover.discoverSerialNumberV2()
        else:
            if not self._runSupportedMethods(self.discoverSerialNumber):
                self.commonModelDiscover.discoverSerialNumberV1()

    def _runSupportedMethods(self, method):
        discovers = self.getSupportedDiscoverMethods(method)
        if discovers:
            canHandle = False
            for discover in discovers:
                logger.info('Apply discover:%s on method: %s.' % (discover, method.__name__))
                try:
                    getattr(discover, method.__name__)()
                    canHandle = True
                    if not discover.continueNext:
                        break
                except NotImplementedError:
                    pass
            return canHandle
        else:
            return False

    def discoverHostModelInformationList(self):
        if self.commonModelDiscover.sanity_mib_check():
            self._runSupportedMethods(self.discoverHostModelInformationList)

    def discoverMoreModelInfo(self):
        self._runSupportedMethods(self.discoverMoreModelInfo)

    def discoverPrinterHostModelInformationList(self):
        if self.commonModelDiscover.sanity_mib_check():
            self._runSupportedMethods(self.discoverPrinterHostModelInformationList)

    def discoverMiscInfo(self):
        self._runSupportedMethods(self.discoverMiscInfo)


class CIBuilderFactory(object):
    builders = {}

    @classmethod
    def getBuilder(cls, moduleType):
        builderClass = cls.builders.get(moduleType)
        if builderClass:
            return builderClass()
        return None


def BuildFor(*types):
    def proxy(f):
        for t in types:
            CIBuilderFactory.builders[t] = f

    return proxy


class CIBuilder(object):
    def build(self, module, container, node):
        raise NotImplementedError


@BuildFor('fan')
class FanBuilder(CIBuilder):
    def build(self, module, container, node):
        if module.ent_index:
            osh = ObjectStateHolder('fan')
            osh.setIntegerAttribute('fan_index', module.ent_index)
            if module.PN:
                osh.setStringAttribute('name', module.PN)
            return osh, node
        else:
            return None, None


@BuildFor('powerSupply')
class PowerSupplyBuilder(CIBuilder):
    def build(self, module, container, node):
        if module.ent_index:
            osh = ObjectStateHolder('power_supply')
            osh.setIntegerAttribute('power_supply_index', module.ent_index)
            if module.PN:
                osh.setStringAttribute('name', module.PN)
            return osh, node
        else:
            return None, None


@BuildFor('sensor')
class SensorBuilder(CIBuilder):
    def build(self, module, container, node):
        if module.ent_index:
            osh = ObjectStateHolder('environmental_sensor')
            osh.setIntegerAttribute('sensor_index', module.ent_index)
            osh.setStringAttribute('sensor_type', 'temperature')
            if module.PN:
                osh.setStringAttribute('name', module.PN)
            return osh, node
        else:
            return None, None


@BuildFor('toner')
class TonerBuilder(CIBuilder):
    def build(self, module, container, node):
        osh = ObjectStateHolder('printer_toner')
        osh.setStringAttribute('unit', module.Unit)
        osh.setFloatAttribute('capacity', module.Capacity)
        if module.SN:
            osh.setStringAttribute('serial_number', module.SN)
        if module.Description:
            osh.setStringAttribute('description', module.Description)
        osh.setStringAttribute('name', module.Name)
        return osh, node


@BuildFor('tray')
class TrayBuilder(CIBuilder):
    def build(self, module, container, node):
        osh = ObjectStateHolder('printer_tray')
        osh.setStringAttribute('unit', module.Unit)
        osh.setFloatAttribute('capacity', module.Capacity)
        if module.SN:
            osh.setStringAttribute('serial_number', module.SN)
        if module.Description:
            osh.setStringAttribute('description', module.Description)
        osh.setStringAttribute('name', module.Name)
        return osh, node


@BuildFor('cpu')
class CpuBuilder(CIBuilder):
    def build(self, module, container, node):
        #build printer CPU CIs
        if module.PrinterCpuId:
            osh = ObjectStateHolder('cpu')
            osh.setStringAttribute('name', module.Name)
            osh.setStringAttribute('cpu_id', module.PrinterCpuId)
            return osh, node
        return None, None


class PortBuilder(CIBuilder):
    def build(self, port, container, node):
        logger.debug('Building port...')
        mac = None
        if port.Address:
            addresses = port.Address.values()
            for addr in addresses:
                if addr.Address:
                    # ieee802:0010DB8D1B40
                    tmp = addr.Address
                    if tmp.startswith('ieee802:'):
                        mac = tmp[len('ieee802:'):]
                        break
        if mac:
            description = None
            ifIndex = None
            mediaType = None
            speed = None
            if port.Description:
                description = port.Description
            if port.IfIndex:
                ifIndex = int(port.IfIndex)
            if port.MediaType:
                mediaType = int(port.MediaType)
            if port.Speed:
                speed = long(port.Speed)
            return modeling.createInterfaceOSH(mac, container, description, ifIndex, mediaType, speed=speed), container
        return None, None


@BuildFor('backplane', 'container', 'module', 'chassis', 'stack')
class PowerSupplyBuilder(CIBuilder):
    def build(self, module, container, node):
        if module.ent_index or module.SN:
            osh = ObjectStateHolder('hardware_board')
            if module.ent_index:
                osh.setStringAttribute('board_index', module.ent_index)
            if module.HR:
                osh.setStringAttribute('hardware_version', module.HR)
            if module.FR:
                osh.setStringAttribute('firmware_version', module.FR)
            if module.SR:
                osh.setStringAttribute('software_version', module.SR)
            if module.PN:
                osh.setStringAttribute('name', module.PN)
            if module.SN:
                osh.setStringAttribute('serial_number', module.SN)
            if module.Description:
                osh.setStringAttribute('description', module.Description)
            if module.Type:
                osh.setStringAttribute('data_note', module.Type)
            return osh, container
        else:
            return None, None


class CIBuilderHelper(object):
    def __init__(self, vector, node, snmpStateHolder, nodeAsContainer=False):
        super(CIBuilderHelper, self).__init__()
        self.node = node
        self.snmpStateHolder = snmpStateHolder
        self.vector = vector
        self.nodeAsContainer = nodeAsContainer

    def buildCIs(self):
        model = self.snmpStateHolder.jay
        if model.SerialNumber:
            self.buildNode(model.SerialNumber)
            self.buildChildrenModules(model.SerialNumber, None, False)

        if model.MiscInfo:
            self.node.setAttribute('misc_info', model.MiscInfo)

        if model.Port:
            self.buildPorts(model.Port)

        if model.PhoneExt:
            self.node.setObjectClass('ip_phone')
            self.node.setAttribute('phone_number', model.PhoneExt)

        if model.MemorySize:
            matcher = re.search('(\d+)',model.MemorySize)
            memory_size_in_mb = int(matcher.group(1))/1024
            self.node.setIntegerAttribute('memory_size', memory_size_in_mb)

    def buildNode(self, module):
        osh = self.node
        modeling.setSNMPSysObjectId(osh, OID(self.snmpStateHolder.sysOid).getISOFormat())
        if self.snmpStateHolder.desc:
            osh.setStringAttribute('discovered_description', self.snmpStateHolder.desc)
        if module.Type in ['chassis', 'stack']:
            if module.SN and not osh.getAttribute('serial_number'):
                osh.setStringAttribute('serial_number', module.SN)
            if module.Description:
                osh.setStringAttribute('description', module.Description)
            if module.Type:
                osh.setStringAttribute('data_note', module.Type)
        if not osh.getAttribute('serial_number') and module.Type in['module'] and module.SN:
            osh.setStringAttribute('serial_number', module.SN)
            osh.setStringAttribute('data_note', module.Type)

    def buildChildrenModules(self, module, container, buildSelf=True):
        myself = None
        if buildSelf:
            myself = self.buildSelfModule(module, container)
        if module.Child:
            if self.nodeAsContainer:
                childContainer = self.node
            elif myself:
                childContainer = myself
            else:
                childContainer = self.node
            if childContainer:
                for key in keys(module.Child):
                    self.buildChildrenModules(module.Child[key], childContainer)

    def buildSelfModule(self, module, container):
        if not module.Type:
            return
        builder = CIBuilderFactory.getBuilder(module.Type)
        if builder:
            osh, container = builder.build(module, container, self.node)
            if osh:
                osh.setContainer(container)
                link = modeling.createLinkOSH('composition', container, osh)
                self.vector.add(osh)
                self.vector.add(link)
                return osh
        else:
            logger.debug('Unsupported module type:', module.Type)

    def buildPorts(self, ports):
        builder = PortBuilder()
        for child in ports.values():
            osh = builder.build(child, self.node)
            self.vector.add(osh)


def getDiscoversByModelTypes(modelTypes):
    discovers = [discover for discover in snmpModelDiscoversMap.values() if discover.isApplicable(modelTypes)]
    discovers.sort(key=lambda x: x.priority, reverse=True)
    return discovers


def doDiscover(snmpStateHolder, snmpQueryHelper):
    mda = ModelDiscoverAll(snmpStateHolder, snmpQueryHelper)
    mda.discoverMoreModelInfo()
    mda.discoverSerialNumber()
    mda.discoverHostModelInformationList()
    mda.discoverPrinterHostModelInformationList()
    mda.discoverMiscInfo()
    mda.commonModelDiscover.finalModelVerificationAll()


def __loadModule(moduleName):
    try:
        from com.hp.ucmdb.discovery.library.execution.impl import ScriptsLoader

        scriptName = moduleName + ScriptsLoader.PY_EXTENTION
        framework = logger._getFramework()
        ScriptsLoader.loadModule(moduleName, scriptName, framework)
    except:
        logger.error("Failed to load module:", moduleName)
    finally:
        __import__(moduleName)


def loadDiscoversRemotely():
    ms = service_loader.find_by_pattern(SNMP_DISCOVERY_PLUGIN_PATTERN)
    for moduleName in ms:
        __loadModule(moduleName)


def loadDiscoversLocally():
    folder = os.path.dirname(__file__)
    ms = service_loader.find_by_pattern(SNMP_DISCOVERY_PLUGIN_PATTERN, [folder])
    for moduleName in ms:
        __import__(moduleName)


def loadDiscoversDynamically():
    if globals().has_key('__file__'):
        loadDiscoversLocally()  # for locally testing
    else:
        loadDiscoversRemotely()  # for running in probe


def discoverAll(node, snmpStateHolder, snmpQueryHelper, nodeAsContainer=False):
    loadDiscoversDynamically()
    logger.info('All loaded discovers:', snmpModelDiscoversMap)
    doDiscover(snmpStateHolder, snmpQueryHelper)
    vector = ObjectStateHolderVector()
    vector.add(node)
    builderHelper = CIBuilderHelper(vector, node, snmpStateHolder, nodeAsContainer)
    builderHelper.buildCIs()
    return vector