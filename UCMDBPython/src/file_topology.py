#coding=utf-8
import os
from java.util import Date
import re
import modeling


class FsException(Exception):
    pass


class PathNotFoundException(FsException):
    def __init__(self, path=None):
        r'@types: str'
        self.path = path


class BatchDiscoveryFsException(FsException):
    pass


class PerlDiscoveryFsException(FsException):
    pass


class FileAttrs:
    NAME = 'name'
    OWNER = 'owner'
    PERMS = 'perms'
    SIZE = 'size'
    PATH = 'path'
    PARENT = 'parent'
    CONTENT = 'content'
    CREATION_TIME = 'creationTime'
    LAST_MODIFICATION_TIME = 'lastModificationTime'
    IS_DIRECTORY = 'isDirectory'
    VERSION = 'version'

BASE_FILE_ATTRIBUTES = [FileAttrs.NAME, FileAttrs.PATH, \
                       FileAttrs.PARENT, FileAttrs.IS_DIRECTORY]


__OCTAL_TO_STR_MAP = {
                     '0': '---',
                     '1': '--x',
                     '2': '-w-',
                     '3': '-wx',
                     '4': 'r--',
                     '5': 'r-x',
                     '6': 'rw-',
                     '7': 'rwx',
                     }


class File:
    def __init__(self, name, isDirectory=None):
        '''Constructor for the file data object.
        str, bool -> File
        @param name: Name of a file including extension
        @type creationTime : java.util.Date
        @param isDirectory: flag indicating whether file or directory
        '''
        if not name:
            raise ValueError('Name is empty')
        # If java.lang.String passed here code will
        #fail on os.path.splitext call with AttributeError: __getitem__
        name = str(name)
        self.__name = name

        '''@deprecated: use getName method instead'''
        self.name = name
        self.isDirectory = isDirectory
        self.owner = None
        self.__perms = None
        ext = name.rfind('.') != 0 and os.path.splitext(name)[1]
        self.ext = ext and ext[1:] or None
        self.path = None
        self.parent = None
        self.version = None
        self.content = None
        self.__creationTime = None
        self.__lastModificationTime = None
        self.__sizeInBytes = None

    def getName(self):
        return self.__name

    def __repr__(self):
        return 'File("%s", isDirectory = %s)' % (self.name, self.isDirectory)

    def setPermissionsInText(self, permissions):
        '''Sets file permissions provided in text form,
        like rwxrwxrwx for unix or '--a------' for windows
        str -> None
        @param permissions: text representation of permissions
        @type permissions: str
        @return: None
        '''
        self.__perms = permissions

    def setPermissionsInOctal(self, mask):
        '''Sets file permissions provided in octal form, like 0777 for unix
        str -> None
        @param permissions: text representation of permissions
        @type permissions: str
        @return: None
        @raise ValueError: if provided mask is invalid: its length < 4 or
             octet value out of [0-7] range including.
        '''
        if (mask and len(mask) == 4):
            ownerOctet = __OCTAL_TO_STR_MAP.get(mask[1])
            groupOctet = __OCTAL_TO_STR_MAP.get(mask[2])
            otherOctet = __OCTAL_TO_STR_MAP.get(mask[3])
            if not(ownerOctet and groupOctet and otherOctet):
                raise ValueError('Not an octet value: %s' % mask)
            setids = mask[0]
            if (setids == '1'):  # Sticky bit
                otherOctet = otherOctet[:2] + (otherOctet[2] == 'x' and 't' or 'T')
            if (setids == '4'):  # Setuid bit
                ownerOctet = ownerOctet[:2] + (ownerOctet[2] == 'x' and 's' or 'S')
            if (setids == '2'):  # Setgid bit
                groupOctet = groupOctet[:2] + (groupOctet[2] == 'x' and 's' or 'S')
            self.__perms = '%s%s%s' % (ownerOctet, groupOctet, otherOctet)
        else:
            raise ValueError('Not an octal value: %s' % mask)

    def permissions(self):
        '''Access permissions of a file
        For unix: 'rwxrwxrwx'
        For windows: '--a------'
        @rtype: str
        @return: string representation of file access attributes
        '''
        return self.__perms

    def setCreateTimeInMls(self, timeInMls):
        ''' Parse java.util.Date from provided milliseconds str
        str -> None
        @param timeInMls: creation time in milliseconds
        @type timeInMls: str
        @return: None
        @raise ValueError: if provided string is not a number
        '''
        if timeInMls and timeInMls.isdigit():
            self.__creationTime = Date(long(timeInMls) * 1000)
        else:
            raise ValueError('Not a number: %s' % timeInMls)

    def setLastModificationTime(self, time):
        '''
        java.util.Date -> None
        @raise ValueError: if provided value is not Date object
        '''
        if time and isinstance(time, Date):
            self.__lastModificationTime = time
        else:
            raise ValueError('Not a Date: %s' % time)

    def setLastModificationTimeInMls(self, timeInMls):
        ''' Parse java.util.Date from provided milliseconds str
        str -> None
        @param timeInMls: last modification time in milliseconds
        @type timeInMls: str
        @return: None
        @raise ValueError: if provided string is not a number
        '''
        if timeInMls and timeInMls.isdigit():
            self.__lastModificationTime = Date(long(timeInMls) * 1000)
        else:
            raise ValueError('Not a number: %s' % timeInMls)

    def setCreateTimeInUTC(self, timeInUTC):
        ''' Parse java.util.Date from provided utc str
        str -> None
        @param timeInUTC: creation time in utc
        @type timeInUTC: str
        @return: None
        @raise ValueError: if failed to parse provided utc string
        '''
        if timeInUTC:
            self.__creationTime = modeling.getDateFromUtcString(timeInUTC)
        else:
            raise ValueError('Not a UTC: %s' % timeInUTC)

    def creationTime(self):
        ''' Creation time
        -> Date  or None
        @return: creation time of a file
        @rtype: java.util.Date
        '''
        return self.__creationTime

    def setLastModificationTimeInUTC(self, timeInUTC):
        ''' Parse java.util.Date from provided str
        str -> None
        @param timeInUTC: last modification time in utc
        @type timeInUTC: str
        @return: None
        @raise ValueError: if failed to parse provided utc string
        '''
        if timeInUTC:
            self.__lastModificationTime = modeling.getDateFromUtcString(timeInUTC)
        else:
            raise ValueError('Not a UTC: %s' % timeInUTC)

    def lastModificationTime(self):
        ''' Last modification time
        -> Date  or None
        @return: last modification time of a file
        @rtype: java.util.Date
        '''
        return self.__lastModificationTime

    def setSizeInBytes(self, sizeInBytes):
        '''Sets size of a file to specified value
        str -> None
        @param sizeInBytes: file size in bytes
        @type sizeInBytes: str
        @return: None
        @raise ValueError: if provided str is not a number
        '''
        if sizeInBytes and sizeInBytes.isdigit():
            self.__sizeInBytes = long(sizeInBytes)
        else:
            raise ValueError('Not a number: %s' % sizeInBytes)

    def sizeInBytes(self):
        '''Returns file size attribute
        -> long
        @return: size of a file
        @rtype: long
        '''
        return self.__sizeInBytes

    def __eq__(self, other):
        if isinstance(other, File):
            for name, otherValue in other.__dict__.items():
                value = self.__dict__.get(name)
                if value != otherValue:
                    return 0
            return 1

    def __ne__(self, file_):
        return not self.__eq__(file_)

    def __str__(self):
        str_ = 'File:\n'
        str_ += '%s: %s\n' % (FileAttrs.NAME, self.name)
        str_ += '%s: %s\n' % (FileAttrs.IS_DIRECTORY, self.isDirectory)
        str_ += '%s: %s\n' % (FileAttrs.PATH, self.path)
        return str_


