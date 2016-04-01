# coding=utf-8
from functools import partial
from itertools import imap, ifilter, izip
from operator import attrgetter

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
import iis
from iteratortools import iflatten, flatten
import logger
import modeling
import netutils
import re


IIS_VENDOR = 'microsoft_corp'


class TopologyBuilder:
    def buildWebSite(self, website):
        """

        :param website: WebSite object
        :type website: iis.Site
        :return: ObjectStateHolder
        :rtype: ObjectStateHolder
        """
        iiswebsiteOSH = ObjectStateHolder('iiswebsite')
        iiswebsiteOSH.setAttribute('name', website.name)
        if website.path:
            iiswebsiteOSH.setAttribute('path', website.path)
        if website.app_pool:
            iiswebsiteOSH.setAttribute('app_pool_id', website.app_pool.name)
        return iiswebsiteOSH

    def buildFTPSite(self, ftpsite, iis_version=None):
        iisFtpServerOSH = ObjectStateHolder('iis_ftp_server')
        iisFtpServerOSH.setAttribute('data_name', 'Microsoft IIS FTP Server')
        # iisFtpServerOSH.setIntegerAttribute('max_connections', MaxConnections)
        # iisFtpServerOSH.setBoolAttribute('anonymous_password_sync', AnonymousPasswordSync)
        iisFtpServerOSH.setAttribute('vendor', IIS_VENDOR)
        if iis_version:
            iisFtpServerOSH.setAttribute('application_version_number', str(iis_version))
        return iisFtpServerOSH

    def buildConfigFile(self, config_file):
        """

        :param config_file: Cofiguration File information
        :type config_file: iis.ConfigFile
        :return: ObjectStateHolder
        :rtype: ObjectStateHolder
        """
        configLocation = config_file.fullpath
        matches = re.match('.*\\\\(.*)',configLocation)
        name = 'web.config'
        if matches:
            name = matches.group(1)
            logger.debug("reporting config file:", name)

        content = config_file.content
        lastModificationDate = config_file.last_modified_time
        return modeling.createConfigurationDocumentOSH(name, configLocation, content,
                                                       None, modeling.MIME_TEXT_XML,
                                                       lastModificationDate, "IIS configuration file")
    def buildAppWebService(self, config_file,webservice_ext_filter=[]):
        configLocation = config_file.fullpath
        matches = re.match('.*\\\\(.*)\.(.*)',configLocation)
        name = ''
        ext = ''
        if matches:
            name = matches.group(1)
            ext = matches.group(2)
            logger.debug("found config file:%s\.%s"%(name,ext))

        if ext and ext in webservice_ext_filter:
            logger.debug("reporting webservice:", name)
            osh = ObjectStateHolder('webservice')
            osh.setAttribute('service_name', name)
            osh.setAttribute('name', name)
            return osh
        else:
            return None

    def buildAppPool(self, app_pool):
        """

        :param app_pool: Application Pool information
        :type app_pool: iis.AppPool
        :return: ObjectStateHolder
        :rtype: ObjectStateHolder
        """
        iisapppoolOSH = ObjectStateHolder('iisapppool')
        iisapppoolOSH.setAttribute('data_name', app_pool.name)
        return iisapppoolOSH


    def buildApplication(self, web_app):
        """

        :param web_app:
        :type web_app: iis.WebApplication
        :return:
        :rtype:
        """
        iiswebdirOSH = ObjectStateHolder('iiswebdir')
        iiswebdirOSH.setAttribute('data_name', web_app.name or "Root")
        iiswebdirOSH.setAttribute('application_name', web_app.name)
        iiswebdirOSH.setAttribute('app_root', web_app.root_path or "/")
        iiswebdirOSH.setAttribute('resource_path', web_app.path or "/")
        iiswebdirOSH.setAttribute('path', web_app.physical_path)
        return iiswebdirOSH

    def buildVirtualDirectory(self, web_dir):
        """

        :param web_dir: Virtual Directory information
        :type web_dir: iis.VirtualDir
        :return: ObjectStateHolder
        :rtype: ObjectStateHolder
        """
        iisvirtualdirOSH = ObjectStateHolder('iisvirtualdir')
        iisvirtualdirOSH.setAttribute('data_name', web_dir.path)
        iisvirtualdirOSH.setAttribute('path', web_dir.physical_path)
        iisvirtualdirOSH.setAttribute('application_name', web_dir.name)
        iisvirtualdirOSH.setAttribute('app_root', web_dir.root_path or "/")
        iisvirtualdirOSH.setAttribute('resource_path', web_dir.path or "/")
        return iisvirtualdirOSH

    def buildWebService(self, web_service):
        """

        :param web_service:
        :type web_service: iis.WebService
        :return: ObjectStateHolder
        :rtype: ObjectStateHolder
        """
        iiswebserviceOSH = ObjectStateHolder('iiswebservice')
        iiswebserviceOSH.setAttribute('data_name', web_service.name)
        # iiswebserviceOSH.setBoolAttribute('allow_keep_alive', valuesMap[WEBSERVER_KEY_ALLOW_KEEP_ALIVE])
        # iiswebserviceOSH.setBoolAttribute('anonymous_password_sync', valuesMap[WEBSERVER_KEY_ANONYMOUS_PASSWORD_SYNC])
        # iiswebserviceOSH.setAttribute('app_pool_id', valuesMap[WEBSERVER_KEY_APP_POOL_ID])
        return iiswebserviceOSH


