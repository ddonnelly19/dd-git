import re
from appilog.common.system.types import ObjectStateHolder
import logger
import modeling
import netutils


class WebSpherePluginConfigReporter:
    '''
    Class is used for reporting the topology discovered from WebSphere Plugin config (plugin-cfg.xml)
    '''

    def __init__(self):
        self.__resolveCache = {}

    def _createHostByIp(self, ip):
        hostOsh = modeling.createHostOSH(ip)
        return hostOsh

    def _createServiceEndpointByTransport(self, transport, hostOsh):
        if transport.hostIp and transport.port and transport.port.isdigit():
            try:
                intPort = int(transport.port)
                serviceEndpointOsh = modeling.createServiceAddressOsh(hostOsh, transport.hostIp, intPort,
                                                                      modeling.SERVICEADDRESS_TYPE_TCP,
                                                                      transport.protocol)
                return serviceEndpointOsh
            except:
                logger.debug("Failed to convert port value to integer")


    def _createRunningSoftwareOsh(self, description, hostOsh):
        runningSoftwareOsh = ObjectStateHolder("j2eeserver")
        if description:
            runningSoftwareOsh.setStringAttribute("description", description)
            runningSoftwareOsh.setStringAttribute("j2eeserver_fullname", description)
        runningSoftwareOsh.setContainer(hostOsh)
        return runningSoftwareOsh

    def _getNormalizedUri(self, uri):
        if uri:
            uri = uri.strip()
            # white spaces should not occur
            if re.search(r"\s+", uri): return

            tokens = re.split(r"/+", uri)

            # should be at least one slash
            if len(tokens) < 2: return

            # uri should start from slash
            if tokens[0] != "": return

            # all middle tokens should not contain *
            middleTokens = tokens[1:-1]
            if middleTokens:
                for middleToken in middleTokens:
                    if re.search(r"\*", middleToken):
                        return

            #remove last *
            lastToken = tokens[len(tokens) - 1]
            if re.search("\*", lastToken):
                if len(lastToken) > 1: return
                tokens[len(tokens) - 1] = ""

            #remove last slash unless it is the only one
            if tokens[len(tokens) - 1] == "" and len(tokens) > 2:
                del tokens[len(tokens) - 1]
            return "/".join(tokens)

    def _createHttpContext(self, uri, transport, serverName, webServerOsh):
        if uri and transport.hostIp and transport.port:
            compositeKey = "_".join([uri, transport.hostIp, str(transport.port)])
            httpContextOsh = ObjectStateHolder('httpcontext')
            httpContextOsh.setAttribute('data_name', compositeKey)

            if transport.hostName:
                httpContextOsh.setAttribute('httpcontext_webapplicationhost', transport.hostName)

            httpContextOsh.setAttribute('httpcontext_webapplicationcontext', uri)

            if serverName:
                httpContextOsh.setAttribute('httpcontext_webapplicationserver', serverName)

            if netutils.isValidIp(transport.hostIp):
                httpContextOsh.setAttribute('httpcontext_webapplicationip', transport.hostIp)

            if transport.protocol:
                httpContextOsh.setAttribute('applicationresource_type', transport.protocol)

            httpContextOsh.setContainer(webServerOsh)
            return httpContextOsh

    def _reportDependentWebSphere(self, server, transport, webServerOsh, resultsVector):
        hostOsh = self._createHostByIp(transport.hostIp)
        serviceEndpointOsh = self._createServiceEndpointByTransport(transport, hostOsh)
        if serviceEndpointOsh is None:
            return

        resultsVector.add(hostOsh)
        resultsVector.add(serviceEndpointOsh)

        webSphereOsh = self._createRunningSoftwareOsh(server.name, hostOsh)
        resultsVector.add(webSphereOsh)

        # 9.x link
        useLink = modeling.createLinkOSH('usage', webSphereOsh, serviceEndpointOsh)
        resultsVector.add(useLink)
        # 9.x link
        if webServerOsh.getObjectClass() != 'iis':
            dependencyLink = modeling.createLinkOSH('dependency', webSphereOsh, webServerOsh)
            resultsVector.add(dependencyLink)


    def report(self, webSphereConfig, resultVector, webServerOsh):
        self._resolveHostNameToIp(webSphereConfig)

        for route in webSphereConfig.routes:
            clusterName = route.clusterName
            cluster = webSphereConfig.clustersByName.get(clusterName)
            if not cluster:
                continue

            uriGroupName = route.uriGroupName
            uriGroup = webSphereConfig.uriGroupsByName.get(uriGroupName)

            for server in cluster.serversByName.values():
                for transport in server.transports:
                    if transport.hostIp and transport.port:

                        self._reportDependentWebSphere(server, transport, webServerOsh, resultVector)

                        if uriGroup is not None:
                            for uri in uriGroup.uris:

                                normalizedUri = self._getNormalizedUri(uri.name)
                                if not normalizedUri: continue

                                httpContextOsh = self._createHttpContext(normalizedUri, transport, server.name,
                                                                         webServerOsh)
                                if httpContextOsh is not None:
                                    contextConfigOsh = modeling.createConfigurationDocumentOSH('httpcontext.txt', '',
                                                                                               self._getContextContent(
                                                                                                   normalizedUri,
                                                                                                   transport),
                                                                                               httpContextOsh)
                                    contextConfigLinkOsh = modeling.createLinkOSH('usage', httpContextOsh,
                                                                                  contextConfigOsh)
                                    resultVector.add(contextConfigOsh)
                                    resultVector.add(contextConfigLinkOsh)
                                    resultVector.add(httpContextOsh)


    def _getContextContent(self, normalizedUri, transport):
        return transport.protocol + '://' + transport.hostIp + ":" + transport.port + normalizedUri

    def _resolveHostNameToIp(self, webSphereConfig):
        # resolving the websphere host names to IP
        for cluster in webSphereConfig.clustersByName.values():
            for server in cluster.serversByName.values():
                for transport in server.transports:
                    hostName = transport.hostName
                    ip = self._resolveHostNameWithCaching(hostName)
                    if ip:
                        transport.hostIp = ip
                        logger.info("Resolved host name (%s) to IP (%s)\n" % (hostName, ip))

    def _resolveHostNameWithCaching(self, hostName):
        # TODO: use external resolver
        ip = None
        if self.__resolveCache.has_key(hostName):
            ip = self.__resolveCache.get(hostName)
        else:
            ip = netutils.getHostAddress(hostName)
            self.__resolveCache[hostName] = ip

        if ip and netutils.isValidIp(ip) and not netutils.isLocalIp(ip):
            return ip
