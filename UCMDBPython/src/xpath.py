import re
import sys

from net.sf.saxon.s9api import Processor
from java.io import StringReader
from javax.xml.transform.stream import StreamSource


class processor:
    NAMESPACE_PATTERN = r'xmlns\s*=\s*[^\'"]*[\'"][^\'"]*[\'"]'

    def __init__(self, content=None):
        self.__processor = Processor(False)
        self.__builder = self.__processor.newDocumentBuilder()
        self.__xPathCompiler = self.__processor.newXPathCompiler()
        if content:
            self.loadContent(content)
        else:
            self.__document = None

    def loadContent(self, content):
        content = re.sub(self.NAMESPACE_PATTERN, '', content)  # remove xml namespace
        reader = StringReader(content)
        self.__document = self.__builder.build(StreamSource(reader))

    def getVersion(self):
        return self.__processor.getSaxonProductVersion()

    def compile(self, xpathExp):
        try:
            executable = self.__xPathCompiler.compile(xpathExp)
            return executable
        except:
            raise SyntaxError, sys.exc_info()[1]

    def evaluateItem(self, xpathExp, context=None):
        if not self.__document:
            raise ValueError('Load xml first')
        executable = self.compile(xpathExp)
        selector = executable.load()
        if not context:
            context = self.__document
        selector.setContextItem(context)
        evaluatedResult = selector.evaluate()
        results = []
        map(results.append, evaluatedResult)
        return results

    def evaluate(self, xpathExp, context=None):
        results = self.evaluateItem(xpathExp, context)
        return [result.getStringValue() for result in results]
