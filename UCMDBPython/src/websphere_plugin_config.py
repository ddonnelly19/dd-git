#coding=utf-8
from org.jdom.input import SAXBuilder
from java.io import StringReader

class WebSpherePluginConfig:
    '''
    Class represents the configuration of WebSphere plugin as DOM
    '''
    
    class Cluster:
        def __init__(self, name):
            self.name = name
            self.serversByName = {}
        
        def __repr__(self):
            serversString = ",\n ".join([repr(server) for server in self.serversByName.values()])
            return "Cluster %s, Servers [\n %s\n]" % (self.name, serversString)
            
    class Server:
        def __init__(self, name):
            self.name = name
            self.transports = []
        
        def __repr__(self):
            transportsString = ",\n ".join([repr(transport) for transport in self.transports])
            return "Server %s, Transports [\n %s\n]" % (self.name, transportsString)
            
    class Transport:
        def __init__(self, hostName, port, protocol):
            self.hostName = hostName
            self.port = port
            self.protocol = protocol
            
            self.hostIp = None
        
        def __repr__(self):
            return "Transport [Host: %s, Port: %s, Protocol %s]" % (self.hostName, self.port, self.protocol)

    class UriGroup:
        def __init__(self, name):
            self.name = name
            self.uris = []
        def __repr__(self):
            urisString = ",\n ".join([repr(uri) for uri in self.uris])
            return "URI Group %s, URIs [\n %s\n]" % (self.name, urisString)
            
    class Uri:
        def __init__(self, name):
            self.name = name
            
        def __repr__(self):
            return "URI %s" % self.name
    
    class Route:
        def __init__(self, clusterName, uriGroupName):
            self.clusterName = clusterName
            self.uriGroupName = uriGroupName
        
        def __repr__(self):
            return "Route for URI Group %s to cluster %s" % (self.uriGroupName, self.clusterName)
    
    def __init__(self):
        
        self.clustersByName = {}

        self.uriGroupsByName = {}
        
        self.routes = []
        
    def __repr__(self):
        clustersString = ",\n ".join([repr(cluster) for cluster in self.clustersByName.values()])
        uriGroupsString = ",\n ".join([repr(uriGroup) for uriGroup in self.uriGroupsByName.values()])
        routes = ",\n ".join([repr(route) for route in self.routes])
        return "WebSphere Plugin Config:\nClusters [\n %s\n],\nURI Groups [\n %s\n],\nRoutes [\n %s\n]" % (clustersString, uriGroupsString, routes)


class WebSpherePluginConfigParser:
    '''
    Class for plugin-cfg.xml parsing which holds configuration of
    WebSphere plugin. Parsed configuration includes clusters, servers in clusters,
    URI groups and URIs, routes.
    
    @see WebSpherePluginConfig
    '''
    def __init__(self):
        pass
    
    def parse(self, pluginConfigContent):
        builder = SAXBuilder(0)
        doc = builder.build(StringReader(pluginConfigContent))
        rootElement = doc.getRootElement()
        
        pluginConfig = WebSpherePluginConfig()
        
        pluginConfig.clustersByName = self._parseClusters(rootElement)
        
        pluginConfig.uriGroupsByName = self._parseUriGroups(rootElement)
        
        pluginConfig.routes = self._parseRoutes(rootElement)
        
        return pluginConfig
        
    def _parseClusters(self, rootElement):
        clustersByName = {}
        clusterElemenents = rootElement.getChildren('ServerCluster')
        if clusterElemenents:
            
            for clusterElement in clusterElemenents:
                clusterName = clusterElement.getAttributeValue('Name')
                clusterName = clusterName and clusterName.strip()
                if not clusterName: continue

                cluster = WebSpherePluginConfig.Cluster(clusterName)
                clustersByName[clusterName] = cluster

                cluster.serversByName = self._parseServersInCluster(clusterElement)
        
        return clustersByName
            
    def _parseServersInCluster(self, clusterElement):
        serversByName = {}
        serverElements = clusterElement.getChildren('Server')
        if serverElements:
            
            for serverElement in serverElements:
                serverName = serverElement.getAttributeValue('Name')
                serverName = serverName and serverName.strip()
                if not serverName: continue
                
                server = WebSpherePluginConfig.Server(serverName)
                serversByName[serverName] = server

                server.transports = self._parseTransportsInServer(serverElement)
            
        return serversByName
    
    def _parseTransportsInServer(self, serverElement):
        transports = []
        transportElements = serverElement.getChildren('Transport')
        if transportElements:
            
            for transportElement in transportElements:
                host = transportElement.getAttributeValue('Hostname')
                host = host and host.strip()
                port = transportElement.getAttributeValue('Port')
                protocol = transportElement.getAttributeValue('Protocol')
                if not host or not port or not protocol: continue
                
                transport = WebSpherePluginConfig.Transport(host, port, protocol)
                transports.append(transport)
        
        return transports
    
    def _parseUriGroups(self, rootElement):
        uriGroupsByName = {}
        uriGroupElements = rootElement.getChildren('UriGroup')
        if uriGroupElements:
            
            for uriGroupElement in uriGroupElements:
                uriGroupName = uriGroupElement.getAttributeValue('Name')
                uriGroupName = uriGroupName and uriGroupName.strip()
                if not uriGroupName: continue
                
                uriGroup = WebSpherePluginConfig.UriGroup(uriGroupName)
                uriGroupsByName[uriGroupName] = uriGroup
                
                uriGroup.uris = self._parseUris(uriGroupElement)
        
        return uriGroupsByName
    
    def _parseUris(self, uriGroupElement):
        uris = []
        uriElements = uriGroupElement.getChildren('Uri')
        if uriElements:
            
            for uriElement in uriElements:
                uriName = uriElement.getAttributeValue('Name')
                uriName = uriName and uriName.strip()
                if not uriName: continue
                
                uri = WebSpherePluginConfig.Uri(uriName)
                uris.append(uri)
        
        return uris
    
    def _parseRoutes(self, rootElement):
        routes = []
        routeElements = rootElement.getChildren('Route')
        if routeElements:
            
            for routeElement in routeElements:
                clusterName = routeElement.getAttributeValue('ServerCluster')
                clusterName = clusterName and clusterName.strip()
                uriGroupName = routeElement.getAttributeValue('UriGroup')
                uriGroupName = uriGroupName and uriGroupName.strip()

                if not clusterName: continue

                route = WebSpherePluginConfig.Route(clusterName, uriGroupName)
                routes.append(route)
        
        return routes