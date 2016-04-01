# coding=utf-8
'''
Created on Aug 14, 2014

@author: ekondrashev
'''
import command
import fptools
from functools import partial
import collections
from iteratortools import first
import post_import_hooks
import logger
from service_loader import load_service_providers_by_file_pattern
from fptools import safeFunc as Sfn
import service_loader
import webseal_wiring
import re


class Error(Exception):
    pass


def raise_on_error(output):
    if output.startswith('Error:'):
        raise Error(output)
    return output


class Cmd(command.BaseCmd):
    '''
    A base class for pdadmin subcommands defining BIN static attribute to hold
    the sub-command string and overriding initializer method to add subcommand
    to the options list.

    All child classes should override BIN attribute with correct value.
    '''
    DEFAULT_HANDLERS = (command.BaseCmd.DEFAULT_HANDLERS +
                        (
#                          command.cmdlet.raiseOnNonZeroReturnCode,
                        command.cmdlet.raiseWhenOutputIsEmpty,
                        command.cmdlet.stripOutput,
                        raise_on_error,
                        fptools.methodcaller('splitlines'),
                        partial(map, fptools.methodcaller('strip'))
#                          command.parser.groupby_unique_key,
                         ))

    BIN = ''

    def __init__(self, options=None, handler=None):
        '''
        @param bin: file path to binary
        @type bin: basestring or file_system.Path
        @param options: list of fcinfo options
        @type options: list[str]
        @param handler: handler to use for current command
        @type handler: callable[command.Result] -> ?.
            The default handler returns `pdadmin` command output splitted by lines
        '''
        self.options = options or []
        command.BaseCmd.__init__(self, self._build_cmdline(),
                                     handler=handler)

    def _build_cmdline(self):
        return ' '.join([self.BIN, ] + self.options)

    def _with_option(self, option, handler=None):
        handler = handler or self.handler
        options = self.options[:]
        options.append(option)
        return Cmd(options, handler)

    def is_applicable(self):
        raise NotImplementedError('is_applicable')

    @staticmethod
    def find(tools):
        impls = service_loader.global_lookup[Cmd]
        for impl in impls:
            is_applicable = webseal_wiring.wired()(impl.is_applicable)
            if Sfn(is_applicable)(**tools):
                return impl.create(**tools)

        raise service_loader.NoImplementationException('No pdadmin impl found')

    @staticmethod
    @webseal_wiring.wired()
    def create(*args, **kwargs):
        raise NotImplementedError('create')

    @property
    def server(self):
        return Server(self)


class SubCmd(object):
    def __init__(self, parentcmd):
        self.parentcmd = parentcmd


