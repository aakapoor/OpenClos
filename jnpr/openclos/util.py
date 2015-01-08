'''
Created on Aug 21, 2014

@author: moloyc
'''

import re
import os
import yaml
import platform
import datetime
import shutil
from netaddr import IPNetwork
import netifaces
import fileinput
import logging.config
from crypt import Cryptic

#__all__ = ['getPortNamesForDeviceFamily', 'expandPortName']
configLocation = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'conf')

TWO_STAGE_CONFIGURATOR_DEFAULT_ATTEMPT=5
TWO_STAGE_CONFIGURATOR_DEFAULT_INTERVAL=30 # in seconds
TWO_STAGE_CONFIGURATOR_DEFAULT_VCP_LLDP_DELAY=40 # in seconds

loggingInitialized = False

def loadConfig(confFile = 'openclos.yaml'):
    '''
    Loads global configuration and creates hash 'conf'
    '''
    try:
        confStream = open(os.path.join(configLocation, confFile), 'r')
        conf = yaml.load(confStream)
        if conf is not None:
            if 'dbUrl' in conf:
                if 'dbDialect' in conf:
                    print "Warning: dbUrl and dbDialect both exist. dbDialect ignored"
                # dbUrl is used by sqlite only
                conf['dbUrl'] = fixSqlliteDbUrlForRelativePath(conf['dbUrl'])
            elif 'dbDialect' in conf:
                db_pass = Cryptic ().decrypt ( conf['dbPassword'] )
                conf['dbUrl'] = conf['dbDialect'] + '://' + conf['dbUser'] + ':' + db_pass + '@' + conf['dbHost'] + '/' + conf['dbName'] 
            if 'outputDir' in conf:
                conf['outputDir'] = fixOutputDirForRelativePath(conf['outputDir'])
        
    except (OSError, IOError) as e:
        print "File error:", e
        return None
    except (yaml.scanner.ScannerError) as e:
        print "YAML error:", e
        confStream.close()
        return None
    finally:
        pass
    return conf

def fixOutputDirForRelativePath(outputDir):
    # /absolute-path/out
    # relative-path/out
    if (os.path.abspath(outputDir) != outputDir):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), outputDir)
    else:
        return outputDir

def fixSqlliteDbUrlForRelativePath(dbUrl):
    # sqlite:////absolute-path/sqllite3.db
    # sqlite:///relative-path/sqllite3.db
    match = re.match(r"sqlite:(\/+)(.*)\/(.*)", dbUrl)
    if match is not None:
        isRelative = (len(match.group(1)) == 3)
        if isRelative:
            relativeDir = match.group(2)
            absoluteDir = os.path.join(os.path.dirname(os.path.abspath(__file__)), relativeDir)
            dbUrl = 'sqlite:///' + absoluteDir + os.path.sep + match.group(3)

    return dbUrl

def loadClosDefinition(closDefination = os.path.join(configLocation, 'closTemplate.yaml')):
    '''
    Loads clos definition from yaml file
    '''
    try:
        stream = open(closDefination, 'r')
        yamlStream = yaml.load(stream)
        
        return yamlStream
    except (OSError, IOError) as e:
        print "File error:", e
    except (yaml.scanner.ScannerError) as e:
        print "YAML error:", e
        stream.close()
    finally:
        pass


def getSupportedDeviceFamily(conf):
    '''
    :param dict: conf -- device family configuration in dict format, not the whole conf, conf['deviceFamily']
    :returns list: device model/family (exactly as it is appeared on junos)

    '''
    if conf is None:
        raise ValueError("Missing configuration data")
    return conf.keys()
    

