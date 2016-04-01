# coding=utf-8
'''
Created on Dec 26, 2013

@author: ekondrashev
'''
import re
from itertools import ifilter
from collections import defaultdict
from functools import partial
from operator import attrgetter

import vendors
import fptools
import logger
import wwn
from fptools import safeFunc as Sfn, identity, comp, methodcaller
from file_system import UnixPath

import service_loader
from os_platform_discoverer import enum as os_platforms
import fc_hba_discoverer
from ls import find as find_ls_impl
import command
import fc_hba_model
from fc_hba_model import _parse_port_speed

def _parse_lspci(lines):
    '''Parses `lspci -v -m -n -s <device_id>` command output, returning
    key/value dictionary.

    @param lines: output of lspci splitted by lines
    @type lines: list[basestring]
    @return: dictionary of name/value pairs
    @rtype: dict[str,str]
    '''
    sep_pattern = re.compile('\s*:\s*')

    lines = ifilter(identity, lines)

    result = {}
    for line in lines:
        key, value = sep_pattern.split(line.strip(), maxsplit=1)
        key = key.strip().lower()
        value = value.strip()
        result[key] = value

    return result


class cat(command.UnixBaseCmd):
    '''
    Command class for `cat` executable extending
    command.BaseCmd.DEFAULT_HANDLERS static attribute with additional
    handlers specific to `cat` command.
    '''

    DEFAULT_HANDLERS = (command.UnixBaseCmd.DEFAULT_HANDLERS +
                        (command.cmdlet.raiseOnNonZeroReturnCode,
                         command.cmdlet.raiseWhenOutputIsNone,
                         command.cmdlet.stripOutput,
                         ))

    def __init__(self, path, handler=None):
        '''
        @param path: file path to get content for
        @type path: basestring or file_system.Path
        @param handler: handler to use for current command
        @type handler: callable[command.Result] -> ?. The default handler returns `cat` command output stripped
        '''
        command.UnixBaseCmd.__init__(self, 'cat "%s"' % path, handler=handler)


class readlink(command.UnixBaseCmd):
    '''
    Command class for `readlink`(print value of a symbolic link or canonical
     file name) executable extending
    command.BaseCmd.DEFAULT_HANDLERS static attribute with additional
    handlers specific to `readlink` command.
    '''
    DEFAULT_HANDLERS = (command.UnixBaseCmd.DEFAULT_HANDLERS +
                        (command.cmdlet.raiseOnNonZeroReturnCode,
                         command.cmdlet.raiseWhenOutputIsNone,
                         command.cmdlet.stripOutput,
                         UnixPath
                         ))

    def __init__(self, path, handler=None):
        '''
        @param path: file path to resolve
        @type path: basestring or file_system.Path
        @param handler: handler to use for current command
        @type handler: callable[command.Result] -> ?. The default handler returns UnixPath instance
        '''
        command.UnixBaseCmd.__init__(self, 'readlink "%s"' % path, handler=handler)

    @property
    def e(self):
        '''Creates new command appending '-e' option
        responsible for "canonicalize by following every symlink in every
        component of the given name recursively, all components must exist"

        @return: new command instance with '-e' option
        @rtype: command.UnixBaseCmd
        '''
        return command.UnixBaseCmd(self.cmdline + " -e", handler=self.handler)


