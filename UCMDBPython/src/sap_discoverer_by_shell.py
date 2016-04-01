'''
Created on May 21, 2013

@author: vvitvitskiy
'''

import re
import sap
import sap_discoverer
import logger
from process_discoverer import ProcessCwdDiscovererOnUnixByShell
from fptools import safeFunc as Sfn
import file_system
import file_topology
import os


def execute_cmd(shell, cmd):
    '''
    @types: shellutils.Shell, sap_discoverer.Cmd -> object
    @raise CommandException: Command execution failed
    '''
    output = shell.execCmd(str(cmd))
    if shell.getLastCmdReturnCode():
        raise CommandException(output)
    return cmd.parse(output)


class CommandException(Exception):
    "Base exception class for all commands"
    pass


class Cmd:
    ''' Abstact shell command'''
    def parse(self, output):
        raise NotImplementedError()


class GetVersionInfoCmd:

    RELEASE_VERSION_REGEX = re.compile(r'.*release\s+(.+)')
    PATCH_NUMBER_REGEX = re.compile(r'patch number:?\s+(\d+)')
    PATCH_LEVEL_REGEX = None

    def __init__(self, bin_path, use_ld_library_path=False):
        if not bin_path:
            raise ValueError("Bin-path for jstart command is not specified")
        self.__bin_path = bin_path
        self.__use_ld_library_path = use_ld_library_path

    def __str__(self):
        return self.__get_command_line(self.__bin_path, self.__use_ld_library_path)

    def __get_command_line(self, bin_path, use_ld_library_path=False):
        cmd = self.get_command_line(bin_path)
        # This is a solution demanded by SAP, provided that
        # the libraries are located in the same folder as binary file
        if use_ld_library_path:
            dir_path = os.path.dirname(bin_path)
            cmd = "LD_LIBRARY_PATH=$LD_LIBRARY_PATH:%s %s" % (dir_path, cmd)
        return cmd

    def get_command_line(self, bin_path):
        return '"%s" -v' % bin_path

    def parse(self, output):
        '@types: str -> sap.VersionInfo?'
        file_content_lines = output.splitlines()
        kernel_release = None
        patch_number = None
        patch_level = None
        for line in file_content_lines:
            level_match = (self.PATCH_LEVEL_REGEX
                           and re.match(self.PATCH_LEVEL_REGEX, line))
            match = re.match(self.RELEASE_VERSION_REGEX, line)
            if match:
                kernel_release = match.group(1)
            elif level_match:
                patch_level = level_match.group(1)
            else:
                found_patch_number = re.match(self.PATCH_NUMBER_REGEX, line)
                if found_patch_number:
                    patch_number = found_patch_number.group(1)
        if kernel_release:
            return sap.VersionInfo(kernel_release, patchNumber=patch_number,
                                   patchLevel=patch_level)



def get_process_bin_path(shell, process, system_home_folder=None, instance_name=None):
    '''
    Get executable path for Win or Unix like system
    r@types: shellutils.Shell, process.Process, str, str -> str
    '''
    if shell.isWinOs():
        bin_path = process.executablePath or process.getName()
    else:
        discoverer = ProcessCwdDiscovererOnUnixByShell(shell)
        working_dir_path = Sfn(discoverer.getWorkingDirByReadlinkInProc,
                              fallbackFn=Sfn(discoverer.getWorkingDirByCwd,
                                   fallbackFn=Sfn(discoverer.getWorkingDirByPwdInProc,
                                         fallbackFn=Sfn(discoverer.getWorkingDirByPwdx)))
                               )(process.getPid())
        logger.debug('Working directory path %s' % working_dir_path)
        if working_dir_path:
            bin_path = '%s/%s' % (working_dir_path, process.getName())
        else:
            bin_path = process.getName()

            if system_home_folder and instance_name:
                bin_path = '%s/%s/exe/%s' % (system_home_folder, instance_name, process.getName())
    return bin_path


def get_process_executable_path(shell, pf_path, process, system):
    '''
    Get process executable path
    @types: shellutils.Shell, str, process.Process, sap.System
    '''
    sys_name = system.getName()
    root_path = sap_discoverer.findSystemBasePath(pf_path, sys_name)
    inst_name = None
    if system.getInstances():
        inst = system.getInstances()[0]
        inst_name = '%s%s' % (inst.getName(), inst.getNumber())
    return get_process_bin_path(shell, process, root_path, inst_name)


def discover_default_pf(shell, pf_path, system_name):
    '''
    Discover DEFAULT.PFL for particular system based on any profile path of
    this system.
    @return: pair of profile path and its parsed content
    @types: shellutils.Shell, str, str -> (File?, sap_discoverer.IniDocument?)
    '''
    _info = (system_name, pf_path)
    logger.info("Discover DEFAULT.pl for %s system based on %s" % _info)
    pathtool = file_system.getPathToolByShell(shell)
    root_path = sap_discoverer.findSystemBasePath(pf_path, system_name)
    sys_layout = sap_discoverer.Layout(pathtool, root_path, system_name)
    default_pf_path = sys_layout.getDefaultProfileFilePath()
    logger.info("Default profile path found: %s" % default_pf_path)
    return read_pf(shell, default_pf_path)


def read_pf(shell, pf_path):
    '@types: Shell, str -> tuple[File, sap_discoverer.IniDocument]'
    try:
        pathtool = file_system.getPathTool(file_system.createFileSystem(shell))
        name = pathtool.baseName(pf_path)
        file_ = file_topology.File(name, False)
        file_.content = shell.safecat(pf_path)
        file_.path = pf_path
    except Exception, e:
        logger.warnException("Failed to read profile: %s" % e)
    else:
        return file_, sap_discoverer.IniParser.parseIniDoc(file_.content)
    return (None, None)
