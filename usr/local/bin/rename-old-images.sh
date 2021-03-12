#!/usr/bin/python
import json
import sys
import os
import requests
from datetime import datetime
from subprocess import Popen, PIPE
from ConfigParser import SafeConfigParser
import time

env = os.environ.copy()

imagename = sys.argv[1]

oldimagename = imagename.replace("Next-","")

#time.sleep(300)

# Read from config file
parser = SafeConfigParser()
try:
    parser.read('/etc/packer-utils/config.ini')
    auth_file = parser.get('rabbit2packer','PACKER_ADMIN_AUTH_FILE')
    success_address = parser.get('global','SUCCESS_ADDRESS')
    failure_address = parser.get('global','FAILURE_ADDRESS')
    slackhook = parser.get('global', 'SLACK_SUCCESS_HOOK')
except:
    print 'Unable to read from config file'
    sys.exit(1)

sourcecmd = "source " + auth_file + ";"

def cl(c):
    p = Popen(sourcecmd+c, shell=True, stdout=PIPE, env=env)
    print(c)
    return p.communicate()[0]

def SendMail(Subject , Body, Recipient):
    body_str_encoded_to_byte = Body.encode()
    print("mail -s \"" + Subject + "\" "+ Recipient + " < " + body_str_encoded_to_byte)
    return_stat = cl("mail -s \"" + Subject + "\" " + Recipient + " < "+body_str_encoded_to_byte)
    print(return_stat)


DATE = datetime.now().strftime("%d-%m-%Y-%H-%M-%S")

print(DATE)

print(imagename)
print(oldimagename)

with open('/etc/packer-utils/templates/rally-test.json') as templatejson:
    testtemplate= json.load(templatejson)

testtemplate["VMTasks.boot_runcommand_delete"][0]["args"]["image"]["name"] = imagename

with open( "/etc/packer-utils/tests/" + imagename + ".json", "w") as testFile:
    json.dump(testtemplate, testFile)

mailfilepath="/tmp/"+imagename+"-"+DATE+".mail"
    

test = cl("rally deployment use openstack-prod ; rally task start /etc/packer-utils/tests/" + imagename + ".json | grep \"rally task report\" | grep \"json\" | sed 's/output.json/\/tmp\/" + imagename + "-" + DATE + "\.json/g'")
#test = cl("rally task start /etc/packer-utils/tests/" + imagename + ".json ")

print(test)
#print(test + " /tmp/"+imagename+"-"+DATE+".json")
#cl(test + " /tmp/"+imagename+"-"+DATE+".json")
cl(test)

with open("/tmp/"+imagename+"-"+DATE+".json") as testresultjson:
    testresult = json.load(testresultjson)

print(testresult["tasks"][0]["pass_sla"])

testPassed=testresult["tasks"][0]["pass_sla"]

if testPassed:
    imagedetails = json.loads(cl("openstack image show -f json " + imagename))

    allimages = json.loads(cl("openstack image list --long -f json"))

    private = True
    public = False
    shared = False

    members = []
    images = []
    for image in allimages:
        if oldimagename.lower() in image["Name"].lower():
            if oldimagename.lower() == image["Name"].lower():
                oldimagedetails = json.loads(cl("openstack image show -f json " + image["Name"]))
            images.append(image)
            if image["Visibility"] == "public":
                public = True
            if image["Visibility"] == "shared":
                print(image)
                print(image["ID"])
                members.extend(json.loads(cl("openstack image member list -f json " + image["ID"])))
                shared = True
        
    visibility = " --private "
    if public:
        visibility = " --public "
    elif shared:
        visibility = " --shared "

    print(visibility)
    metadatastring = ""
    try:
        for metadata in oldimagedetails["properties"]:
            if "AQ" in metadata or "os_distro" in metadata or "os_version" in metadata or "os_variant" in metadata:
                metadatastring = metadatastring + " --property " + metadata + "=" + oldimagedetails["properties"][metadata]
    except:
        print("Previous version not found")
    

    for member in members:
        print("glance member-create " + imagedetails["id"] + " " + member["Member ID"])
        cl("glance member-create " + imagedetails["id"] + " " + member["Member ID"])
        print("glance member-update " + imagedetails["id"] + " " + member["Member ID"] + " accepted")
        cl("glance member-update " + imagedetails["id"] + " " + member["Member ID"] + " accepted")

    cl("openstack image set " + oldimagename + " --deactivate --name 'warehoused-" + oldimagename + "-" + DATE + "'")
    print("openstack image set " + oldimagename + " --deactivate --name 'warehoused-" + oldimagename + "-" + DATE + "'")

    cl("openstack image set " + visibility + imagename + " --name '" + oldimagename + "' " + metadatastring)
    print("openstack image set " + visibility + imagename + " --name '" + oldimagename + "' " + metadatastring)

    

#print(images)

#print(members)
    
    for image in allimages:
        if oldimagename.lower() in image["Name"].lower():
            print("sed -i 's/" + image["ID"] + "/" + imagedetails["id"] + "/g' /etc/packer-utils/build/*.json")
            cl("sed -i 's/" + image["ID"] + "/" + imagedetails["id"] + "/g' /etc/packer-utils/build/*.json")
            print("sed -i 's/" + image["ID"] + "/" + imagedetails["id"] + "/g' /etc/packer-utils/source-images.json")
            cl("sed -i 's/" + image["ID"] + "/" + imagedetails["id"] + "/g' /etc/packer-utils/source-images.json")

    with open(mailfilepath, "w") as mailfile:
        mailfile.write("Build of " + imagename + " succeeded on " + DATE "+. New image ID is `" + imagedetails["id"] + "`")  
    SendMail(oldimagename+ " - Build Succeeded", mailfilepath, success_address)
    
    slackheaders = {'Content-Type': 'application/json'}
    slackdata = {'text': "Build of " + imagename + " succeeded on " + DATE "+. New image ID is `" + imagedetails["id"] + "`"}
    slackdebug=requests.post(slackhook, headers=slackheaders, data=json.dumps(slackdata))
    print(slackdebug)
    

else:
    with open(mailfilepath, "w") as mailfile:
        mailfile.write("Build of " + imagename + " failed on " + DATE + " due to rally test failing")
    SendMail("Build Failed", mailfilepath, failure_address)
    visibility = " --private "
    print("openstack image set " + visibility + imagename + " --name 'Broken-" + oldimagename + DATE + "'")
    cl("openstack image set " + visibility + imagename + " --name 'Broken-" + oldimagename + DATE + "'")
    