@service_loader.service_provider(fc_hba_discoverer.Discoverer)
class Discoverer(fc_hba_discoverer.Discoverer):
    OS_PLATFORM = os_platforms.LINUX

    def __init__(self):
        self.get_driver_version = self._scsi_host_attribute_getter(('driver_version','lpfc_drvr_version'))
        self.get_model_name = self._scsi_host_attribute_getter(('model_name','modelname'))
        self.get_serial_num = self._scsi_host_attribute_getter(('serial_num','serialnum'))
        self.get_fw_version = self._scsi_host_attribute_getter(('fw_version','fwrev'))

        self.get_port_id = self._fc_host_attribute_getter(('port_id',))
        self.get_port_type = self._fc_host_attribute_getter(('port_type',))
        self.get_port_name = self._fc_host_attribute_getter(('port_name',))
        self.get_node_name = self._fc_host_attribute_getter(('node_name',))
        self.get_port_speed = self._fc_host_attribute_getter(('speed',))

    @staticmethod
    def list_fc_host_instances(list_dir_fullnames_fn):
        '''Returns list of paths of corresponding to fc_host class instances

        @param list_dir_fullnames_fn: callable returning list of child path
            instances corresponding to passed path.
        @type list_dir_fullnames_fn: callable[basestring or file_system.Path]
            -> list[file_system.Path].
            The callable may throw command.ExecuteException on list dir names failure

        @return: list of pathes of child directories for the target folder
        @rtype: list[file_system.Path]
        @raise command.ExecuteException: on list directory failure
        '''
        return list_dir_fullnames_fn(UnixPath('/sys/class/fc_host'))

    @staticmethod
    def list_fchost_remote_ports(list_dir_fullnames_fn, fc_host):
        '''Returns list of paths of corresponding to fc_host class remote instances

        @param list_dir_fullnames_fn: callable returning list of child path
            instances corresponding to passed path.
        @type list_dir_fullnames_fn: callable[basestring or file_system.Path]
            -> list[file_system.Path].
            The callable may throw command.ExecuteException on list dir names failure

        @param fc_host: name of fc host instance to list remote ports for
        @type fc_host: basestring
        @return: list of pathes of child directories for the target folder
        @rtype: list[file_system.Path]
        @raise command.ExecuteException: on list directory failure
        '''
        path = UnixPath('/sys/class/fc_host/%s/device' % fc_host)
        return filter(methodcaller('startswith', 'rport-'),
                      map(attrgetter('basename'),
                          list_dir_fullnames_fn(path)))

    @staticmethod
    def get_sys_class_attribute(get_file_content_fn, cls, inst_name, attr_name):
        '''Returns sysfs instance attribute value for target class

        @param get_file_content_fn: callable returning file content for passed path.
        @type get_file_content_fn: callable[basestring or file_system.Path]
            -> basestring.
            The callable may throw command.ExecuteException on get file content failure

        @param cls: name of a class to get the attribute for
        @type cls: basestring
        @param inst_name: name of the instance to query attribute for
        @type inst_name: basestring
        @param attr_name:
        @type attr_name:
        @return: Content of a file
        @rtype: basestring
        @raise command.ExecuteException: on get file content failure
        '''
        for attr in attr_name:
            path = UnixPath('/sys/class/%s/%s/%s' % (cls, inst_name, attr))
            value = get_file_content_fn(path)
            if value is None:
                logger.info("Command %s not found, try next one" % attr)
                continue
            return value

    @classmethod
    def get_scsi_host_attribute(cls, get_file_content_fn, scsi_name, attr_name):
        '''Returns sysfs instance attribute value for scsi_host class

        @param get_file_content_fn: callable returning file content for passed path.
        @type get_file_content_fn: callable[basestring or file_system.Path]
            -> basestring.
            The callable may throw command.ExecuteException on get file content failure

        @param scsi_name: name of the scsi_host instance to query attribute for
        @type scsi_name: basestring
        @param attr_name: name of the attribute to get value for
        @type attr_name: basestring
        @return: attribute value for target scsi device
        @rtype: basestring
        @raise command.ExecuteException: on get file content failure
        '''
        return cls.get_sys_class_attribute(get_file_content_fn, "scsi_host",
                                           scsi_name, attr_name)

    @classmethod
    def get_fc_host_attribute(cls, get_file_content_fn, fc_name, attr_name):
        '''Returns sysfs instance attribute value for fc_host class

        @param get_file_content_fn: callable returning file content for passed path.
        @type get_file_content_fn: callable[basestring or file_system.Path]
            -> basestring.
            The callable may throw command.ExecuteException on get file content failure

        @param fc_name: name of the fc_name instance to query attribute for
        @type fc_name: basestring
        @param attr_name: name of the attribute to get value for
        @type attr_name: basestring
        @return: attribute value for target fchost device
        @rtype: basestring
        @raise command.ExecuteException: on get file content failure
        '''
        return cls.get_sys_class_attribute(get_file_content_fn, "fc_host",
                                           fc_name, attr_name)

    @classmethod
    def _fc_host_attribute_getter(cls, attr_name):
        return partial(cls.get_fc_host_attribute, attr_name=attr_name)

    @classmethod
    def _scsi_host_attribute_getter(cls, attr_name):
        return partial(cls.get_scsi_host_attribute, attr_name=attr_name)

    def _get_list_dir_fullnames_fn(self, shell):
        executor = self.__get_produce_result_executor(shell)
        ls = find_ls_impl(command.cmdlet.executeCommand(shell))

        def fn(path):
            cmd = ls(path + '*').d.file_per_line
            return map(UnixPath, executor.process(cmd))
        return fn

    def _get_readlink_fn(self, shell):
        executor = self.__get_produce_result_executor(shell)

        def fn(path):
            return executor.process(readlink(path).e)
        return fn

    def _get_file_content_fn(self, shell):
        executor = self.__get_produce_result_executor(shell)

        def fn(path):
            return Sfn(executor.process)(cat(path))
        return fn

    def get_vendor_by_device_id(self, device_id, executor):
        '''Returns vendor name by device id

        @param device_id: id of device in form <domain>:<bus>:<slot>
        @type device_id: basestring
        @param executor: instance of a command executor
        @type executor: command.Executor
        @return: vendor name
        @rtype: basestring
        '''
        handler = comp(*reversed((command.cmdlet.raiseOnNonZeroReturnCode,
                                 command.cmdlet.raiseWhenOutputIsNone,
                                 command.cmdlet.stripOutput,
                                 fptools.methodcaller('splitlines'),
                                 _parse_lspci)))
        lspci = command.UnixBaseCmd("lspci -v -m -n -s %s" % device_id,
                                    handler=handler)
        result = executor.process(lspci)
        return vendors.find_name_by_id_in_hex(result.get('vendor'))

    def get_vendor_by_device_path(self, path, executor):
        '''Returns vendor name by device fs path

        @param path: path to device
        @type path: file_system.Path
        @param executor: instance of a command executor
        @type executor: command.Executor
        @return: vendor name
        @rtype: basestring
        '''
        device_path = executor.process(readlink(path).e)
        device_id = device_path.get_parent().get_parent().get_parent().basename
        return self.get_vendor_by_device_id(device_id, executor)

    def __get_produce_result_executor(self, shell):
        return command.ChainedCmdlet(command.cmdlet.executeCommand(shell),
                                         command.cmdlet.produceResult)

    def get_remote_port_descriptors(self, list_dir_fullnames_fn, get_content_fn, fchost):
        '''Returns dictionary of remote port details corresponding to passed fchost instance

        @param list_dir_fullnames_fn: callable returning list of child path
            instances corresponding to passed path.
        @type list_dir_fullnames_fn: callable[basestring or file_system.Path]
            -> list[file_system.Path].
            The callable may throw command.ExecuteException on list dir names failure

        @param get_content_fn: callable returning file content for passed path.
        @type get_content_fn: callable[basestring or file_system.Path]
            -> basestring.
            The callable may throw command.ExecuteException on get file content failure

        @param fchost: name of fc host instance to list remote ports for
        @type fchost: basestring
        @return: dictionary of remote port details:
            node wwn as a key, list of port wwn and port id pairs as value
        @rtype: dict[basestring, list[tuple[basestring, basestring]]
        @raise command.ExecuteException: on list directory failure
        '''
        names = self.list_fchost_remote_ports(list_dir_fullnames_fn, fchost)
        result = defaultdict(list)
        for name in names:
            portid = get_content_fn(UnixPath('/sys/class/fc_remote_ports') + name + 'port_id')
            nodename = get_content_fn(UnixPath('/sys/class/fc_remote_ports') + name + 'node_name')
            portname = get_content_fn(UnixPath('/sys/class/fc_remote_ports') + name + 'port_name')
            result[nodename].append((portid, portname))
        return result

    def get_fc_hbas(self, shell):
        executor = self.__get_produce_result_executor(shell)
        list_file_names_fn = self._get_list_dir_fullnames_fn(shell)
        get_content_fn = self._get_file_content_fn(shell)
        result = defaultdict(list)
        for path in self.list_fc_host_instances(list_file_names_fn):
            try:
                name = path.basename
                driver_version = Sfn(self.get_driver_version)(get_content_fn, name)
                fw_version = Sfn(self.get_fw_version)(get_content_fn, name)
                model = Sfn(self.get_model_name)(get_content_fn, name)
                portwwn = self.get_port_name(get_content_fn, name)
                nodewwn = self.get_node_name(get_content_fn, name)
                nodewwn = wwn.parse_from_str(nodewwn)
                serialnum = Sfn(self.get_serial_num)(get_content_fn, name)
                vendor = Sfn(self.get_vendor_by_device_path)(path, executor)

                fchba = fc_hba_model.FcHba(name, unicode(path),
                                           wwn=nodewwn,
                                           vendor=vendor, model=model,
                                           serial_number=serialnum,
                                           driver_version=driver_version,
                                           firmware_version=fw_version)

                remote_ports = self.get_remote_port_descriptors(list_file_names_fn, get_content_fn, name)
                ports = []
                try:
                    port_id = self.get_port_id(get_content_fn, name)
                    port_id = Sfn(int)(port_id, 16)
                    port_wwn = wwn.parse_from_str(portwwn)
                    type_ = self.get_port_type(get_content_fn, name)
                    port_speed = _parse_port_speed(self.get_port_speed(get_content_fn, name))
                    ports.append((fc_hba_model.FcPort(port_id, port_wwn,
                                                      type_, None, port_speed),
                                  self._create_target_fchba_details(remote_ports)))
                except (command.ExecuteException, TypeError, ValueError), ex:
                    logger.debugException('Failed to create fcport data object')

                result[fchba].extend(ports)
            except (command.ExecuteException, TypeError, ValueError), ex:
                logger.debugException('Failed to create fchba data object')

        return result.items()

    def _create_target_fchba_details(self, remote_descriptors):
        result = []
        if remote_descriptors:
            for nodewwn, port_descriptors in remote_descriptors.items():
                for port_descriptor in port_descriptors:
                    portid, portwwn = port_descriptor
                    try:
                        port_id = Sfn(int)(portid, 16)
                        wwpn = wwn.normalize(portwwn)
                        wwnn = wwn.normalize(nodewwn)
                        port_name = ''
                        node_name = ''
                        fchba = fc_hba_model.FcHba('', node_name, wwn=wwnn)
                        fcport = fc_hba_model.FcPort(port_id, wwpn, type=None, name=port_name)
                        result.append((fchba, fcport, None))
                    except (TypeError, ValueError):
                        logger.debugException('Failed to create target fchba/fcport data object')
        return tuple(result)