def stripQuotes(value):
    unquoted = value
    matcher = re.match(r"\"([^\"]*)\"$", value)
    if matcher:
        unquoted = matcher.group(1)
    else:
        matcher = re.match(r"'([^']*)'$", value)
        if matcher:
            unquoted = matcher.group(1)
    return unquoted


def fixForwardSlashesInWindowsPath(path):
    return re.sub(r"/", r"\\", path)


class PathTool:
    r'''Abstract path class that defines an interface
    '''
    def _getProxy(self):
        r'Returns one of the os.path implementations'
        raise NotImplementedError()

    def cmdline_path(self, path):
        raise NotImplemented()

    def absolutePath(self, path):
        return self._getProxy().abspath(path)

    def join(self, *paths):
        return self._getProxy().join(*paths)

    def baseName(self, path):
        r'@types: -> str -> str'
        return self._getProxy().basename(path)

    def dirName(self, path):
        r'@types: -> str -> str'
        return self._getProxy().dirname(path)

    def isAbsolute(self, path):
        r'@types: str -> bool'
        return self._getProxy().isabs(path)

    def normalizePath(self, path):
        return self._getProxy().normpath(path)

    def split(self, path):
        return self._getProxy().split(path)

    def splitDrive(self, path):
        return self._getProxy().splitdrive(path)

    def splitExt(self, path):
        return self._getProxy().splitext(path)


