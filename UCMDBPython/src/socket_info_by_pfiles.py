# coding=utf-8
'''
Created on Sep 19, 2013

@author: ekondrashev
'''
from itertools import imap, ifilter
import re

import modeling
from fptools import identity
import command


def _parse_socket_descriptor(output):
    r'unicode -> (str?, str?, bool?, int?, str?, str?)'
    output_lower = output.lower()
    is_listen = None
    if 'peername' in output_lower or 'remaddr/port' in output_lower:
        is_listen = False
    elif 'listening' in output_lower or 'sockname' in output_lower:
        is_listen = True

    protocol_type = None
    if 'SOCK_STREAM' in output or 'PROTO_TCP' in output:
        protocol_type = modeling.TCP_PROTOCOL
    elif 'SOCK_DGRAM' in output or 'PROTO_UDP' in output:
        protocol_type = modeling.UDP_PROTOCOL

    local_match = re.search('sockname:\s*AF_INET6?\s*(.+?)\s*port:\s*(\d+)', output)
    if not local_match:
        local_match = re.search('localaddr/port\s+=\s+(.+?)/(\d+)', output)

    remote_match = re.search('peername:\s*AF_INET6?\s*(.+?)\s*port:\s*(\d+)', output)
    if not remote_match:
        remote_match = re.search('remaddr/port\s+=\s+(.+?)/(\d+)', output)

    local_ip = local_match and local_match.group(1).strip()
    local_port = local_match and local_match.group(2).strip()

    remote_ip = remote_match and remote_match.group(1).strip()
    remote_port = remote_match and remote_match.group(2).strip()

    return local_ip, local_port, is_listen, protocol_type, remote_ip, remote_port


def _parse_socket_descriptors(output, pid_marker):
    r'unicode, str -> generator((str?, (str?, str?, bool?, int?, str?, str?)))'
    output_ = re.split('%s(\d+)' % pid_marker, output)[1:]
    pid_to_output = [output_[i:i + 2] for i in xrange(0, len(output_), 2)]

    for pid, socket_infos in pid_to_output:
        socket_infos = socket_infos.strip()

        if socket_infos:
            socket_infos = re.split(('\s*\d+:\s*S_IFSOCK|'
                                    '\s*\d+:\s*S_ISSOCK'), socket_infos)
            for socket_descriptor in ifilter(identity, imap(unicode.strip, socket_infos)):
                yield pid, _parse_socket_descriptor(socket_descriptor)


def get_socket_descriptors(shell):
    r'''
    Discovers pid, local_addr, local_port, is_listen, protocol_type,
    remote_addr, remote_port using pfiles command for all the processes

    shellutils.Shell -> list[(str?, (str?, str?, bool?, int?, str?, str?))]
    @raise ValueError: if no shell passed
    @raise command.ExecutionException: on command execution failure
    @raise com.hp.ucmdb.discovery.library.clients.protocols.command.TimeoutException: on command timeout
    '''
    if not shell:
        raise ValueError('Invalid shell')

    marker = '_next_pid_marker_'
    cmdLine = ('for i in '
                '`ps -e|awk \'{if($4 != "<defunct>") if($1 != "PID") print $1}\'`;\n '
                  'do '
                    'echo %s$i; '
                    'nice pfiles $i 2>&1|awk "/S_ISSOCK|S_IFSOCK|SOCK_STREAM|SOCK_DGRAM|port/ { print }"; '
                  'done' % marker)

    result = []
    output = shell.execCmd(cmdLine, shell.getDefaultCommandTimeout() * 4)
    if shell.getLastCmdReturnCode() != 0:
        raise command.ExecuteException()

    for pid, socket_descriptor in _parse_socket_descriptors(output, marker):
        local_ip, local_port, is_listen, protocol_type, _, _ = socket_descriptor
        if local_ip and local_port is not None and is_listen is not None and protocol_type:
            result.append((pid, socket_descriptor))
    return result
