#coding=utf-8
'''
Created on Jan 25, 2012

@author: ekondrashev
'''
from __future__ import nested_scopes
from plugins import Plugin as BasePlugin
from fptools import findFirst, safeFunc as Sfn
from functools import partial
import logger
import shellutils
import re
import maxdb_discoverer
import applications
import file_system
from maxdb_discoverer import DbEnumResult
from iteratortools import second
from itertools import izip, ifilter, starmap

_UNIX_KERNEL_NAME = 'kernel'
_WINDOWS_KERNEL_NAME = 'kernel.exe'


class SnmpMaxdbPlugin(BasePlugin):
    '''
    This plugin is created to remove false detected MaxDB in case there's a OS
    core kernel process visible via SNMP
    '''
    def __init__(self):
        BasePlugin.__init__(self)

    def isApplicable(self, context):
        return 1

    def process(self, context):
        kernelProc = context.application.getProcess(_UNIX_KERNEL_NAME)
        cmdLine = kernelProc.commandLine
        logger.debug('Kernel proc cmdLine: %s' % cmdLine)
        if cmdLine and cmdLine.startswith(_UNIX_KERNEL_NAME):
            logger.debug('Kernel is running without full path. Ignoring instance')
            raise applications.IgnoreApplicationException('Current kernel process is not valid.')


class BaseMaxdbPlugin(BasePlugin):
    def _getMainProcessName(self):
        raise NotImplementedError('_getMainProcessName')

    def isApplicable(self, context):
        return isinstance(context.client, shellutils.Shell)

    def process(self, context):
        r'''
         @types: applications.ApplicationSignatureContext
        '''
        shell = context.client
        kernelProcName = self._getMainProcessName()
        kernelProc = context.application.getProcess(kernelProcName)
        logger.debug('Kernel proc cmdLine: %s' % kernelProc.commandLine)
        fs = file_system.createFileSystem(shell)
        dbmCliWithPath = maxdb_discoverer.findDbmCliPath(fs, kernelProc.commandLine)
        dbmCli = maxdb_discoverer.getDbmCli(shell, dbmCliWithPath)
        appOsh = context.application.applicationOsh
        try:
            allDbEnums = dbmCli.db_enum().process()
        except maxdb_discoverer.DbmCliException, dce:
            logger.debugException(str(dce))
        else:
            dbEnums = filter(DbEnumResult.isOnline, allDbEnums) or allDbEnums
            equal_cmdlines = partial(_equals_cmdlines, kernelProc)
            currentDbEnum = findFirst(equal_cmdlines, dbEnums)
            if currentDbEnum:
                _update_instance_info(currentDbEnum, kernelProc, appOsh)
                _discover_paths(dbmCli, currentDbEnum.dbName, appOsh)
            else:
                msg = ('Current kernel process is not found '
                       'among registered database instances')
                raise applications.IgnoreApplicationException(msg)


def _equals_cmdlines(process, dbenum):
    '@types: Process, DbEnumResult -> bool'
    process_cmdline = process.commandLine.lower().strip('" ')
    dbenum_cmdline = dbenum.dependentPath.lower().strip('" ')
    return process_cmdline.startswith(dbenum_cmdline)


def _parse_major_minor_numbers(version):
    '@types: str -> tuple[int?, int?]'
    match = re.match('(\d+)\.(\d+)', version)
    if match:
        return tuple(match.groups())
    return [None, None]


def _update_instance_info(db_enum, kernel_process, osh):
    '@types: DbEnumResult, osh -> osh'
    osh.setAttribute('name', db_enum.dbName)
    osh.setAttribute('database_dbsid', db_enum.dbName)
    osh.setAttribute('startup_time', kernel_process.getStartupTime())
    return _update_version_information(db_enum, osh)


def _update_version_information(currentDbEnum, osh):
    '@types: DbEnumResult, osh -> osh'
    db_version = currentDbEnum.dbVersion
    if db_version:
        osh.setAttribute('application_version', db_version)
        details = _parse_major_minor_numbers(db_version)
        if all(details):
            version = '.'.join(details)
            osh.setAttribute('version', version)
            logger.debug('Discovered MAXDB version %s' % version)
    return osh


def _discover_paths(dbm_cli, db_name, osh):
    '''Discover application, program and data pathes for the current DB
    @types: DbmCli7_6, str, osh -> osh'''
    attrs = ('application_path', 'data_path', 'program_path')
    fns = (dbm_cli.get_isntallation_path,
           dbm_cli.get_indep_data_path,
           dbm_cli.get_indep_prog_path)
    paths = (Sfn(fn)(db_name=db_name) for fn in fns)
    attrname_to_value = ifilter(second, izip(attrs, paths))
    tuple(starmap(osh.setAttribute, attrname_to_value))
    return osh


class WinMaxdbPlugin(BaseMaxdbPlugin):
    def __init__(self):
        BaseMaxdbPlugin.__init__(self)

    def _getMainProcessName(self):
        return _WINDOWS_KERNEL_NAME

    def isApplicable(self, context):
        return context.client.isWinOs()


class UnixMaxdbPlugin(BaseMaxdbPlugin):
    def __init__(self):
        BaseMaxdbPlugin.__init__(self)

    def _getMainProcessName(self):
        return _UNIX_KERNEL_NAME

    def isApplicable(self, context):
        return not context.client.isWinOs()
