# coding=utf-8

from itertools import imap
from java.util import Date

import entity
import pyargs_validator


class StateEnum(entity.Immutable):
    STARTED = 1
    STOPPED = 0


def get_apppool_state(data):
    """

    :param data: raw state
    :type data: str or unicode
    :return: StateEnum.STARTED or StateEnum.STOPPED
    :rtype: int
    """
    return data.lower() == "stopped" and StateEnum.STOPPED or \
           data.lower() == "started" and StateEnum.STARTED or \
           None


class AppPool(entity.Immutable):

    @pyargs_validator.validate(basestring, basestring, pyargs_validator.optional(int))
    def __init__(self, id, name, state=None):
        """

        :param id: AppPool ID
        :type id: str or unicode
        :param name: AppPool
        :type name: str or unicode
        :param state: AppPool's state
        :type state: int
        """
        self.name = name
        self.state = state
        self.id = id

    def __repr__(self):
        return '%s(%s)' % (str(self.__class__), ', '.join(imap(repr,
                                                               (self.name,
                                                                self.state))))


class ConfigFile(entity.Immutable):

    @pyargs_validator.validate(basestring, basestring, pyargs_validator.optional(Date), pyargs_validator.optional(list))
    def __init__(self, fullpath, content=None, last_modified_time=None, db_sources=None):
        """

        :param fullpath: Full path to config file
        :type fullpath: str or unicode
        :param content: File's content
        :type content: str or unicode
        :param last_modified_time: Date
        :type last_modified_time: Date
        :param db_sources: list of Datasources which was found in the passed content
        :type db_sources: list[NamedDbSource]
        """
        self.fullpath = fullpath
        self.content = content
        self.last_modified_time = last_modified_time
        self.db_sources = db_sources

    def __repr__(self):
        return '%s(%s)' % (str(self.__class__), ', '.join(imap(repr,
                                                               (self.fullpath,
                                                                self.last_modified_time))))


class WebDir(entity.Immutable):

    @pyargs_validator.validate(basestring, basestring, pyargs_validator.optional(list))
    def __init__(self, resource_path, physical_path, config_files=None):
        """

        :param resource_path: Resource path - absolute path from root of website
        :type resource_path: str or unicode
        :param physical_path: Full physical path on the file syste,
        :type physical_path: str or unicode
        :param config_files: Collection of config files which was find under cur dir
        :type config_files: list[iis.ConfigFile]
        """
        self.path = resource_path
        self.physical_path = physical_path
        self.config_files = config_files
        self.name = self.__get_name(resource_path)
        self.root_path = self.__getRoot(resource_path)

    @pyargs_validator.validate(basestring)
    def __get_name(self, path):
        """

        :param path: resource path of folder
        :type path: str or unicode
        :return: last name of folder in the path
        :rtype: str or unicode
        """
        if not path:
            return None
        s = path.rstrip("/")
        pos = s.rfind("/")
        if pos != -1 and pos != len(path) - 1:
            return s[pos + 1:]
        else:
            return s

    @pyargs_validator.validate(basestring)
    def __getRoot(self, path):
        """

        :param path: resource path of folder
        :type path: str or unicode
        :return: first name of folder in the path
        :rtype: str or unicode
        """
        if not path:
            return None
        s = path.rstrip("/")
        pos = s.rfind("/")
        if pos != -1 and pos != len(path) - 1:
            return s[:pos] or None
        else:
            return None

    def __repr__(self):
        return '%s(%s)' % (str(self.__class__), ', '.join(imap(repr,
                                                               (self.path,
                                                                self.physical_path,
                                                                self.config_files))))


class WebApplication(WebDir):

    @pyargs_validator.validate(basestring,
                               basestring, basestring, list, list)
    def __init__(self, app_pool_name, resources_path, physical_path, config_files=None, virtual_dirs=None):
        """

        :param app_pool_name: name of pool which is used in the application
        :type app_pool_name: str or unicode
        :param resources_path: resource path of application
        :type resources_path: str or unicode
        :param physical_path: file system path to the application
        :type physical_path: str or unicode
        :param config_files: Collection of config files which are using in the applications
        :type config_files:  list(iis.ConfigFile)
        """
        WebDir.__init__(self, resources_path, physical_path, config_files)
        self.app_pool_name = app_pool_name
        self.virtual_dirs = virtual_dirs


class VirtualDir(WebDir): pass


class WebService(WebApplication):

    @pyargs_validator.validate(basestring, basestring, basestring, pyargs_validator.optional(list))
    def __init__(self, app_pool_name, resource_path, full_path, config_files=None):
        """

        :param app_pool_name: AppPool's name which is used by WebService
        :type app_pool_name: str or unicode
        :param resource_path: resource path of application
        :type resource_path: str or unicode
        :param full_path: file system full path to the application
        :type full_path: str or unicode
        :param config_files: Config files which are using by the application
        :type config_files: list[iis.ConfigFile]
        """
        WebApplication.__init__(self, app_pool_name, resource_path, full_path, config_files)


class Site(entity.Immutable):

    @pyargs_validator.validate(basestring, list, AppPool,
                               pyargs_validator.optional(int), pyargs_validator.optional(basestring),
                               pyargs_validator.optional(list), pyargs_validator.optional(list),
                               pyargs_validator.optional(list), pyargs_validator.optional(list))
    def __init__(self, name, bindings, app_pool, state=None, path=None, config_files=None, web_applications=None,
                 virtual_dirs=None, web_services=None):
        """

        :param name: Web site's name
        :type name: str or unicode
        :param bindings: list of list which include the 3 items - hostname, port, list of endpoint
        :type bindings: list[list]
        :param app_pool: App Pool information
        :type app_pool: iis.AppPool
        :param state: State
        :type state: int
        :param path: Physical path of the website
        :type path: str or unicode
        :param config_files: Config files which are using
        :type config_files: list(iis.ConfigFile)
        :param web_applications: List of application which are configured
        :type web_applications: list[iis.WebApplication]
        :param virtual_dirs: List of virtual dirs which are configured
        :type virtual_dirs: list[iis.VirtualDirectory]
        :param web_services: List of webservices which are configuref
        :type web_services: list[iis.WebService]
        """
        self.name = name
        self.app_pool = app_pool
        self.bindings = bindings
        self.state = state
        self.path = path
        self.config_files = config_files
        self.web_applications = web_applications
        self.virtual_dirs = virtual_dirs
        self.web_services = web_services

    def is_ftp(self):
        protocols = imap(lambda obj: obj and obj[1].lower(), self.bindings)
        return 'ftp' in protocols

    def __repr__(self):
        return '%s(%s)' % (str(self.__class__), ', '.join(imap(repr,
                                                               (self.name,
                                                                self.bindings,
                                                                self.app_pool,
                                                                self.state,
                                                                self.path,
                                                                self.config_files,
                                                                self.web_applications,
                                                                self.virtual_dirs,
                                                                self.web_services))))
