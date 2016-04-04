# coding=utf-8
"""
This library contains log utilities and helper functions for error reporting.
It contains APIs to log the at debug, info, and error levels.

The logs configuration is in the probeMgrLog4j.properties file. By default, the messages from the log level
and up are written to probeMgr-patternsDebug.log in the discovery probe log folder. The info and error messages
are also displayed on the console.

There are two sets of APIs:
 - logger.<debug/info/warn/error>
 - logger.<debugException/infoException/warnException/errorException>
The first set issues the concatenation of all its string arguments in the appropriate log level.
The second does the same along with the most recent thrown exception's stack trace. This facilitates
understanding the cause of the exception.
"""

import traceback
import sys
from org.apache.log4j import Category
from java.lang import Exception as JException, Object
from com.hp.ucmdb.discovery.library.clients import ScriptsExecutionManager

cat = Category.getInstance('PATTERNS_DEBUG')


def _getFramework():
    return ScriptsExecutionManager.getFramework()


def addLog(level, msg, stackTrace=None):
    ScriptsExecutionManager.addExecutionRecordLog(level, msg)


def join(msg, *args):
    def coerce_(x):
        if isinstance(x, basestring):
            return x
        elif isinstance(x, Object):
            return x.toString()
        elif isinstance(x, Exception):
            return unicode(x.message)
        return repr(x)

    msgUnicode = coerce_(msg)
    if args:
        msgUnicode = msgUnicode + u''.join(map(coerce_, args))
    return msgUnicode


def debug(msg, *args):
    """
    Logs a debug message if debug messages are enabled.
    @param msg: the log message
    @type msg: string
    @param args: additional variables to log
    """

    if isDebugEnabled():
        message = join(msg, *args)
        cat.debug(message)
        addLog('debug', message)


def info(msg, *args):
    """
    Logs an info level message if info messages are enabled.
    @param msg: the log message
    @type msg: string
    @param args: additional variables to log
    """

    if isInfoEnabled():
        message = join(msg, *args)
        cat.info(message)
        addLog('info', message)


def warn(msg, *args):
    """
    Logs a warning message if warn messages are enabled.
    @param msg: the log message
    @type msg: string
    @param args: additional variables to log
    """

    message = join(msg, *args)
    cat.warn(message)
    addLog('warn', message)


def error(msg, *args):
    """
    Logs an error message if debug messages.
    @param msg: the log message
    @type msg: string
    @param args: additional variables to log
    """

    message = join(msg, *args)
    cat.error(message)
    addLog('error', message)


def fatal(msg, *args):
    """
    Logs a fatal message.
    @param msg: the log message
    @type msg: string
    @param args: additional variables to log
    """

    message = join(msg, *args)
    cat.fatal(message)
    addLog('fatal', message)


def isDebugEnabled():
    """
    Checks whether DEBUG messages are configured to be written to the log file.
    The method checks in thel log4j properties file.
    @return: true if the debug messages should be written, false otherwise
    @rtype: boolean
    """

    return cat.isDebugEnabled()


def isInfoEnabled():
    """
    Checks whether INFO messages should be written to the log file, acording to
    The method checks in thel log4j properties file.
    @return: true if the info messages should be written, false otherwise
    @rtype:	boolean
    """

    return cat.isInfoEnabled()


def prepareJythonStackTrace(msg, *args):
    exc_info = sys.exc_info()
    stacktrace = traceback.format_exception(exc_info[0], exc_info[1], exc_info[2])
    resultMessage = join(msg, *args) + '\n' + ''.join(map(str, stacktrace))
    return resultMessage


def prepareJavaStackTrace():
    dataObj = sys.exc_info()[1]
    if type(dataObj.__class__).__name__ == 'org.python.core.PyJavaClass':
        if JException.getClass().isAssignableFrom(dataObj.__class__):
            return dataObj
    return None


def prepareFullStackTrace(msg, *args):
    """
    Returns the full exception stack trace from both Java and Jython.
    @param msg: the log message
    @type msg: string
    @param args: additional variables to log
    @return: full Stack Trace string (both java and jython)
    @rtype: string
    """

    exc_info = sys.exc_info()
    stacktrace = traceback.format_exception(exc_info[0], exc_info[1], exc_info[2])
    resultMessage = join(msg, *args) + ''.join(map(str, stacktrace))
    javaStacktrace = prepareJavaStackTrace()
    if (javaStacktrace != None):
        resultMessage = resultMessage + '\nJava stackTrace:\n' + str(javaStacktrace)
    return resultMessage


