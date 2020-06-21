import os, sys

sys.path.append('/usr/local/CyberCP')
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "CyberCP.settings")
try:
    django.setup()
except:
    pass
import pexpect
from plogical import CyberCPLogFileWriter as logging
import subprocess
import shlex
from shutil import make_archive, rmtree
from plogical import mysqlUtilities
import tarfile
from multiprocessing import Process
import signal
from plogical.installUtilities import installUtilities
import argparse

try:
    from plogical.virtualHostUtilities import virtualHostUtilities
    from plogical.sslUtilities import sslUtilities
    from plogical.mailUtilities import mailUtilities
except:
    pass

from xml.etree.ElementTree import Element, SubElement
from xml.etree import ElementTree
from xml.dom import minidom
import time
from shutil import copy
from distutils.dir_util import copy_tree
from random import randint
from plogical.processUtilities import ProcessUtilities

try:
    from websiteFunctions.models import Websites, ChildDomains, Backups
    from databases.models import Databases
    from loginSystem.models import Administrator
    from plogical.dnsUtilities import DNS
    from mailServer.models import Domains as eDomains
    from backup.models import DBUsers
except:
    pass

VERSION = '2.0'
BUILD = 2


## I am not the monster that you think I am..

class backupUtilities:
    Server_root = "/usr/local/lsws"

    completeKeyPath = "/home/cyberpanel/.ssh"
    destinationsPath = "/home/cyberpanel/destinations"
    licenseKey = '/usr/local/lsws/conf/license.key'

    @staticmethod
    def prepareBackupMeta(backupDomain, backupName, tempStoragePath, backupPath):
        try:

            status = os.path.join(backupPath, 'status')

            logging.CyberCPLogFileWriter.statusWriter(status, 'Setting up meta data..')

            website = Websites.objects.get(domain=backupDomain)

            ######### Generating meta

            ## XML Generation

            metaFileXML = Element('metaFile')

            child = SubElement(metaFileXML, 'VERSION')
            child.text = VERSION

            child = SubElement(metaFileXML, 'BUILD')
            child.text = str(BUILD)

            child = SubElement(metaFileXML, 'masterDomain')
            child.text = backupDomain

            child = SubElement(metaFileXML, 'phpSelection')
            child.text = website.phpSelection

            child = SubElement(metaFileXML, 'externalApp')
            child.text = website.externalApp

            ### Find user of site

            siteUser = website.admin

            child = SubElement(metaFileXML, 'userName')
            child.text = siteUser.userName

            child = SubElement(metaFileXML, 'userPassword')
            child.text = siteUser.password

            child = SubElement(metaFileXML, 'firstName')
            child.text = siteUser.firstName

            child = SubElement(metaFileXML, 'lastName')
            child.text = siteUser.lastName

            child = SubElement(metaFileXML, 'email')
            child.text = siteUser.email

            child = SubElement(metaFileXML, 'type')
            child.text = str(siteUser.type)

            child = SubElement(metaFileXML, 'owner')
            child.text = str(siteUser.owner)

            child = SubElement(metaFileXML, 'token')
            child.text = siteUser.token

            child = SubElement(metaFileXML, 'api')
            child.text = str(siteUser.api)

            child = SubElement(metaFileXML, 'securityLevel')
            child.text = str(siteUser.securityLevel)

            child = SubElement(metaFileXML, 'state')
            child.text = siteUser.state

            child = SubElement(metaFileXML, 'initWebsitesLimit')
            child.text = str(siteUser.initWebsitesLimit)

            child = SubElement(metaFileXML, 'aclName')
            child.text = siteUser.acl.name

            #####################

            childDomains = website.childdomains_set.all()

            databases = website.databases_set.all()

            ## Child domains XML

            childDomainsXML = Element('ChildDomains')

            for items in childDomains:
                childDomainXML = Element('domain')

                child = SubElement(childDomainXML, 'domain')
                child.text = items.domain
                child = SubElement(childDomainXML, 'phpSelection')
                child.text = items.phpSelection
                child = SubElement(childDomainXML, 'path')
                child.text = items.path

                childDomainsXML.append(childDomainXML)

            metaFileXML.append(childDomainsXML)

            ## Databases XML

            databasesXML = Element('Databases')

            for items in databases:
                try:
                    dbuser = DBUsers.objects.get(user=items.dbUser)
                    userToTry = items.dbUser
                except:
                    try:
                        dbusers = DBUsers.objects.all().filter(user=items.dbUser)
                        userToTry = items.dbUser
                        for it in dbusers:
                            dbuser = it
                            break

                        userToTry = mysqlUtilities.mysqlUtilities.fetchuser(items.dbName)

                        if userToTry == 0 or userToTry == 1:
                            continue

                        try:
                            dbuser = DBUsers.objects.get(user=userToTry)
                        except:
                            try:
                                dbusers = DBUsers.objects.all().filter(user=userToTry)
                                for it in dbusers:
                                    dbuser = it
                                    break

                            except BaseException as msg:
                                logging.CyberCPLogFileWriter.writeToFile(
                                    'While creating backup for %s, we failed to backup database %s. Error message: %s' % (
                                        backupDomain, items.dbName, str(msg)))
                                continue
                    except BaseException as msg:
                        logging.CyberCPLogFileWriter.writeToFile(
                            'While creating backup for %s, we failed to backup database %s. Error message: %s' % (
                                backupDomain, items.dbName, str(msg)))
                        continue

                databaseXML = Element('database')

                child = SubElement(databaseXML, 'dbName')
                child.text = str(items.dbName)
                child = SubElement(databaseXML, 'dbUser')
                child.text = str(userToTry)
                child = SubElement(databaseXML, 'password')
                child.text = str(dbuser.password)

                databasesXML.append(databaseXML)

            metaFileXML.append(databasesXML)

            ## Get Aliases

            try:

                aliasesXML = Element('Aliases')

                aliases = backupUtilities.getAliases(backupDomain)

                for items in aliases:
                    child = SubElement(aliasesXML, 'alias')
                    child.text = items

                metaFileXML.append(aliasesXML)

            except BaseException as msg:
                logging.CyberCPLogFileWriter.statusWriter(status, '%s. [167:prepMeta]' % (str(msg)))

            ## Finish Alias

            ## DNS Records XML

            try:

                dnsRecordsXML = Element("dnsrecords")
                dnsRecords = DNS.getDNSRecords(backupDomain)

                for items in dnsRecords:
                    dnsRecordXML = Element('dnsrecord')

                    child = SubElement(dnsRecordXML, 'type')
                    child.text = items.type
                    child = SubElement(dnsRecordXML, 'name')
                    child.text = items.name
                    child = SubElement(dnsRecordXML, 'content')
                    child.text = items.content
                    child = SubElement(dnsRecordXML, 'priority')
                    child.text = str(items.prio)

                    dnsRecordsXML.append(dnsRecordXML)

                metaFileXML.append(dnsRecordsXML)

            except BaseException as msg:
                logging.CyberCPLogFileWriter.statusWriter(status, '%s. [158:prepMeta]' % (str(msg)))

            ## Email accounts XML

            try:
                emailRecordsXML = Element('emails')
                eDomain = eDomains.objects.get(domain=backupDomain)
                emailAccounts = eDomain.eusers_set.all()

                for items in emailAccounts:
                    emailRecordXML = Element('emailAccount')

                    child = SubElement(emailRecordXML, 'email')
                    child.text = items.email
                    child = SubElement(emailRecordXML, 'password')
                    child.text = items.password

                    emailRecordsXML.append(emailRecordXML)

                metaFileXML.append(emailRecordsXML)
            except BaseException as msg:
                logging.CyberCPLogFileWriter.statusWriter(status, '%s. [179:prepMeta]' % (str(msg)))

            ## Email meta generated!

            def prettify(elem):
                """Return a pretty-printed XML string for the Element.
                """
                rough_string = ElementTree.tostring(elem, 'utf-8')
                reparsed = minidom.parseString(rough_string)
                return reparsed.toprettyxml(indent="  ")

            ## /home/example.com/backup/backup-example.com-02.13.2018_10-24-52/meta.xml -- metaPath

            metaPath = '/tmp/%s' % (str(randint(1000, 9999)))

            xmlpretty = prettify(metaFileXML).encode('ascii', 'ignore')
            metaFile = open(metaPath, 'w')
            metaFile.write(xmlpretty.decode())
            metaFile.close()
            os.chmod(metaPath, 0o777)

            ## meta generated

            newBackup = Backups(website=website, fileName=backupName, date=time.strftime("%m.%d.%Y_%H-%M-%S"),
                                size=0, status=1)
            newBackup.save()

            logging.CyberCPLogFileWriter.statusWriter(status, 'Meta data is ready..')

            return 1, 'None', metaPath


        except BaseException as msg:
            logging.CyberCPLogFileWriter.statusWriter(status, "%s [207][5009]" % (str(msg)))
            return 0, str(msg)

    @staticmethod
    def startBackup(tempStoragePath, backupName, backupPath, metaPath=None):
        try:

            ## /home/example.com/backup/backup-example.com-02.13.2018_10-24-52 -- tempStoragePath
            ## /home/example.com/backup - backupPath

            ##### Writing the name of backup file.

            ## /home/example.com/backup/backupFileName
            pidFile = '%sstartBackup' % (backupPath)
            writeToFile = open(pidFile, 'w')
            writeToFile.writelines(str(os.getpid()))
            writeToFile.close()

            backupFileNamePath = os.path.join(backupPath, "backupFileName")
            logging.CyberCPLogFileWriter.statusWriter(backupFileNamePath, backupName)

            #####

            status = os.path.join(backupPath, 'status')

            logging.CyberCPLogFileWriter.statusWriter(status, "Making archive of home directory.\n")

            ##### Parsing XML Meta file!

            ## /home/example.com/backup/backup-example.com-02.13.2018_10-24-52 -- tempStoragePath

            metaPathInBackup = os.path.join(tempStoragePath, 'meta.xml')

            if metaPath != None:
                writeToFile = open(metaPathInBackup, 'w')
                writeToFile.write(open(metaPath, 'r').read())
                writeToFile.close()

            backupMetaData = ElementTree.parse(metaPathInBackup)

            ##### Making archive of home directory

            domainName = backupMetaData.find('masterDomain').text

            ## Saving original vhost conf file

            completPathToConf = backupUtilities.Server_root + '/conf/vhosts/' + domainName + '/vhost.conf'

            if os.path.exists(backupUtilities.licenseKey):
                copy(completPathToConf, tempStoragePath + '/vhost.conf')

            ## /home/example.com/backup/backup-example.com-02.13.2018_10-24-52 -- tempStoragePath
            ## shutil.make_archive

            ## Stop making archive of document_root and copy instead

            copy_tree('/home/%s/public_html' % domainName, '%s/%s' % (tempStoragePath, 'public_html'))

            # make_archive(os.path.join(tempStoragePath,"public_html"), 'gztar', os.path.join("/home",domainName,"public_html"))

            ##

            logging.CyberCPLogFileWriter.statusWriter(status, "Backing up databases..")
            print('1,None')

        except BaseException as msg:
            try:
                os.remove(os.path.join(backupPath, backupName + ".tar.gz"))
            except:
                pass

            try:
                rmtree(tempStoragePath)
            except:
                pass

            status = os.path.join(backupPath, 'status')
            logging.CyberCPLogFileWriter.statusWriter(status, "Aborted, " + str(msg) + ".[365] [5009]")
            print(("Aborted, " + str(msg) + ".[365] [5009]"))

        os.remove(pidFile)

    @staticmethod
    def BackupRoot(tempStoragePath, backupName, backupPath, metaPath=None):

        pidFile = '%sBackupRoot' % (backupPath)

        writeToFile = open(pidFile, 'w')
        writeToFile.writelines(str(os.getpid()))
        writeToFile.close()

        status = os.path.join(backupPath, 'status')
        metaPathInBackup = os.path.join(tempStoragePath, 'meta.xml')
        backupMetaData = ElementTree.parse(metaPathInBackup)

        domainName = backupMetaData.find('masterDomain').text
        ##### Saving SSL Certificates if any

        sslStoragePath = '/etc/letsencrypt/live/' + domainName

        if os.path.exists(sslStoragePath):
            try:
                copy(os.path.join(sslStoragePath, "cert.pem"), os.path.join(tempStoragePath, domainName + ".cert.pem"))
                copy(os.path.join(sslStoragePath, "fullchain.pem"),
                     os.path.join(tempStoragePath, domainName + ".fullchain.pem"))
                copy(os.path.join(sslStoragePath, "privkey.pem"),
                     os.path.join(tempStoragePath, domainName + ".privkey.pem"))
            except BaseException as msg:
                logging.CyberCPLogFileWriter.writeToFile('%s. [283:startBackup]' % (str(msg)))

        ## Child Domains SSL.

        childDomains = backupMetaData.findall('ChildDomains/domain')

        try:
            for childDomain in childDomains:

                actualChildDomain = childDomain.find('domain').text
                childPath = childDomain.find('path').text

                if os.path.exists(backupUtilities.licenseKey):
                    completPathToConf = backupUtilities.Server_root + '/conf/vhosts/' + actualChildDomain + '/vhost.conf'
                    copy(completPathToConf, tempStoragePath + '/' + actualChildDomain + '.vhost.conf')

                    ### Storing SSL for child domainsa

                sslStoragePath = '/etc/letsencrypt/live/' + actualChildDomain

                if os.path.exists(sslStoragePath):
                    try:
                        copy(os.path.join(sslStoragePath, "cert.pem"),
                             os.path.join(tempStoragePath, actualChildDomain + ".cert.pem"))
                        copy(os.path.join(sslStoragePath, "fullchain.pem"),
                             os.path.join(tempStoragePath, actualChildDomain + ".fullchain.pem"))
                        copy(os.path.join(sslStoragePath, "privkey.pem"),
                             os.path.join(tempStoragePath, actualChildDomain + ".privkey.pem"))
                        make_archive(os.path.join(tempStoragePath, "sslData-" + domainName), 'gztar',
                                     sslStoragePath)
                    except:
                        pass

                if childPath.find('/home/%s/public_html' % domainName) == -1:
                    copy_tree(childPath, '%s/%s-docroot' % (tempStoragePath, actualChildDomain))

        except BaseException as msg:
            pass

        ## backup emails

        domainName = backupMetaData.find('masterDomain').text

        if os.path.islink(status) or os.path.islink(tempStoragePath or os.path.islink(backupPath)) or os.path.islink(
                metaPath):
            logging.CyberCPLogFileWriter.writeToFile('symlinked.')
            logging.CyberCPLogFileWriter.statusWriter(status, 'Symlink attack. [365][5009]')
            return 0

        ## backup email accounts

        logging.CyberCPLogFileWriter.statusWriter(status, "Backing up email accounts..\n")

        try:

            emailPath = '/home/vmail/%s' % (domainName)

            if os.path.exists(emailPath):
                copy_tree(emailPath, '%s/vmail' % (tempStoragePath), preserve_symlinks=True)

            ## shutil.make_archive. Creating final package.

            make_archive(os.path.join(backupPath, backupName), 'gztar', tempStoragePath)
            rmtree(tempStoragePath)

            ###

            backupObs = Backups.objects.filter(fileName=backupName)

            ## adding backup data to database.

            filePath = '%s/%s.tar.gz' % (backupPath, backupName)
            totalSize = '%sMB' % (str(int(os.path.getsize(filePath) / 1048576)))

            try:
                for items in backupObs:
                    items.status = 1
                    items.size = totalSize
                    items.save()
            except BaseException as msg:
                logging.CyberCPLogFileWriter.writeToFile('%s. [backupRoot:499]' % str(msg))
                for items in backupObs:
                    items.status = 1
                    items.size = totalSize
                    items.save()

            command = 'chmod 600 %s' % (os.path.join(backupPath, backupName + ".tar.gz"))
            ProcessUtilities.executioner(command)

            logging.CyberCPLogFileWriter.statusWriter(status, "Completed\n")
            os.remove(pidFile)
        except BaseException as msg:
            logging.CyberCPLogFileWriter.statusWriter(status, '%s. [511:BackupRoot][[5009]]\n' % str(msg))

    @staticmethod
    def initiateBackup(tempStoragePath, backupName, backupPath):
        try:
            p = Process(target=backupUtilities.startBackup, args=(tempStoragePath, backupName, backupPath,))
            p.start()
            pid = open(backupPath + 'pid', "w")
            pid.write(str(p.pid))
            pid.close()
        except BaseException as msg:
            logging.CyberCPLogFileWriter.writeToFile(str(msg) + " [initiateBackup]")

    @staticmethod
    def createWebsiteFromBackup(backupFileOrig, dir):
        try:
            backupFile = backupFileOrig.strip(".tar.gz")
            originalFile = "/home/backup/" + backupFileOrig

            if os.path.exists(backupFileOrig):
                path = backupFile
            elif not os.path.exists(originalFile):
                dir = dir
                path = "/home/backup/transfer-" + str(dir) + "/" + backupFile
            else:
                path = "/home/backup/" + backupFile

            admin = Administrator.objects.get(userName='admin')

            ## open meta file to read data

            ## Parsing XML Meta file!

            backupMetaData = ElementTree.parse(os.path.join(path, 'meta.xml'))

            domain = backupMetaData.find('masterDomain').text
            phpSelection = backupMetaData.find('phpSelection').text
            externalApp = backupMetaData.find('externalApp').text

            ### Fetch user details

            try:

                userName = backupMetaData.find('userName').text

                try:
                    siteUser = Administrator.objects.get(userName=userName)
                except:
                    userPassword = backupMetaData.find('userPassword').text
                    firstName = backupMetaData.find('firstName').text
                    lastName = backupMetaData.find('lastName').text
                    email = backupMetaData.find('email').text
                    type = int(backupMetaData.find('type').text)
                    owner = int(backupMetaData.find('owner').text)
                    token = backupMetaData.find('token').text
                    api = int(backupMetaData.find('api').text)
                    securityLevel = int(backupMetaData.find('securityLevel').text)
                    state = backupMetaData.find('state').text
                    initWebsitesLimit = int(backupMetaData.find('initWebsitesLimit').text)
                    from loginSystem.models import ACL
                    acl = ACL.objects.get(name=backupMetaData.find('aclName').text)
                    siteUser = Administrator(userName=userName, password=userPassword, firstName=firstName,
                                             initWebsitesLimit=initWebsitesLimit, acl=acl,
                                             lastName=lastName, email=email, type=type, owner=owner, token=token,
                                             api=api, securityLevel=securityLevel, state=state)
                    siteUser.save()
            except:
                siteUser = Administrator.objects.get(userName='admin')

            ## Pre-creation checks

            if Websites.objects.filter(domain=domain).count() > 0:
                raise BaseException('This website already exists.')

            if ChildDomains.objects.filter(domain=domain).count() > 0:
                raise BaseException("This website already exists as child domain.")

            ####### Pre-creation checks ends

            ## Create Configurations

            result = virtualHostUtilities.createVirtualHost(domain, siteUser.email, phpSelection, externalApp, 0, 1, 0,
                                                            siteUser.userName, 'Default', 0)

            if result[0] == 0:
                raise BaseException(result[1])

            ## Create Configurations ends here

            ## Create databases

            databases = backupMetaData.findall('Databases/database')
            website = Websites.objects.get(domain=domain)

            for database in databases:
                dbName = database.find('dbName').text
                dbUser = database.find('dbUser').text

                if mysqlUtilities.mysqlUtilities.createDatabase(dbName, dbUser, "cyberpanel") == 0:
                    raise BaseException("Failed to create Databases!")

                newDB = Databases(website=website, dbName=dbName, dbUser=dbUser)
                newDB.save()

            ## Create dns zone

            dnsrecords = backupMetaData.findall('dnsrecords/dnsrecord')

            DNS.createDNSZone(domain, admin)

            zone = DNS.getZoneObject(domain)

            for dnsrecord in dnsrecords:
                recordType = dnsrecord.find('type').text
                value = dnsrecord.find('name').text
                content = dnsrecord.find('content').text
                prio = int(dnsrecord.find('priority').text)

                DNS.createDNSRecord(zone, value, recordType, content, prio, 3600)

            return 1, 'None'

        except BaseException as msg:
            return 0, str(msg)

    @staticmethod
    def startRestore(backupName, dir):
        try:

            if dir == "CyberPanelRestore":
                backupFileName = backupName.strip(".tar.gz")
                completPath = os.path.join("/home", "backup", backupFileName)  ## without extension
                originalFile = os.path.join("/home", "backup", backupName)  ## with extension
            elif dir == 'CLI':
                completPath = backupName.strip(".tar.gz")  ## without extension
                originalFile = backupName  ## with extension
            else:
                backupFileName = backupName.strip(".tar.gz")
                completPath = "/home/backup/transfer-" + str(dir) + "/" + backupFileName  ## without extension
                originalFile = "/home/backup/transfer-" + str(dir) + "/" + backupName  ## with extension

            pathToCompressedHome = os.path.join(completPath, "public_html.tar.gz")

            if not os.path.exists(completPath):
                os.mkdir(completPath)

            ## Writing pid of restore process

            pid = os.path.join(completPath, 'pid')

            logging.CyberCPLogFileWriter.statusWriter(pid, str(os.getpid()))

            status = os.path.join(completPath, 'status')
            logging.CyberCPLogFileWriter.statusWriter(status, "Extracting Main Archive!")

            ## Converting /home/backup/backup-example.com-02.13.2018_10-24-52.tar.gz -> /home/backup/backup-example.com-02.13.2018_10-24-52

            tar = tarfile.open(originalFile)
            tar.extractall(completPath)
            tar.close()

            logging.CyberCPLogFileWriter.statusWriter(status, "Creating Accounts,Databases and DNS records!")

            ########### Creating website and its dabases

            ## extracting master domain for later use
            backupMetaData = ElementTree.parse(os.path.join(completPath, "meta.xml"))
            masterDomain = backupMetaData.find('masterDomain').text

            twoPointO = 0
            try:
                version = backupMetaData.find('VERSION').text
                build = backupMetaData.find('BUILD').text
                twoPointO = 1
            except:
                twoPointO = 0

            result = backupUtilities.createWebsiteFromBackup(backupName, dir)

            if result[0] == 1:
                ## Let us try to restore SSL.

                sslStoragePath = completPath + "/" + masterDomain + ".cert.pem"

                if os.path.exists(sslStoragePath):
                    sslHome = '/etc/letsencrypt/live/' + masterDomain

                    try:
                        if not os.path.exists(sslHome):
                            os.mkdir(sslHome)

                        copy(completPath + "/" + masterDomain + ".cert.pem", sslHome + "/cert.pem")
                        copy(completPath + "/" + masterDomain + ".privkey.pem", sslHome + "/privkey.pem")
                        copy(completPath + "/" + masterDomain + ".fullchain.pem", sslHome + "/fullchain.pem")

                        sslUtilities.installSSLForDomain(masterDomain)
                    except BaseException as msg:
                        logging.CyberCPLogFileWriter.writeToFile('%s. [555:startRestore]' % (str(msg)))

            else:
                logging.CyberCPLogFileWriter.statusWriter(status, "Error Message: " + result[
                    1] + ". Not able to create Account, Databases and DNS Records, aborting. [575][5009]")
                return 0

            ########### Creating child/sub/addon/parked domains

            logging.CyberCPLogFileWriter.statusWriter(status, "Creating Child Domains!")

            ## Reading meta file to create subdomains

            externalApp = backupMetaData.find('externalApp').text
            websiteHome = os.path.join("/home", masterDomain, "public_html")

            ### Restoring Child Domains if any.

            childDomains = backupMetaData.findall('ChildDomains/domain')

            try:
                for childDomain in childDomains:

                    domain = childDomain.find('domain').text

                    ## mail domain check

                    mailDomain = 'mail.%s' % (masterDomain)

                    if domain == mailDomain:
                        continue

                    ## Mail domain check

                    phpSelection = childDomain.find('phpSelection').text
                    path = childDomain.find('path').text

                    retValues = virtualHostUtilities.createDomain(masterDomain, domain, phpSelection, path, 0, 0, 0,
                                                                  'admin', 0)

                    if retValues[0] == 1:
                        if os.path.exists(websiteHome):
                            rmtree(websiteHome)

                        ## Let us try to restore SSL for Child Domains.

                        try:

                            if os.path.exists(backupUtilities.licenseKey):
                                if os.path.exists(completPath + '/' + domain + '.vhost.conf'):
                                    completPathToConf = backupUtilities.Server_root + '/conf/vhosts/' + domain + '/vhost.conf'
                                    copy(completPath + '/' + domain + '.vhost.conf', completPathToConf)

                            sslStoragePath = completPath + "/" + domain + ".cert.pem"

                            if os.path.exists(sslStoragePath):
                                sslHome = '/etc/letsencrypt/live/' + domain

                                try:
                                    if not os.path.exists(sslHome):
                                        os.mkdir(sslHome)

                                    copy(completPath + "/" + domain + ".cert.pem", sslHome + "/cert.pem")
                                    copy(completPath + "/" + domain + ".privkey.pem", sslHome + "/privkey.pem")
                                    copy(completPath + "/" + domain + ".fullchain.pem",
                                         sslHome + "/fullchain.pem")

                                    sslUtilities.installSSLForDomain(domain)
                                except:
                                    pass
                        except:
                            logging.CyberCPLogFileWriter.writeToFile(
                                'While restoring backup we had minor issues for rebuilding vhost conf for: ' + domain + '. However this will be auto healed.')

                        if float(version) > 2.0 or float(build) > 0:
                            if path.find('/home/%s/public_html' % masterDomain) == -1:
                                copy_tree('%s/%s-docroot' % (completPath, domain), path)

                        continue
                    else:
                        logging.CyberCPLogFileWriter.writeToFile('Error domain %s' % (domain))
                        logging.CyberCPLogFileWriter.statusWriter(status, "Error Message: " + retValues[
                            1] + ". Not able to create child domains, aborting. [635][5009]")
                        return 0
            except BaseException as msg:
                status = open(os.path.join(completPath, 'status'), "w")
                status.write("Error Message: " + str(msg) + ". Not able to create child domains, aborting. [638][5009]")
                status.close()
                logging.CyberCPLogFileWriter.writeToFile(str(msg) + " [startRestore]")
                return 0

            ## Restore Aliases

            logging.CyberCPLogFileWriter.statusWriter(status, "Restoring Domain Aliases!")

            aliases = backupMetaData.findall('Aliases/alias')

            for items in aliases:
                virtualHostUtilities.createAlias(masterDomain, items.text, 0, "", "", "admin")

            ## Restoring email accounts

            logging.CyberCPLogFileWriter.statusWriter(status, "Restoring email accounts!")

            emailAccounts = backupMetaData.findall('emails/emailAccount')

            try:
                for emailAccount in emailAccounts:

                    email = emailAccount.find('email').text
                    username = email.split("@")[0]
                    password = emailAccount.find('password').text

                    result = mailUtilities.createEmailAccount(masterDomain, username, password, 'restore')
                    if result[0] == 0:
                        raise BaseException(result[1])
            except BaseException as msg:
                logging.CyberCPLogFileWriter.statusWriter(status, "Error Message: " + str(
                    msg) + ". Not able to create email accounts, aborting. [671][5009]")
                logging.CyberCPLogFileWriter.writeToFile(str(msg) + " [startRestore]")
                return 0

            ## Emails restored

            ## restoring databases

            logging.CyberCPLogFileWriter.statusWriter(status, "Restoring Databases!")

            databases = backupMetaData.findall('Databases/database')

            for database in databases:
                dbName = database.find('dbName').text
                password = database.find('password').text
                if mysqlUtilities.mysqlUtilities.restoreDatabaseBackup(dbName, completPath, password) == 0:
                    raise BaseException

            ## Databases restored

            logging.CyberCPLogFileWriter.statusWriter(status, "Extracting web home data!")

            # /home/backup/backup-example.com-02.13.2018_10-24-52/public_html.tar.gz
            ## Moving above v2.0.0 extracting webhome data is not required, thus commenting below lines

            if not twoPointO:
                tar = tarfile.open(pathToCompressedHome)
                tar.extractall(websiteHome)
                tar.close()
            else:
                if float(version) > 2.0 or float(build) > 0:
                    copy_tree('%s/public_html' % (completPath), websiteHome)

            ## extracting email accounts

            logging.CyberCPLogFileWriter.statusWriter(status, "Extracting email accounts!")

            if not twoPointO:

                try:
                    pathToCompressedEmails = os.path.join(completPath, masterDomain + ".tar.gz")
                    emailHome = os.path.join("/home", "vmail", masterDomain)

                    tar = tarfile.open(pathToCompressedEmails)
                    tar.extractall(emailHome)
                    tar.close()

                    ## Change permissions

                    command = "chown -R vmail:vmail " + emailHome
                    subprocess.call(shlex.split(command))

                except:
                    pass
            else:

                emailsPath = '%s/vmail' % (completPath)

                if os.path.exists(emailsPath):
                    copy_tree(emailsPath, '/home/vmail/%s' % (masterDomain))

                command = "chown -R vmail:vmail /home/vmail/%s" % (masterDomain)
                ProcessUtilities.executioner(command)

            ## emails extracted

            if os.path.exists(backupUtilities.licenseKey):
                completPathToConf = backupUtilities.Server_root + '/conf/vhosts/' + masterDomain + '/vhost.conf'
                if os.path.exists(completPath + '/vhost.conf'):
                    copy(completPath + '/vhost.conf', completPathToConf)

            logging.CyberCPLogFileWriter.statusWriter(status, "Done")

            installUtilities.reStartLiteSpeed()

            ## Fix permissions

            from filemanager.filemanager import FileManager

            fm = FileManager(None, None)
            fm.fixPermissions(masterDomain)

        except BaseException as msg:
            status = os.path.join(completPath, 'status')
            logging.CyberCPLogFileWriter.statusWriter(status, str(msg) + " [736][5009]")
            logging.CyberCPLogFileWriter.writeToFile(str(msg) + " [startRestore]")

    @staticmethod
    def initiateRestore(backupName, dir):
        try:
            p = Process(target=backupUtilities.startRestore, args=(backupName, dir,))
            p.start()
        except BaseException as msg:
            logging.CyberCPLogFileWriter.writeToFile(str(msg) + " [initiateRestore]")

    @staticmethod
    def sendKey(IPAddress, password, port='22', user='root'):
        try:

            expectation = []
            expectation.append("password:")
            expectation.append("Password:")
            expectation.append("Permission denied")
            expectation.append("100%")

            ## Temp changes

            command = 'chmod 600 %s' % ('/root/.ssh/cyberpanel.pub')
            ProcessUtilities.executioner(command)

            command = "scp -o StrictHostKeyChecking=no -P " + port + " /root/.ssh/cyberpanel.pub " + user + "@" + IPAddress + ":~/.ssh/authorized_keys"
            setupKeys = pexpect.spawn(command, timeout=3)

            if os.path.exists(ProcessUtilities.debugPath):
                logging.CyberCPLogFileWriter.writeToFile(command)

            index = setupKeys.expect(expectation)

            ## on first login attempt send password

            if index == 0:
                setupKeys.sendline(password)
                setupKeys.expect("100%")
                setupKeys.wait()
            elif index == 1:
                setupKeys.sendline(password)
                setupKeys.expect("100%")
                setupKeys.wait()
            elif index == 2:
                return [0, 'Please enable password authentication on your remote server.']
            elif index == 3:
                pass
            else:
                raise BaseException

            ## Temp changes

            command = 'chmod 644 %s' % ('/root/.ssh/cyberpanel.pub')
            ProcessUtilities.executioner(command)

            return [1, "None"]

        except pexpect.TIMEOUT as msg:

            command = 'chmod 644 %s' % ('/root/.ssh/cyberpanel.pub')
            ProcessUtilities.executioner(command)

            logging.CyberCPLogFileWriter.writeToFile(str(msg) + " [sendKey]")
            return [0, "TIMEOUT [sendKey]"]
        except pexpect.EOF as msg:

            command = 'chmod 644 %s' % ('/root/.ssh/cyberpanel.pub')
            ProcessUtilities.executioner(command)

            logging.CyberCPLogFileWriter.writeToFile(str(msg) + " [sendKey]")
            return [0, "EOF [sendKey]"]
        except BaseException as msg:

            command = 'chmod 644 %s' % ('/root/.ssh/cyberpanel.pub')
            ProcessUtilities.executioner(command)

            logging.CyberCPLogFileWriter.writeToFile(str(msg) + " [sendKey]")
            return [0, str(msg) + " [sendKey]"]

    @staticmethod
    def setupSSHKeys(IPAddress, password, port='22', user='root'):
        try:
            ## Checking for host verification

            backupUtilities.host_key_verification(IPAddress)

            if backupUtilities.checkIfHostIsUp(IPAddress) == 1:
                pass
            else:
                logging.CyberCPLogFileWriter.writeToFile("Host is Down.")
                # return [0,"Host is Down."]

            expectation = []
            expectation.append("password:")
            expectation.append("Password:")
            expectation.append("Permission denied")
            expectation.append("File exists")

            command = "ssh -o StrictHostKeyChecking=no -p " + port + ' ' + user + "@" + IPAddress + ' "mkdir ~/.ssh || rm -f ~/.ssh/temp && rm -f ~/.ssh/authorized_temp && cp ~/.ssh/authorized_keys ~/.ssh/temp || chmod 700 ~/.ssh || chmod g-w ~"'
            setupKeys = pexpect.spawn(command, timeout=3)

            if os.path.exists(ProcessUtilities.debugPath):
                logging.CyberCPLogFileWriter.writeToFile(command)

            index = setupKeys.expect(expectation)

            ## on first login attempt send password

            if index == 0:
                setupKeys.sendline(password)
            elif index == 1:
                setupKeys.sendline(password)
            elif index == 2:
                return [0, 'Please enable password authentication on your remote server.']
            elif index == 3:
                pass
            else:
                raise BaseException

            ## if it again give you password, than provided password is wrong

            expectation = []
            expectation.append("please try again.")
            expectation.append("Password:")
            expectation.append(pexpect.EOF)

            index = setupKeys.expect(expectation)

            if index == 0:
                return [0, "Wrong Password!"]
            elif index == 1:
                return [0, "Wrong Password!"]
            elif index == 2:
                setupKeys.wait()

                sendKey = backupUtilities.sendKey(IPAddress, password, port, user)

                if sendKey[0] == 1:
                    return [1, "None"]
                else:
                    return [0, sendKey[1]]


        except pexpect.TIMEOUT as msg:
            return [0, str(msg) + " [TIMEOUT setupSSHKeys]"]
        except BaseException as msg:
            return [0, str(msg) + " [setupSSHKeys]"]

    @staticmethod
    def checkIfHostIsUp(IPAddress):
        try:
            if subprocess.check_output(['ping', IPAddress, '-c 1']).decode("utf-8").find("0% packet loss") > -1:
                return 1
            else:
                return 0
        except BaseException as msg:
            logging.CyberCPLogFileWriter.writeToFile(str(msg) + "[checkIfHostIsUp]")

    @staticmethod
    def checkConnection(IPAddress, port='22', user='root'):
        try:

            try:
                import json
                destinations = backupUtilities.destinationsPath
                data = json.loads(open(destinations, 'r').read())
                port = data['port']
                user = data['user']
            except:
                port = "22"

            expectation = []
            expectation.append("password:")
            expectation.append("Password:")
            expectation.append("Last login")
            expectation.append(pexpect.EOF)
            expectation.append(pexpect.TIMEOUT)

            command = "sudo ssh -i /root/.ssh/cyberpanel -o StrictHostKeyChecking=no -p " + port + ' ' + user + "@" + IPAddress

            if os.path.exists(ProcessUtilities.debugPath):
                logging.CyberCPLogFileWriter.writeToFile(command)

            checkConn = pexpect.spawn(command,timeout=3)
            index = checkConn.expect(expectation)

            if index == 0:
                subprocess.call(['kill', str(checkConn.pid)])
                logging.CyberCPLogFileWriter.writeToFile(
                    "Remote Server is not able to authenticate for transfer to initiate, IP Address:" + IPAddress)
                return [0, "Remote Server is not able to authenticate for transfer to initiate."]
            elif index == 1:
                subprocess.call(['kill', str(checkConn.pid)])
                logging.CyberCPLogFileWriter.writeToFile(
                    "Remote Server is not able to authenticate for transfer to initiate, IP Address:" + IPAddress)
                return [0, "Remote Server is not able to authenticate for transfer to initiate."]
            elif index == 2:
                subprocess.call(['kill', str(checkConn.pid)])
                return [1, "None"]
            elif index == 4:
                subprocess.call(['kill', str(checkConn.pid)])
                return [1, "None"]
            else:
                subprocess.call(['kill', str(checkConn.pid)])
                return [1, "None"]

        except pexpect.TIMEOUT as msg:
            logging.CyberCPLogFileWriter.writeToFile("Timeout " + IPAddress + " [checkConnection]")
            return [0, "371 Timeout while making connection to this server [checkConnection]"]
        except pexpect.EOF as msg:
            logging.CyberCPLogFileWriter.writeToFile("EOF " + IPAddress + "[checkConnection]")
            return [0, "374 Remote Server is not able to authenticate for transfer to initiate. [checkConnection]"]
        except BaseException as msg:
            logging.CyberCPLogFileWriter.writeToFile(str(msg) + " " + IPAddress + " [checkConnection]")
            return [0, "377 Remote Server is not able to authenticate for transfer to initiate. [checkConnection]"]

    @staticmethod
    def verifyHostKey(IPAddress, port='22', user='root'):
        try:
            backupUtilities.host_key_verification(IPAddress)

            password = "hello"  ## dumb password, not used anywhere.

            expectation = []

            expectation.append("continue connecting (yes/no)?")
            expectation.append("password:")

            setupSSHKeys = pexpect.spawn("ssh -p " + port + user + "@" + IPAddress, timeout=3)

            index = setupSSHKeys.expect(expectation)

            if index == 0:
                setupSSHKeys.sendline("yes")

                setupSSHKeys.expect("password:")
                setupSSHKeys.sendline(password)

                expectation = []

                expectation.append("password:")
                expectation.append(pexpect.EOF)

                innerIndex = setupSSHKeys.expect(expectation)

                if innerIndex == 0:
                    setupSSHKeys.kill(signal.SIGTERM)
                    return [1, "None"]
                elif innerIndex == 1:
                    setupSSHKeys.kill(signal.SIGTERM)
                    return [1, "None"]

            elif index == 1:

                setupSSHKeys.expect("password:")
                setupSSHKeys.sendline(password)

                expectation = []

                expectation.append("password:")
                expectation.append(pexpect.EOF)

                innerIndex = setupSSHKeys.expect(expectation)

                if innerIndex == 0:
                    setupSSHKeys.kill(signal.SIGTERM)
                    return [1, "None"]
                elif innerIndex == 1:
                    setupSSHKeys.kill(signal.SIGTERM)
                    return [1, "None"]


        except pexpect.TIMEOUT as msg:
            logging.CyberCPLogFileWriter.writeToFile("Timeout [verifyHostKey]")
            return [0, "Timeout [verifyHostKey]"]
        except pexpect.EOF as msg:
            logging.CyberCPLogFileWriter.writeToFile("EOF [verifyHostKey]")
            return [0, "EOF [verifyHostKey]"]
        except BaseException as msg:
            logging.CyberCPLogFileWriter.writeToFile(str(msg) + " [verifyHostKey]")
            return [0, str(msg) + " [verifyHostKey]"]

    @staticmethod
    def createBackupDir(IPAddress, port='22', user='root'):

        try:
            command = "sudo ssh -o StrictHostKeyChecking=no -p " + port + " -i /root/.ssh/cyberpanel " + user + "@" + IPAddress + " mkdir ~/backup"

            if os.path.exists(ProcessUtilities.debugPath):
                logging.CyberCPLogFileWriter.writeToFile(command)

            subprocess.call(shlex.split(command))

            command = "sudo ssh -o StrictHostKeyChecking=no -p " + port + " -i /root/.ssh/cyberpanel " + user + "@" + IPAddress + ' "cat ~/.ssh/authorized_keys ~/.ssh/temp > ~/.ssh/authorized_temp"'

            if os.path.exists(ProcessUtilities.debugPath):
                logging.CyberCPLogFileWriter.writeToFile(command)

            subprocess.call(shlex.split(command))


            command = "sudo ssh -o StrictHostKeyChecking=no -p " + port + " -i /root/.ssh/cyberpanel " + user + "@" + IPAddress + ' "cat ~/.ssh/authorized_temp > ~/.ssh/authorized_keys"'

            if os.path.exists(ProcessUtilities.debugPath):
                logging.CyberCPLogFileWriter.writeToFile(command)

            subprocess.call(shlex.split(command))

        except BaseException as msg:
            logging.CyberCPLogFileWriter.writeToFile(str(msg) + " [createBackupDir]")
            return 0

    @staticmethod
    def host_key_verification(IPAddress):
        try:
            command = 'sudo ssh-keygen -R ' + IPAddress
            subprocess.call(shlex.split(command))
            return 1
        except BaseException as msg:
            logging.CyberCPLogFileWriter.writeToFile(str(msg) + " [host_key_verification]")
            return 0

    @staticmethod
    def getAliases(masterDomain):
        try:
            aliases = []
            master = Websites.objects.get(domain=masterDomain)
            aliasDomains = master.aliasdomains_set.all()

            for items in aliasDomains:
                aliases.append(items.aliasDomain)

            return aliases

        except BaseException as msg:
            logging.CyberCPLogFileWriter.writeToFile(str(msg) + "  [getAliases]")
            print(0)