class NtPath(PathTool):
    r'''Common pathname manipulations on Windows pathnames'''
    _PROXY_PACKAGE = __import__('ntpath')

    def _getProxy(self):
        r'Returns one of the os.path implementations'
        return self._PROXY_PACKAGE

    def escapeQuotes(self, path):
        r'''@types: str -> str
        @raise ValueError: Path to escape quotes is empty
        '''
        if not (path and path.strip()):
            raise ValueError("Path to escape quotes is empty")
        return path.replace('"', '""')

    def wrapWithQuotes(self, path):
        r'''@types: str -> str
        @raise ValueError: Path to wrap with quotes is empty
        '''
        if not (path and path.strip()):
            raise ValueError("Path to wrap with quotes is empty")
        path = path.strip()
        if not (path.startswith('"') and path.endswith('"')):
            path = '"%s"' % self.escapeQuotes(path)
        return path


class PosixPath(PathTool):
    r'''Common operations on POSIX pathnames'''
    _PROXY_PACKAGE = __import__('posixpath')

    def escapeWhitespaces(self, path):
        if not (path and path.strip()):
            raise ValueError("Path is empty")
        return path.replace(" ", "\ ")

    def _getProxy(self):
        r'Returns one of the os.path implementations'
        return self._PROXY_PACKAGE


class Builder:
    r'Simple builder class for file DO'
    def buildFile(self, file_):
        r''' Builder uses modeling method so far, but in further versions
        build procedure will be rewritten to get rid of modeling
        @types: File -> ObjectStateHolder'''
        osh = modeling.createConfigurationDocumentOSH(
                    file_.getName(), file_.path, file_.content,
                    containerOSH=None,  # can be specified in container level only
                    contentType=None,  # no corresponding attribute
                    contentLastUpdate=file_.lastModificationTime(),
                    description=None,  # no corresponding attribute
                    version=file_.version,
                    charsetName=None)   # no corresponding attribute
        if file_.owner:
            osh.setAttribute('document_osowner', file_.owner)
        if file_.permissions():
            osh.setAttribute('document_permissions', file_.permissions())
        return osh


class Reporter:
    def __init__(self, builder):
        r'''@types: file_topology.Builder
        @raise ValueError: Builder is not specified
        '''
        if not builder:
            raise ValueError("Builder is not specified")
        self.__builder = builder

    def report(self, file_, containerOsh):
        r'''@types: File, ObjectStateHolder -> ObjectStateHolder
        @raise ValueError: Container is not specified
        '''
        if not containerOsh:
            raise ValueError("Container is not specified")
        osh = self.__builder.buildFile(file_)
        osh.setContainer(containerOsh)
        return osh
