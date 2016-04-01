'''
Created on Feb 19, 2014

@author: ekondrashev
'''
import command
from command import ChainedCmdlet

from pyargs_validator import not_none, validate
import ioscan
import fcmsutil


@validate(not_none, not_none)
def get_remote_fc_hba_descriptors(shell, device_filename):
    r'''
    Discovers fibre channel info using ioscan and fcmsutil commands
    shellutils.Shell, str -> tuple[fcmsutil.RemoteOptionDescriptor]]
    @raise ValueError: if no shell passed
    @raise command.ExecutionException: on command execution failure
    @raise com.hp.ucmdb.discovery.library.clients.protocols.command.TimeoutException: on command timeout
    '''
    executor = ChainedCmdlet(command.getExecutor(shell),
                             command.cmdlet.produceResult)

    fcmsutil_cmd = fcmsutil.Cmd(device_filename=device_filename)
    return fcmsutil_cmd.remote() | executor


@validate(not_none)
def get_fc_hba_descriptors(shell):
    r'''
    Discovers fibre channel info using ioscan and fcmsutil commands
    shellutils.Shell -> tuple[tuple[ioscan.fOptionDescriptor, fcmsutil.FcmsutilDescriptor, fcmsutil.FcmsutilVpdOptionDescriptor]]
    @raise ValueError: if no shell passed
    @raise command.ExecutionException: on command execution failure
    @raise com.hp.ucmdb.discovery.library.clients.protocols.command.TimeoutException: on command timeout
    '''
    executor = ChainedCmdlet(command.getExecutor(shell),
                             command.cmdlet.produceResult)
    cmd = ioscan.Cmd().fnC('fc')
    ioscan_result = cmd | executor

    result = []
    for ioscan_result_descriptor in ioscan_result:
        device_filename = ioscan_result_descriptor.device_filename
        fcmsutil_cmd = fcmsutil.Cmd(device_filename=device_filename)
        fc_descriptor = fcmsutil_cmd | executor
        fc_vpd_descriptor = fcmsutil_cmd.vpd() | executor
        result.append((ioscan_result_descriptor, fc_descriptor, fc_vpd_descriptor))

    return tuple(result)