def submitBackupCreation(tempStoragePath, backupName, backupPath, backupDomain):
    try:
        ## /home/example.com/backup/backup-example.com-02.13.2018_10-24-52 -- tempStoragePath
        ## backup-example.com-02.13.2018_10-24-52 -- backup name
        ## /home/example.com/backup - backupPath
        ## /home/cyberpanel/1047.xml - metaPath

        status = os.path.join(backupPath, 'status')
        website = Websites.objects.get(domain=backupDomain)

        ##

        schedulerPath = '/home/cyberpanel/%s-backup.txt' % (backupDomain)

        if not os.path.exists(backupPath) or not os.path.islink(backupPath):
            command = 'mkdir -p %s' % (backupPath)
            ProcessUtilities.executioner(command)
        else:
            writeToFile = open(schedulerPath, 'w')
            writeToFile.writelines('1269')
            writeToFile.close()
            return 0

        if not os.path.exists(backupPath) or not os.path.islink(backupPath):
            command = 'chown -R %s:%s %s' % (website.externalApp, website.externalApp, backupPath)
            ProcessUtilities.executioner(command)
        else:
            writeToFile = open(schedulerPath, 'w')
            writeToFile.writelines('1278')
            writeToFile.close()
            return 0

        ##

        if not os.path.exists(tempStoragePath) or not os.path.islink(tempStoragePath):
            command = 'mkdir -p %s' % (tempStoragePath)
            ProcessUtilities.executioner(command)
        else:
            writeToFile = open(schedulerPath, 'w')
            writeToFile.writelines('1289')
            writeToFile.close()
            return 0

        if not os.path.exists(tempStoragePath) or not os.path.islink(tempStoragePath):
            command = 'chown -R %s:%s %s' % (website.externalApp, website.externalApp, tempStoragePath)
            ProcessUtilities.executioner(command)
        else:
            writeToFile = open(schedulerPath, 'w')
            writeToFile.writelines('1298')
            writeToFile.close()
            return 0

        ##
        if not os.path.exists(status) or not os.path.islink(status):
            command = 'touch %s' % (status)
            ProcessUtilities.executioner(command)
        else:
            writeToFile = open(schedulerPath, 'w')
            writeToFile.writelines('1308')
            writeToFile.close()
            return 0

        if not os.path.exists(status) or not os.path.islink(status):
            command = 'chown cyberpanel:cyberpanel %s' % (status)
            ProcessUtilities.executioner(command)
        else:
            writeToFile = open(schedulerPath, 'w')
            writeToFile.writelines('1317')
            writeToFile.close()
            return 0

        result = backupUtilities.prepareBackupMeta(backupDomain, backupName, tempStoragePath, backupPath)

        if result[0] == 0:
            writeToFile = open(schedulerPath, 'w')
            writeToFile.writelines('1325')
            writeToFile.close()
            logging.CyberCPLogFileWriter.statusWriter(status, str(result[1]) + ' [1084][5009]')
            return 0

        command = 'chown %s:%s %s' % (website.externalApp, website.externalApp, status)
        ProcessUtilities.executioner(command)

        execPath = "sudo nice -n 10 /usr/local/CyberCP/bin/python " + virtualHostUtilities.cyberPanel + "/plogical/backupUtilities.py"
        execPath = execPath + " startBackup --tempStoragePath " + tempStoragePath + " --backupName " \
                   + backupName + " --backupPath " + backupPath + ' --backupDomain ' + backupDomain + ' --metaPath %s' % (
                       result[2])

        output = ProcessUtilities.outputExecutioner(execPath, website.externalApp)
        if output.find('[5009') > -1:
            logging.CyberCPLogFileWriter.writeToFile(output)
            writeToFile = open(schedulerPath, 'w')
            writeToFile.writelines(output)
            writeToFile.close()
            return 0

        ## Backing up databases

        backupMetaData = ElementTree.parse(result[2])

        databases = backupMetaData.findall('Databases/database')

        for database in databases:

            dbName = database.find('dbName').text

            if mysqlUtilities.mysqlUtilities.createDatabaseBackup(dbName, '/home/cyberpanel') == 0:
                writeToFile = open(schedulerPath, 'w')
                writeToFile.writelines('1358')
                writeToFile.close()
                return 0

            command = 'mv /home/cyberpanel/%s.sql %s/%s.sql' % (dbName, tempStoragePath, dbName)
            ProcessUtilities.executioner(command, 'root')

        ##

        output = ProcessUtilities.outputExecutioner(execPath, website.externalApp)

        if output.find('1,None') > -1:
            execPath = "sudo nice -n 10 /usr/local/CyberCP/bin/python " + virtualHostUtilities.cyberPanel + "/plogical/backupUtilities.py"
            execPath = execPath + " BackupRoot --tempStoragePath " + tempStoragePath + " --backupName " \
                       + backupName + " --backupPath " + backupPath + ' --backupDomain ' + backupDomain + ' --metaPath %s' % (
                           result[2])

            ProcessUtilities.executioner(execPath, 'root')
        else:
            logging.CyberCPLogFileWriter.writeToFile(output)

        command = 'chown -R %s:%s %s' % (website.externalApp, website.externalApp, backupPath)
        ProcessUtilities.executioner(command)

        command = 'rm -f %s' % (result[2])
        ProcessUtilities.executioner(command, 'cyberpanel')

    except BaseException as msg:
        logging.CyberCPLogFileWriter.writeToFile(
            str(msg) + "  [submitBackupCreation]")