def debugException(msg, *args):
    """
    Writes the full exception stack trace from both Java and Jython to the log at the debug level.
    @param msg: the log message
    @type msg: string
    @param args: additional variables to log
    """

    if (isDebugEnabled()):
        message = prepareJythonStackTrace(msg, *args)
        srtackTrace = prepareJavaStackTrace()
        cat.debug(message, srtackTrace)
        addLog('debug', message, srtackTrace)


def infoException(msg, *args):
    """
    Writes the full exception stack trace from both Java and Jython to the log at the info level.
    @param msg: the log message
    @type msg: string
    @param args: additional variables to log
    """

    if (isInfoEnabled()):
        message = prepareJythonStackTrace(msg, *args)
        srtackTrace = prepareJavaStackTrace()
        cat.info(message, srtackTrace)
        addLog('info', message, srtackTrace)


def warnException(msg, *args):
    """
    Writes the full exception stack trace from both Java and Jython to the log at the warn level.
    @param msg: the log message
    @type msg: string
    @param args: additional variables to log
    """

    message = prepareJythonStackTrace(msg, *args)
    srtackTrace = prepareJavaStackTrace()
    cat.warn(message, srtackTrace)
    addLog('warn', message, srtackTrace)


def getCauseMessagesFromJavaStacktrace(stacktrace):
    r'@types: Throwable > list[str]'
    causeMessages = []
    while stacktrace:
        try:
            # some 3rd party Exception classes may
            # raise exception on getMessage method
            message = stacktrace.getMessage()
        except:
            causeMessages.append(message)
        try:
            stacktrace = stacktrace.getCause()
        except:
            stacktrace = None
    return map(str, filter(None, causeMessages))


def warnCompactException(msg, *args):
    r'Warns message along with exception details that are messages of cases'
    stacktrace = prepareJavaStackTrace()
    causeMessages = stacktrace and getCauseMessagesFromJavaStacktrace(stacktrace)
    shortenedTrace = causeMessages and "Caused by:\n%s" % (
                                        '\n'.join(causeMessages))
    addLog('warn', msg, shortenedTrace or '')


def errorException(msg, *args):
    """
    Writes the full exception stack trace from both Java and Jython to the log at the error level.
    @param msg: the log message
    @type msg: string
    @param args: additional variables to log
    """

    message = prepareJythonStackTrace(msg, *args)
    stackTrace = prepareJavaStackTrace()
    cat.error(message, stackTrace)
    addLog('error', message, stackTrace)


def fatalException(msg, *args):
    """
    Writes the full exception stack trace from both Java and Jython to the log at the fatal level.
    @param msg: the log message
    @type msg: string
    @param args: additional variables to log
    """
    message = prepareJythonStackTrace(msg, *args)
    stackTrace = prepareJavaStackTrace()
    cat.fatal(message, stackTrace)
    addLog('fatal', message, stackTrace)


def reportWarning(warning=None):
    if warning == None:
        warning = str(sys.exc_info()[1])

    _getFramework().reportWarning(warning)


def reportError(error=None):
    if error == None:
        error = str(sys.exc_info()[1])

    _getFramework().reportError(error)


def reportWarningObject(warnobj):
    if not warnobj.isEmpty():
        Framework = _getFramework()
        __reportWarning(warnobj.errCode, warnobj.params, warnobj.errMsg, Framework)
        debug("Reporting warning code " + str(warnobj.errCode) + " to framework.")
        debug("Warning message is: " + warnobj.errMsg)


def reportErrorObject(errobj):
    if not errobj.isEmpty():
        Framework = _getFramework()
        __reportError(errobj.errCode, errobj.params, errobj.errMsg, Framework)
        debug("Reporting error code " + str(errobj.errCode) + " to framework.")
        debug("Error message is: " + errobj.errMsg)


def __reportWarning(errorCode, params, errmsg, framework):
    framework.reportWarning(errorCode, params)


def __reportError(errorCode, params, errmsg, framework):
    framework.reportError(errorCode, params)


class Version:
    foundVersion = None

    def getVersion(self, framework):
        ''' Framework -> double
        @deprecated: use modeling.CmdbClassModel().version() instead
        '''
        if (Version.foundVersion is None):
            versionAsDouble = 8.01  # v8.01 or lower...
            try:
                envInfo = framework.getEnvironmentInformation()
                # The following method was impl. in v8.02 and therefore exception will be thrown on earlier versions
                version = envInfo.getProbeVersion()
                versionAsDouble = version.getVersion()
            except:
                pass
            Version.foundVersion = versionAsDouble
        return Version.foundVersion


def __getVersion(framework):
    ''' Framework -> double
    @deprecated: use modeling.CmdbClassModel().version() instead
    '''
    return Version().getVersion(framework)

