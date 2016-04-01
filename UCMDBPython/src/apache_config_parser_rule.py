# __author__ = 'gengt'
import logger
import re
from apache_config_item import Block, Property, IncludeProperty, LoadModuleProperty, ServerRootProperty
from apache_config_item_utils import ApacheConfigParserException, getPathOperation


parserRules = {}    # all the apache config parser rules

PRIORITY_HIGHER = 20
PRIORITY_HIGH = 20
PRIORITY_DEFAULT = 10
PRIORITY_LOW = 0


def getApacheConfParserRule(content):
    rules = [rule for rule in parserRules.values() if rule.regex.match(content)]
    if rules:
        rules.sort(key=lambda x: x.priority, reverse=True)
        return rules[0]()
    else:
        return None


def Rule(regex, priority=PRIORITY_DEFAULT):
    def decorator(c):
        c.regex = re.compile(regex)
        c.priority = priority
        parserRules[c.__name__] = c
        return c
    return decorator


class BaseRule(object):
    regex = None

    def parse(self, content):
        """parse the config content"""
        if self.regex:
            results = self.regex.match(content)
            if results:
                return self._parse(results.groups())
        return None

    def _parse(self, groups):
        """Create some config item according to the groups result by rule regex"""
        raise NotImplementedError

    def getNextBlock(self, item, currentBlock):
        """Return the next container block"""
        raise NotImplementedError

    def postParse(self, parser, item, path_prefix=''):
        """Doing something after config content parsed"""
        pass


@Rule(r'(\w+)\s+(.*)', PRIORITY_LOW)
class PropertyRule(BaseRule):
    def _parse(self, groups):
        key, value = groups
        return Property(key, value)

    def getNextBlock(self, item, currentBlock):
        return currentBlock


@Rule(r'<(\w+)\s+(.*)>', PRIORITY_LOW)
class BlockStartRule(BaseRule):
    def _parse(self, groups):
        key, value = groups
        return Block(key, value)

    def getNextBlock(self, item, currentBlock):
        return item


@Rule(r'</(\w+)>', PRIORITY_LOW)
class BlockEndRule(BaseRule):
    def _parse(self, groups):
        return groups[0]

    def getNextBlock(self, item, currentBlock):
        if currentBlock and currentBlock.name == item:
            return currentBlock.block
        else:
            raise ApacheConfigParserException('Unexpected block end')


@Rule(r'[iI]nclude\s+(([\'"]?)(\S+)\2)')
class IncludeRule(PropertyRule):
    def _parse(self, groups):
        value, _, path = groups
        return IncludeProperty('include', value, path=path)

    def postParse(self, parser, item, path_prefix=''):
        """
        Read the included file, add it to parser

        :param parser: apache_config_parser
        :param item: IncludeProperty item
        :param path_prefix: the path of file which has this include sentense
        """
        logger.debug('Load included file: %s' % item.filePath)
        # append file path if the include filePath is not absolute
        path_operation = getPathOperation(parser.shell)
        # use server_root for relative path
        path_prefix = getattr(item.root, 'server_root', path_prefix)
        if not path_operation.isabs(item.filePath):
            item.filePath = path_operation.join(path_prefix, item.filePath)
            logger.debug('Load included file using absolute path: %s' % item.filePath)

        content = item.getFileContent(parser.shell, path_prefix)
        # append include content to parse iterator
        if content:
            path, name = path_operation.split(item.filePath)
            parser.contentsIterator.addContent(parser.shell, content, path, name)
            logger.debug('Successful loading included file: %s' % item.filePath)
        else:
            logger.debug('Failed loading included file: %s' % item.filePath)


@Rule(r'LoadModule\s+((\S+)\s+(\S+))')
class LoadModuleRule(PropertyRule):
    def _parse(self, groups):
        value, module_name, module_path = groups
        return LoadModuleProperty('LoadModule', value, module_name=module_name, module_path=module_path)


@Rule(r'ServerRoot\s+(([\'"]?)(\S+)\2)')
class ServerRootRule(PropertyRule):
    def _parse(self, groups):
        value, _, server_root = groups
        return ServerRootProperty('ServerRoot', value, server_root=server_root)

    def postParse(self, parser, item, path_prefix=''):
        item.setServerRootInRootBlock()