def cancelBackupCreation(backupCancellationDomain, fileName):
    try:

        path = "/home/" + backupCancellationDomain + "/backup/pid"

        pid = open(path, "r").readlines()[0]

        try:
            os.kill(int(pid), signal.SIGKILL)
        except BaseException as msg:
            logging.CyberCPLogFileWriter.writeToFile(str(msg) + " [cancelBackupCreation]")

        backupPath = "/home/" + backupCancellationDomain + "/backup/"

        tempStoragePath = backupPath + fileName

        try:
            os.remove(tempStoragePath + ".tar.gz")
        except BaseException as msg:
            logging.CyberCPLogFileWriter.writeToFile(str(msg) + " [cancelBackupCreation]")

        try:
            rmtree(tempStoragePath)
        except BaseException as msg:
            logging.CyberCPLogFileWriter.writeToFile(str(msg) + " [cancelBackupCreation]")

        status = open(backupPath + 'status', "w")
        status.write("Aborted manually. [1165][5009]")
        status.close()
    except BaseException as msg:
        logging.CyberCPLogFileWriter.writeToFile(
            str(msg) + "  [cancelBackupCreation]")
        print("0," + str(msg))


def submitRestore(backupFile, dir):
    try:

        p = Process(target=backupUtilities.startRestore, args=(backupFile, dir,))
        p.start()

        print("1,None")

    except BaseException as msg:
        logging.CyberCPLogFileWriter.writeToFile(
            str(msg) + "  [cancelBackupCreation]")
        print("0," + str(msg))