class Server(SubCmd):

    Descriptor = collections.namedtuple('Descriptor', ('name',
                                                       'description',
                                                       'hostname',
                                                       'principal',
                                                       'admin_request_port',
                                                       'is_listening_for_auth_db_update_notifications',
                                                       'azn_admin_services'))

    @staticmethod
    def parse_show(lines):
        #first line is a server name
        name = lines[0]
        lines = lines[1:]
        grouped = first(command.parser.groupby_unique_key(lines))
        hostname = grouped.get('Hostname')
        description = grouped.get('Description')
        principal = grouped.get('Principal')
        admin_request_port = grouped.get('Administration Request Port')
        is_listening = grouped.get('Listening for authorization database update notifications')

        azn_admin_services = lines[lines.index('AZN Administration Services:') + 1:]
        return Server.Descriptor(name, description, hostname, principal,
                                 admin_request_port, is_listening,
                                 tuple(azn_admin_services))

    @property
    def list(self):
        return self.parentcmd._with_option('server list')

    def show(self, name):
        handlers = (self.parentcmd.handler, self.parse_show, )
        handler = self.parentcmd.compose_handler(handlers)
        return self.parentcmd._with_option('server show %s' % name, handler)

    class Task(SubCmd):
        def __init__(self, parentcmd, server):
            self.parentcmd = parentcmd
            self.server = server

        JunctionDescriptor = collections.namedtuple('JunctionDescriptor',
                                                    ('name', 'type',
                                                     'hard_limit', 'soft_limit',
                                                     'active_worker_threads',
                                                     'basic_authentication_mode',
                                                     'forms_based_sso',
                                                     'tfim_junction_sso',
                                                     'authentication_http_header',
                                                     'remote_address_http_header',
                                                     'stateful_junction',
                                                     'boolean_rule_header',
                                                     'scripting_support',
                                                     'preserve_cookie_names',
                                                     'cookie_names_include_path',
                                                     'transparent_path_junction',
                                                     'delegation_support',
                                                     'mutually_authenticated',
                                                     'insert_websphere_ltpa_cookies',
                                                     'insert_webseal_session_cookies',
                                                     'request_encoding',
                                                     'servers'))
        JunctionServerDescriptor = collections.namedtuple('JunctionServerDescriptor',
                                                          ('number', 'id', 'state',
                                                           'operational_state',
                                                           'hostname', 'port',
                                                           'virtual_hostname',
                                                           'dn', 'local_ip_address',
                                                           'query_contents_url',
                                                           'query_contents',
                                                           'case_insensitive_urls',
                                                           'allow_windows_style_urls',
                                                           'current_requests',
                                                           'total_requests'
                                                           ))

        @property
        def list(self):
            return self.parentcmd._with_option('server task %s list' % self.server, self.parentcmd.handler)

        @classmethod
        def parse_show(cls, lines):
            server_def_indexes = []
            i = None
            for i, line in enumerate(lines):
                m = re.match('Server (\d+):', line)
                if m:
                    server_def_indexes.append((i, m.group(1)))

            servers_by_number = {}
            junction_lines = lines
            if server_def_indexes:
                pindex, number = server_def_indexes[0]

                #for i to be defined in else statement if only one server definition available
                i = pindex
                for i, number in server_def_indexes[1:]:
                    servers_by_number[number] = lines[pindex: i]
                    pindex = i
                else:
                    servers_by_number[number] = lines[i:]

            junction_info = command.parser.groupby_unique_key(junction_lines)[0]

            name = junction_info.get('Junction point')
            type_ = junction_info.get('Type')
            hard_limit = junction_info.get('Junction hard limit')
            soft_limit = junction_info.get('Junction soft limit')
            active_worker_threads = junction_info.get('Active worker threads')
            basic_authentication_mode = junction_info.get('Basic authentication mode')
            forms_based_sso = junction_info.get('Forms based SSO')
            tfim_junction_sso = junction_info.get('TFIM junction SSO')
            authentication_http_header = junction_info.get('Authentication HTTP header')
            remote_address_http_header = junction_info.get('Remote Address HTTP header')
            stateful_junction = junction_info.get('Stateful junction')
            boolean_rule_header = junction_info.get('Boolean Rule Header')
            scripting_support = junction_info.get('Scripting support')
            preserve_cookie_names = junction_info.get('Preserve cookie names')
            cookie_names_include_path = junction_info.get('Cookie names include path')
            transparent_path_junction = junction_info.get('Transparent Path junction')
            delegation_support = junction_info.get('Delegation support')
            mutually_authenticated = junction_info.get('Mutually authenticated')
            insert_websphere_ltpa_cookies = junction_info.get('Insert WebSphere LTPA cookies')
            insert_webseal_session_cookies = junction_info.get('Insert WebSEAL session cookies')
            request_encoding = junction_info.get('Request Encoding')
            servers = []
            for number, server_lines in servers_by_number.items():
                server_info = command.parser.groupby_unique_key(server_lines)[0]
                total_requests = server_info.get('Total requests')
                query_contents = server_info.get('Query-contents')
                allow_windows_style_urls = server_info.get('Allow Windows-style URLs')
                case_insensitive_urls = server_info.get('Case insensitive URLs')
                query_contents_url = server_info.get('Query_contents URL')
                id_ = server_info.get('ID')
                local_ip_address = server_info.get('local IP address')
                server_state = server_info.get('Server State')
                current_requests = server_info.get('Current requests')
                hostname = server_info.get('Hostname')
                port = server_info.get('Port')
                virtual_hostname = server_info.get('Virtual hostname')
                server_dn = server_info.get('Server DN')
                operational_state = server_info.get('Operational State')
                server = cls.JunctionServerDescriptor(number=number,
                                                      id=id_,
                                                      state=server_state,
                                                      operational_state=operational_state,
                                                      hostname=hostname,
                                                      port=port,
                                                      virtual_hostname=virtual_hostname,
                                                      dn=server_dn,
                                                      local_ip_address=local_ip_address,
                                                      query_contents_url=query_contents_url,
                                                      query_contents=query_contents,
                                                      case_insensitive_urls=case_insensitive_urls,
                                                      allow_windows_style_urls=allow_windows_style_urls,
                                                      current_requests=current_requests,
                                                      total_requests=total_requests)
                servers.append(server)
            junction = cls.JunctionDescriptor(name=name,
                                             type=type_,
                                             hard_limit=hard_limit,
                                             soft_limit=soft_limit,
                                             active_worker_threads=active_worker_threads,
                                             basic_authentication_mode=basic_authentication_mode,
                                             forms_based_sso=forms_based_sso,
                                             tfim_junction_sso=tfim_junction_sso,
                                             authentication_http_header=authentication_http_header,
                                             remote_address_http_header=remote_address_http_header,
                                             stateful_junction=stateful_junction,
                                             boolean_rule_header=boolean_rule_header,
                                             scripting_support=scripting_support,
                                             preserve_cookie_names=preserve_cookie_names,
                                             cookie_names_include_path=cookie_names_include_path,
                                             transparent_path_junction=transparent_path_junction,
                                             delegation_support=delegation_support,
                                             mutually_authenticated=mutually_authenticated,
                                             insert_websphere_ltpa_cookies=insert_websphere_ltpa_cookies,
                                             insert_webseal_session_cookies=insert_webseal_session_cookies,
                                             request_encoding=request_encoding,
                                             servers=servers)
            return junction
