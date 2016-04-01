# __author__ = 'gengt'
import logger
from apache_config_item import ConfigItem, Block
from apache_config_parser_rule import getApacheConfParserRule
from apache_config_item_utils import ConfigItems, ApacheConfigParserException, getPathOperation


class ApacheConfParser(object):
    def __init__(self, shell):
        self.shell = shell
        self.rootBlock = Block('', is_root=True)    # the root block of the Apache config
        self.items = ConfigItems()    # all the parsed config items
        self.contentsIterator = self.ContentsIterator()

    def parseApacheConf(self, content, contentPath="", contentName=""):
        """
        Parse Apache Config
        :param content: content of Apache config
        :param contentPath: the file path of the given content
        :param contentName: the file name of the given content
        """
        if content is None:
            return
        self.rootBlock = Block('', is_root=True)
        self.items = ConfigItems()
        self.contentsIterator = self.ContentsIterator()
        currentBlock = self.rootBlock
        self.contentsIterator.addContent(self.shell, content, contentPath, contentName)
        for iterator in self.contentsIterator:
            line, lineNumber, path, name = iterator
            if not line:
                continue
            line = line.strip()
            if not line or line[0] == '#':
                continue
            try:
                parserRule = getApacheConfParserRule(line)
                if parserRule:
                    item = parserRule.parse(line)
                    if item and isinstance(item, ConfigItem):
                        currentBlock.appendChild(item)
                        self.items.append(item)
                    currentBlock = parserRule.getNextBlock(item, currentBlock)
                    parserRule.postParse(self, item, path)
                else:
                    logger.warn("cannot find parser rule for config: %s. (%s Line %s)" % (
                        line, getPathOperation(self.shell).join(path, name), lineNumber))
            except ApacheConfigParserException, e:
                raise ApacheConfigParserException('%s: %s Line %s' % (
                    e.message, getPathOperation(self.shell).join(path, name), lineNumber))
        if currentBlock != self.rootBlock:
            raise ApacheConfigParserException('Missing block end at the end of config file: %s' %
                                              getPathOperation(self.shell).join(contentPath, contentName))

    class ContentsIterator(object):
        def __init__(self):
            self.contents = []    # list of ContentIterator

        def __iter__(self):
            return self

        def next(self):
            if not self.contents:
                raise StopIteration
            current = self.contents.pop()
            detail = current.detail()
            try:
                self.contents.append(current.next())
            except StopIteration:
                pass
            return detail

        def addContent(self, shell, content, contentPath="", contentName=""):
            self.contents.append(self.ContentIterator(shell, content, contentPath, contentName))

        class ContentIterator(object):
            def __init__(self, shell, content, contentPath, contentName):
                self.shell = shell
                self.contents = content.splitlines()
                self.filePath = contentPath
                self.fileName = contentName
                self.maxLineNumber = len(self.contents)
                self.currentLineNumber = 0

            def __iter__(self):
                return self

            def next(self):
                self.currentLineNumber += 1
                # treat multiple line ending with '\'; combine them to one line
                while self.currentLineNumber < self.maxLineNumber and \
                        self.contents[self.currentLineNumber] and \
                        self.contents[self.currentLineNumber].replace('\\\\', '')[-1] == '\\':
                    if self.currentLineNumber + 1 < self.maxLineNumber:
                        self.contents[self.currentLineNumber + 1] = '%s%s' % (
                            self.contents[self.currentLineNumber][0:-1],
                            self.contents[self.currentLineNumber + 1])
                        self.currentLineNumber += 1
                    else:
                        raise ApacheConfigParserException("Illegal content end: '\\'. %s Line %s" % (
                            getApacheConfParserRule(self.shell).join(self.filePath, self.fileName),
                            self.currentLineNumber))
                if self.currentLineNumber < self.maxLineNumber:
                    return self
                else:
                    raise StopIteration

            def detail(self):
                # merge multiple line ending with '\' to one line
                return self.contents[self.currentLineNumber], self.currentLineNumber, self.filePath, self.fileName