def submitDestinationCreation(ipAddress, password, port='22', user='root'):
    setupKeys = backupUtilities.setupSSHKeys(ipAddress, password, port, user)

    if setupKeys[0] == 1:
        backupUtilities.createBackupDir(ipAddress, port, user)
        print("1,None")
    else:
        print(setupKeys[1])


def getConnectionStatus(ipAddress):
    try:
        checkCon = backupUtilities.checkConnection(ipAddress)

        if checkCon[0] == 1:
            print("1,None")
        else:
            print(checkCon[1])

    except BaseException as msg:
        print(str(msg))


def main():
    parser = argparse.ArgumentParser(description='CyberPanel Installer')
    parser.add_argument('function', help='Specific a function to call!')
    parser.add_argument('--tempStoragePath', help='')
    parser.add_argument('--backupName', help='!')
    parser.add_argument('--backupPath', help='')
    parser.add_argument('--backupDomain', help='')
    parser.add_argument('--metaPath', help='')

    ## Destination Creation

    parser.add_argument('--ipAddress', help='')
    parser.add_argument('--password', help='')
    parser.add_argument('--port', help='')
    parser.add_argument('--user', help='')

    ## backup cancellation arguments

    parser.add_argument('--backupCancellationDomain', help='')
    parser.add_argument('--fileName', help='')

    ## backup restore arguments

    parser.add_argument('--backupFile', help='')
    parser.add_argument('--dir', help='')

    args = parser.parse_args()

    if args.function == "submitBackupCreation":
        submitBackupCreation(args.tempStoragePath, args.backupName, args.backupPath, args.backupDomain)
    elif args.function == "cancelBackupCreation":
        cancelBackupCreation(args.backupCancellationDomain, args.fileName)
    elif args.function == "submitRestore":
        submitRestore(args.backupFile, args.dir)
    elif args.function == "submitDestinationCreation":
        submitDestinationCreation(args.ipAddress, args.password, args.port, args.user)
    elif args.function == "getConnectionStatus":
        getConnectionStatus(args.ipAddress)
    elif args.function == "startBackup":
        backupUtilities.startBackup(args.tempStoragePath, args.backupName, args.backupPath, args.metaPath)
    elif args.function == "BackupRoot":
        backupUtilities.BackupRoot(args.tempStoragePath, args.backupName, args.backupPath, args.metaPath)


if __name__ == "__main__":
    main()
