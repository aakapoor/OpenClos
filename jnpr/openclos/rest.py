'''
Created on Sep 2, 2014

@author: moloyc
'''

import os
import logging
import bottle
from sqlalchemy.orm import exc

import util
from model import Pod, Device
from dao import Dao

moduleName = 'rest'
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(moduleName)
webServerRoot = os.path.join('out', 'junosTemplates')

class ResourceLink():
    def __init__(self, baseUrl, path):
        self.baseUrl = baseUrl
        self.path = path
    def __str__(self):
        return str("{'href': %s%s}" % (self.baseUrl, self.path))
    def __repr__(self):
        return self.__str__()
    def toDict(self):
        return {'href': self.baseUrl + self.path}

class RestServer():
    def __init__(self, conf = {}):
        if any(conf) == False:
            self.conf = util.loadConfig()
            logging.basicConfig(level=logging.getLevelName(self.conf['logLevel'][moduleName]))
            logger = logging.getLogger(moduleName)
        else:
            self.conf = conf
        self.dao = Dao(self.conf)

        if (self.conf['httpServer']['ipAddr'] is None):
            host = 'localhost'
        port = self.conf['httpServer']['port']
        self.baseUrl = 'http://%s:%d' % (host, port)
        
        self.addRoutes(self.baseUrl)
        app = bottle.app()
        bottle.run(app, host=host, port=port)

    def addRoutes(self, baseUrl):
        self.indexLinks = []
        bottle.route('/', 'GET', self.getIndex)
        bottle.route('/pods/<podName>/devices/<deviceName>/config', 'GET', self.getDeviceConfig)
        # TODO: the resource lookup should hierarchical
        # /pods/*
        # /pods/{podName}/devices/*
        # /pods/{podName}/devices/{deviceName}/config
        self.createLinkForConfigs()

    def createLinkForConfigs(self):
        pods = self.dao.getAll(Pod)
        for pod in pods:
            for device in pod.devices:
                self.indexLinks.append(ResourceLink(self.baseUrl, 
                    '/pods/%s/devices/%s/config' % (pod.name, device.name)))
    
    def getIndex(self):
        jsonLinks = []
        for link in self.indexLinks:
            jsonLinks.append({'link': link.toDict()})

        jsonBody = \
            {'href': self.baseUrl,
             'links': jsonLinks
             }

        return jsonBody
    
    def getDeviceConfig(self, podName, deviceName):

        if not self.isDeviceExists(podName, deviceName):
            raise bottle.HTTPError(404, "No device found with pod name: '%s', device name: '%s'" % (podName, deviceName))
        
        fileName = os.path.join(podName, deviceName+'.conf')
        config = bottle.static_file(fileName, root='out')
        if isinstance(config, bottle.HTTPError):
            logger.debug("Device exists but no config found. Pod name: '%s', device name: '%s'" % (podName, deviceName))
            raise bottle.HTTPError(404, "Device exists but no config found, probably fabric script is not ran. Pod name: '%s', device name: '%s'" % (podName, deviceName))
        return config

    def isDeviceExists(self, podName, deviceName):
        try:
            self.dao.Session.query(Device).join(Pod).filter(Device.name == deviceName).filter(Pod.name == podName).one()
            return True
        except (exc.NoResultFound):
            logger.debug("No device found with pod name: '%s', device name: '%s'" % (podName, deviceName))
            return False
    
if __name__ == '__main__':
    RestServer()