def getPortNamesForDeviceFamily(deviceFamily, conf):
    '''
    returns all port names for a device family grouped by uplink/downlink
    ex - xe-0/0/0, xe-0/0/1 ... xe-0/0/47
    For some device family (qfx5100-24q-2p) there is no specific uplink/downlink, 
    for those it is just a list in the dict.
    
    :param str: deviceFamily -- example qfx5100-24q-2p
    :param dict: conf -- device family configuration in dict format, example in openclos.yaml
    :returns dict: portNames
        uplinkPorts: 
        downlinkPorts:
        ports: list of ports that are not tagged, example qfx5100-24q-2p 
    '''

    if conf is None:
        raise ValueError("Missing configuration data")
    
    if deviceFamily not in conf:
        raise ValueError("Unknown device family: %s" % (deviceFamily))
    
    portMapping = conf[deviceFamily]
    portNames = {'uplinkPorts': [], 'downlinkPorts': [], 'ports': []}
    if 'uplinkPorts' in portMapping:
        portNames['uplinkPorts'] = expandPortName(portMapping['uplinkPorts'])
    if 'downlinkPorts' in portMapping:
        portNames['downlinkPorts'] = expandPortName(portMapping['downlinkPorts'])
    if 'ports' in portMapping:
        portNames['ports'] = expandPortName(portMapping['ports'])
    return portNames

def expandPortName(portName):
    '''    
    Expands portname regular expression to a list
    ex - [xe-0/0/0, xe-0/0/1 ... xe-0/0/47]
    Currently it does not expands all junos regex, only few limited 

    Keyword arguments:
    portName -- port name in junos regular expression, example: xe-0/0/[0-10]
    '''
    if portName is None or portName == '':
        return []
    
    error = "Port name regular expression is not formatted properly: %s, example: xe-0/0/[0-10]" % (portName)
    match = re.match(r"([a-z]+-\d\/\d\/\[)(\d{1,3})-(\d{1,3})(\])", portName)
    if match is None:
        raise ValueError(error)
    
    portNames = []
    preRegx = match.group(1)    # group index starts with 1, NOT 0
    postRegx = match.group(4)
    startNum = int(match.group(2))
    endNum = int(match.group(3))
    
    for id in range(startNum, endNum + 1):
        portNames.append(preRegx[:-1] + str(id) + postRegx[1:])
        
    return portNames

def isPlatformUbuntu():
    #return 'ubuntu' in platform.platform().lower()
    result = os.popen("grep -i ubuntu /etc/*-release").read()
    return result is not None and len(result) > 0

def isPlatformCentos():
    #return 'centos' in platform.platform().lower()
    result = os.popen("grep -i centos /etc/*-release").read()
    return result is not None and len(result) > 0

def isPlatformWindows():
    return 'windows' in platform.platform().lower()

def backupDatabase(conf):
    if conf is not None and 'dbUrl' in conf:
        match = re.match(r"sqlite:\/\/\/(.*)", conf['dbUrl'])
        if match is not None:
            dbFileName = match.group(1)
            if dbFileName != '':
                timestamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
                backupDbFileName = dbFileName + '.' + timestamp
                shutil.copyfile(dbFileName, backupDbFileName)

def getMgmtIps(prefix, startingIP, mask, count):
    '''
    returns list of management IP for given number of devices
    
    Keyword arguments:
    prefix -- ip prefix, example 1.2.3.4/24
    count -- number of devices
    '''
    mgmtIps = []
    cidr = None
    if startingIP is not None and mask is not None:
        cidr = startingIP + '/' + str(mask)
    else:
        cidr = prefix
        
    if cidr is not None:
        ipNetwork = IPNetwork(cidr)
        ipNetworkList = list(ipNetwork)
        start = ipNetworkList.index(ipNetwork.ip)
        end = start + count
        ipList = ipNetworkList[start:end]
        for ip in ipList:
            mgmtIps.append(str(ip) + '/' + str(ipNetwork.prefixlen))

    return mgmtIps

def getMgmtIpsForLeaf():
    return []

def isIntegratedWithND(conf):
    if conf is not None and conf.get('deploymentMode') is not None:
        return conf['deploymentMode'].get('ndIntegrated', False)
    return False
        
def isZtpStaged(conf):
    if conf is not None and conf.get('deploymentMode') is not None:
        return conf['deploymentMode'].get('ztpStaged', False)
    return False

def getZtpStagedInterval(conf):
    if isZtpStaged(conf) == True:
        return conf['deploymentMode'].get('ztpStagedInterval', TWO_STAGE_CONFIGURATOR_DEFAULT_INTERVAL)
    else:
        return None
        
def getZtpStagedAttempt(conf):
    if isZtpStaged(conf) == True:
        return conf['deploymentMode'].get('ztpStagedAttempt', TWO_STAGE_CONFIGURATOR_DEFAULT_ATTEMPT)
    else:
        return None