class TopologyReporter:
    def __init__(self, builder, endpoint_reporter, odbc_reporter=None, odbc_cache=None):
        """

        :param builder: Topology builder
        :type builder: TopologyBuilder
        :param endpoint_reporter: Endpoint's Topology reporter
        :type endpoint_reporter: netutils.EndpointReporter
        """
        self._builder = builder
        self._endpoint_reporter = endpoint_reporter
        self._odbc_reporter = odbc_reporter
        self._odbc_cache = odbc_cache or {}

    def __set_container(self, osh, parentOsh):
        osh.setContainer(parentOsh)
        return osh

    def reportAppPools(self, app_pools_list, parentOsh):
        """

        :param app_pools_list:
        :type app_pools_list: list[iis.AppPool]
        :param parentOsh: ObjectStateHolder
        :type parentOsh: ObjectStateHolder
        :return: dict[ObjectStateHolder]
        :rtype: dict[ObjectStateHolder]
        """
        # build AppPool OSH
        oshs = imap(self._builder.buildAppPool, app_pools_list)
        # set container for each built OSH
        func = partial(self.__set_container, parentOsh=parentOsh)
        oshs = imap(func, oshs)
        return dict(izip(imap(attrgetter('name'), app_pools_list), oshs))

    def reportWebSite(self, website, parentOsh, iis_version):
        """

        :param website:
        :type website: iis.Site
        :param parentOsh: ObjectStateHolder
        :type parentOsh: ObjectStateHolder
        :param iis_version: IIS version (for FTP reporting)
        :type iis_version: str or unicode
        :return: ObjectStateHolder
        :rtype: ObjectStateHolder
        """

        if website.is_ftp():
            websiteOsh = self._builder.buildFTPSite(website, iis_version)
        else:
            websiteOsh = self._builder.buildWebSite(website)
        websiteOsh.setContainer(parentOsh)
        return websiteOsh


    def reportWebSites(self, web_sites_list, parentOsh, iis_version):
        report_func = partial(self.reportWebSite, parentOsh=parentOsh, iis_version=iis_version)
        oshs = imap(report_func, web_sites_list)
        return dict(izip(imap(attrgetter('name'), web_sites_list), oshs))

    def reportVirtualDir(self, dir, parent_osh):
        osh = self._builder.buildVirtualDirectory(dir)
        osh.setContainer(parent_osh)
        return [osh]

    def reportWebDir(self, web_app, parent_osh, app_pools_map=None, webservice_ext_filter = []):
        """

        :param web_app:
        :type web_app: iis.WebApplication
        :param parent_osh:
        :type parent_osh:
        :param app_pools_map:
        :type app_pools_map:
        :return:
        :rtype:
        """
        oshs = []
        osh = self._builder.buildApplication(web_app)
        osh.setContainer(parent_osh)
        oshs.append(osh)
        if app_pools_map:
            app_pool_osh = app_pools_map.get(web_app.app_pool_name)
            if app_pool_osh:
                oshs.append(modeling.createLinkOSH("deployed", osh, app_pool_osh))
        if web_app.config_files:
            oshs.extend(self.reportConfigFiles(web_app.config_files, osh))
            #report webservice using webservice config file
            oshs.extend(self.reportWebServices(web_app.config_files, osh, webservice_ext_filter))
        if web_app.virtual_dirs:
            func = partial(self.reportVirtualDir, parent_osh=osh)
            oshs.extend(iflatten(ifilter(None, imap(func, web_app.virtual_dirs))))
        return oshs

    def reportTopology(self, app_pools_list, web_sites_list, parentOsh, iis_version=None, webservice_ext_filter=[]):
        """

        :param web_sites_list: List of WebSites which was discovered
        :type web_sites_list: list[iis.Site]
        :param parentOsh: parent OSH for each website
        :type parentOsh: ObjectStateHolder
        :return: list[ObjectStateHolder]
        :rtype: list[ObjectStateHolder]
        """
        result = []
        apppool_map = self.reportAppPools(app_pools_list, parentOsh)
        sites_map = self.reportWebSites(web_sites_list, parentOsh, iis_version)
        result.extend(sites_map.values())
        result.extend(apppool_map.values())

        # report VirtualDir and WebDirs(WebApplication)
        for site in web_sites_list:
            web_site_osh = sites_map.get(site.name)
            if not site.is_ftp():
                # report root web dir
                root_web_dir = iis.WebApplication("Root", "/", site.path, site.config_files)
                root_osh = self._builder.buildApplication(root_web_dir)
                root_osh.setContainer(web_site_osh)
                result.append(root_osh)
                if apppool_map:
                    app_pool_osh = apppool_map.get(site.app_pool.name)
                    if app_pool_osh:
                        result.append(modeling.createLinkOSH("deployed", root_osh, app_pool_osh))

                # report config files
                result.extend(self.reportConfigFiles(site.config_files, root_osh))

                # report virtual dirs
                report_virtual_dirs = partial(self.reportVirtualDir, parent_osh=root_osh)
                result.extend(iflatten(ifilter(None, imap(report_virtual_dirs, site.virtual_dirs))))

                # report Webdirs = WebApplications
                report_web_application = partial(self.reportWebDir, parent_osh=root_osh, app_pools_map=apppool_map, webservice_ext_filter=webservice_ext_filter)
                result.extend(iflatten(ifilter(None, imap(report_web_application, site.web_applications))))

            bindings = flatten(
                ifilter(None, imap(lambda binding: binding[1].lower() in ['http', 'https', 'ftp'] and binding[2],
                                   site.bindings)))
            result.extend(self.reportBindings(bindings, web_site_osh, parentOsh))

        return result

    def reportConfigFiles(self, config_files, parent_osh):
        oshs = imap(self._builder.buildConfigFile, config_files)
        func = partial(self.__set_container, parentOsh=parent_osh)
        oshs = map(func, oshs)

        db_sources = flatten(imap(attrgetter('db_sources'), config_files))
        oshs.extend(self.reportDatabaseSources(db_sources, parent_osh))
        return oshs

    def reportWebServices(self, config_files, parent_osh, webservice_ext_filter = []):
        oshs = []
        for config_file in config_files:
            osh = self._builder.buildAppWebService(config_file, webservice_ext_filter)
            if osh:
                osh.setContainer(parent_osh)
                oshs.append(osh)
                oshs.append(modeling.createLinkOSH("dependency",osh, parent_osh))

        return oshs

    def reportDatabaseSources(self, database_sources, parent_osh):
        from NTCMD_IIS import NamedDbDataSource

        oshs = []
        for dataSource in database_sources:
            if dataSource:
                if isinstance(dataSource, NamedDbDataSource):
                    dsn_info = self._odbc_cache.get(dataSource.getName())
                    if dsn_info and self._odbc_reporter:
                        oshs.extend(self._odbc_reporter.reportDatabaseTopology(dsn_info, parent_osh))
                    else:
                        logger.warn("Cannot report %s DSN. Skip!" % dataSource.getName())
                        if self._odbc_cache:
                            logger.reportWarning("ODBC don't have configuration for DSN which was specified in an application")
                        else:
                            logger.reportWarning("Cannot retrieve ODBC information from system registry")
                else:
                    vector = ObjectStateHolderVector()
                    dataSource.addResultsToVector(parent_osh, vector)
                    oshs.extend(vector)
        return oshs

    def reportBinding(self, binding, parentOsh, useObjectsOshs):
        result = []
        endpoint_osh = self._endpoint_reporter.reportEndpoint(binding, parentOsh)
        result.append(endpoint_osh)
        for osh in useObjectsOshs:
            result.append(modeling.createLinkOSH("usage", osh, endpoint_osh))
        return result

    def reportBindings(self, bindings, web_site_osh, iis_osh):
        """

        :param bindings:
        :type bindings: list[netutils.Endpoint]
        :param web_site_osh:
        :type web_site_osh:
        :param iis_osh:
        :type iis_osh:
        :return:
        :rtype:
        """
        result = []
        for binding in bindings:
            host_osh = self._endpoint_reporter.reportHostFromEndpoint(binding)
            result.append(host_osh)
            result.extend(self.reportBinding(binding, host_osh, [web_site_osh, iis_osh]))
        return result