#
#             Junction point: /g_junction
# Type: TCP
# Junction hard limit: 0 - using global value
# Junction soft limit: 0 - using global value
# Active worker threads: 0
# Basic authentication mode: filter
# Forms based SSO: disabled
# TFIM junction SSO: no
# Authentication HTTP header: do not insert
# Remote Address HTTP header: do not insert
# Stateful junction: no
# Boolean Rule Header: no
# Scripting support: no
# Preserve cookie names: no
# Cookie names include path: no
# Transparent Path junction: no
# Delegation support: no
# Mutually authenticated: no
# Insert WebSphere LTPA cookies: no
# Insert WebSEAL session cookies: no
# Request Encoding: UTF-8, URI Encoded
# Server 1:
# ID: 148e2aa4-3f3c-11e4-a096-000c29368982
# Server State: running
# Operational State: Online
# Hostname: 173.194.113.192
# Port: 80
# Virtual hostname: 173.194.113.192
# Server DN:
# local IP address:
# Query_contents URL: /cgi-bin/query_contents
# Query-contents: unknown
# Case insensitive URLs: no
# Allow Windows-style URLs: yes
# Current requests : 0
# Total requests : 27

        def show(self, junction_name):
            handlers = (self.parentcmd.handler, self.parse_show, )
            handler = self.parentcmd.compose_handler(handlers)
            return self.parentcmd._with_option('server task %s show %s' % (self.server, junction_name), handler)

    def task(self, server):
        return self.Task(self.parentcmd, server)


@post_import_hooks.invoke_when_loaded(__name__)
def __load_plugins(module):
    logger.debug('Loading pdadmin implementations')
    load_service_providers_by_file_pattern('*pdadmin*_impl.py')
