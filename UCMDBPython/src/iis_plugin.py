# -*- coding: UTF-8 -*-
from collections import defaultdict
from xml.etree import ElementTree as ET
import re
import logger

CMD_PATH = r'%windir%\system32\inetsrv\appcmd.exe'


def parseConfigFile(shell, filePath, fileName, fileContent, variableResolver):
    siteName = fileContent.strip()
    logger.debug('Narrow IIS discovery to site \'%s\' by port.' % siteName)
    vdirs = discoverVdirs(shell)
    apps = discoverApps(shell, vdirs).get(siteName)
    if apps:
        findIISPluginPhysicalPaths(apps, variableResolver)
        findMatchedPhysicalPaths(apps, variableResolver)


def discoverVdirs(shell):
    COMMAND = CMD_PATH + ' list vdir /xml'
    result = shell.execCmd(COMMAND)
    if shell.getLastCmdReturnCode() == 0 and result:
        vdirs = parseVdirs(result)
        logger.debug('Vdir:', vdirs)
        return vdirs
    else:
        return {}


def parseVdirs(result):
    root = ET.fromstring(result)
    vdirElements = root.findall('VDIR')

    vdirsOfApps = defaultdict(list)
    for vdirElement in vdirElements:
        path = vdirElement.get('path')
        physicalPath = vdirElement.get('physicalPath')
        appName = vdirElement.get('APP.NAME')
        vdir = Vdir(path, physicalPath)
        vdirs = vdirsOfApps[appName]
        vdirs.append(vdir)
    return vdirsOfApps


def discoverApps(shell, vdirs):
    COMMAND = CMD_PATH + ' list app /xml'
    result = shell.execCmd(COMMAND)
    if shell.getLastCmdReturnCode() == 0 and result:
        apps = parseApps(result, vdirs)
        logger.debug('Apps:', apps)
        return apps
    else:
        return {}


def parseApps(result, vdirs):
    root = ET.fromstring(result)
    appElements = root.findall('APP')

    appOfSites = defaultdict(list)
    for appElement in appElements:
        name = appElement.get('APP.NAME')
        appPath = appElement.get('path')
        siteName = appElement.get('SITE.NAME')
        vdirsOfApp = vdirs.get(name)
        app = App(appPath, vdirsOfApp)
        apps = appOfSites[siteName]
        apps.append(app)

    return appOfSites


def findIISPluginPhysicalPaths(apps, variableResolver):
    for app in apps:
        for vdir in app.vdirs:
            if vdir.path == '/sePlugins':  # IIS plugins for WebSphere
                logger.debug('Found IIS plugins for WebSphere on virtual directory \'%s\'.' % vdir.path)
                variableResolver.add('sePluginsPath', vdir.physicalPath)

            if vdir.path == '/jakarta':  # IIS plugins for Tomcat
                logger.debug('Found IIS plugins for Tomcat on virtual directory \'%s\'.' % vdir.path)
                variableResolver.add('tomcatPluginPath', vdir.physicalPath)


def findMatchedPhysicalPaths(apps, variableResolver):
    for context in variableResolver.get('scp.context'):
        sortedApps = sorted(apps, key=lambda app: len(app.path.split('/')))  # Sort applications by app path levels
        for app in reversed(sortedApps):  # Match application path from the most levels to the least levels
            pattern = '^/' if app.path == '/' else '^' + app.path + '(/|$)'
            if re.match(pattern, context, re.I | re.M):
                logger.debug('Narrow discovery to application \'%s\'.' % app.path)
                for vdir in app.vdirs:
                    variableResolver.add('physicalPath', vdir.physicalPath)
                break


class Vdir:
    def __init__(self, path, physicalPath):
        self.path = path
        self.physicalPath = physicalPath

    def __repr__(self):
        return 'Vdir(%s)' % self.path


class App:
    def __init__(self, path, vdirs):
        self.path = path
        self.vdirs = vdirs

    def __repr__(self):
        return 'App(%s)' % self.path


