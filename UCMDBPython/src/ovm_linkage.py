'''
Created on Apr 3, 2013

@author: vvitvitskiy
'''
from appilog.common.system.types import ObjectStateHolder


class Builder:

    @staticmethod
    def build_link(cit_name, end1_osh, end2_osh):
        r""" Creates an C{osh} class that represents a link.
        The link must be a valid link according to the class model.
        @types: str, osh, osh -> osh
          @param cit_name: the name of the link to create
          @param end1: the I{from} of the link
          @param end2: the I{to} of the link
          @return: a link from end1 to end2 of type className
        """
        assert cit_name and end1_osh and end2_osh
        osh = ObjectStateHolder(cit_name)
        osh.setAttribute("link_end1", end1_osh)
        osh.setAttribute("link_end2", end2_osh)
        return osh


class Reporter:
    def __init__(self, builder=Builder()):
        r'@types: Builder'
        self.__builder = builder

    def _get_builder(self):
        return self.__builder

    def execution_environment(self, osh1, osh2):
        if not (osh1 and osh2):
            raise ValueError("Start or End OSH is not specified")
        name = 'execution_environment'
        return self._get_builder().build_link(name, osh1, osh2)

    def report_deployment(self, osh1, osh2):
        r'''@types: osh, osh -> osh'''
        assert osh1 and osh2
        return self._get_builder().build_link('deployed', osh1, osh2)

    def report_dependency(self, slave, master):
        r'''@types: osh, osh -> osh[dependency]
        @raise ValueError: System OSH is not specified
        @raise ValueError: Instance OSH is not specified
        '''
        if not slave:
            raise ValueError("Slave OSH is not specified")
        if not master:
            raise ValueError("Master OSH is not specified")
        return self._get_builder().build_link('dependency', slave, master)

    def report_usage(self, who, whom):
        r'''@types: osh, osh -> osh[usage]
        @raise ValueError: Who-OSH is not specified
        @raise ValueError: Whom-OSH is not specified
        '''
        if not who:
            raise ValueError("Who-OSH is not specified")
        if not whom:
            raise ValueError("Whom-OSH is not specified")
        return self._get_builder().build_link('usage', who, whom)

    def report_membership(self, who, whom):
        r'''@types: osh, osh -> osh[membership]
        @raise ValueError: Who-OSH is not specified
        @raise ValueError: Whom-OSH is not specified
        '''
        if not who:
            raise ValueError("Who-OSH is not specified")
        if not whom:
            raise ValueError("Whom-OSH is not specified")
        return self._get_builder().build_link('membership', who, whom)

    def report_client_server_relation(self, client, server):
        r'''@types: osh, osh -> osh[membership]
        @raise ValueError: Client OSH is not specified
        @raise ValueError: Server OSH is not specified
        '''
        if not client:
            raise ValueError("Client OSH is not specified")
        if not server:
            raise ValueError("Server OSH is not specified")
        osh = self._get_builder().build_link('client_server', client, server)
        osh.setAttribute('clientserver_protocol', 'TCP')
        return osh

    def report_containment(self, who, whom):
        r'''@types: osh, osh -> osh[containment]
        @raise ValueError: Who-OSH is not specified
        @raise ValueError: Whom-OSH is not specified
        '''
        if not who:
            raise ValueError("Who-OSH is not specified")
        if not whom:
            raise ValueError("Whom-OSH is not specified")
        return self._get_builder().build_link('containment', who, whom)