def getVcpLldpDelay(conf):
    if isZtpStaged(conf) == True:
        return conf['deploymentMode'].get('ztpVcpLldpDelay', TWO_STAGE_CONFIGURATOR_DEFAULT_VCP_LLDP_DELAY)
    else:
        return None
    
def isPrimaryNode():
    '''
    Checks if current node is primary node in cluster.
    Needed to check only for ND integration on centos, as ND can run only on centos.
    For any other platform returns True

    Example output of 'ip a list'
    2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc pfifo_fast qlen 1000
    link/ether 00:50:56:9f:99:d4 brd ff:ff:ff:ff:ff:ff
    inet 192.168.63.251/25 brd 192.168.63.255 scope global eth0
    inet 192.168.63.250/25 brd 192.168.63.255 scope global secondary eth0:0

    :returns bool: True if the node has eth0:0 configured with VIP
    '''
    
    if not isIntegratedWithND() or not isPlatformCentos():
        return True
    
    import subprocess
    proc = subprocess.Popen('/sbin/ip a list dev eth0 | grep -q eth0:0', shell=True)
    returnValue = proc.wait()
    if (returnValue == 0):
        return True
    else:
        return False

def enumerateRoutableIpv4Addresses():
    addrs = []
    intfs = netifaces.interfaces()
    for intf in intfs:
        if intf != 'lo':
            addrDict = netifaces.ifaddresses(intf)
            ipv4AddrInfoList = addrDict.get(netifaces.AF_INET)
            if ipv4AddrInfoList is not None:
                for ipv4AddrInfo in ipv4AddrInfoList:
                    addrs.append(ipv4AddrInfo['addr'])
    return addrs

def modifyConfigTrapTarget(target, confFile = 'openclos.yaml'):
    '''
    Modify openclos.yaml, sets trap target for ND only
    '''
    try:
        lineIterator = fileinput.input(os.path.join(configLocation, confFile), inplace=True) 
        for line in lineIterator:
            if 'networkdirector_trap_group :' in line:
                print line,
                print lineIterator.next(),
                lineIterator.next()
                print '        target : %s' %(target)
            else:
                print line,
        
    except (OSError, IOError) as e:
        print "File error:", e
        return None

def loadLoggingConfig(appName, confFile = 'logging.yaml'):
    '''
    Loads global configuration and creates hash 'conf'
    '''
    try:
        confStream = open(os.path.join(configLocation, confFile), 'r')
        conf = yaml.load(confStream)
        if conf is not None:
            handlers = conf.get('handlers')
            if handlers is not None:
                for handlerName, handlerDict in handlers.items():
                    filename = handlerDict.get('filename')
                    if filename is not None:
                        handlerDict['filename'] = filename.replace('%(appName)', appName)
            # now we are done with substitution, we are ready to start the logging
            logging.config.dictConfig(conf)
            global loggingInitialized
            loggingInitialized = True
    except (OSError, IOError) as e:
        print "File error:", e
    except (yaml.scanner.ScannerError) as e:
        print "YAML error:", e
        confStream.close()
    return loggingInitialized

def loadLoggingConfigForTest(confFile = 'loggingTest.yaml'):
    '''
    Loads global configuration for Test and creates hash 'conf'
    '''
    try:
        confStream = open(os.path.join(configLocation, confFile), 'r')
        conf = yaml.load(confStream)
        if conf is not None:
            logging.config.dictConfig(conf)
            global loggingInitialized
            loggingInitialized = True
    except (OSError, IOError) as e:
        print "File error:", e
    except (yaml.scanner.ScannerError) as e:
        print "YAML error:", e
        confStream.close()
    return loggingInitialized

def getLogger(moduleName):
    '''
    Get logger based on module name
    '''
    if loggingInitialized == False:
        raise ValueError("util.loadLoggingConfig needs to be called before util.getLogger")
        
    return logging.getLogger(moduleName)

def getImageNameForDevice(pod, device):
    if device.role == 'spine':
        return pod.spineJunosImage
    elif device.role == 'leaf':
        for leafSetting in pod.leafSettings:
            if leafSetting.deviceFamily == device.family:
                return leafSetting.junosImage
    
    return None
    