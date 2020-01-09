# Packuilon

A collection of scripts to allow OpenStack VM images to be automatically built based on personalities from Aquilon. It communicates with Quattor/Aquilon (https://www.quattor.org/) to know when to initiate the process, and uses Packer (https://www.packer.io) to do the image building. The use case for this is having a more automated method of updating existing images and adding new ones.

# cdb2rabbit

Checks for changes to the continuous integration profiles (or profiles defined by a "PROFILE_MATCH" string, which can be left blank to check all profiles). It does this by comparing the cached profile (found in `/etc/packer-utils/profiles`) with the profile downloaded during execution of the script. A message is pushed to a RabbitMQ queue if a change is found. Can be called by cron, or by Quattor (using ncm-cdispd). The message is just the profile object (json encoded) which is obtained from Aquilon.

# rabbit2packer

Listens to the same RabbitMQ queue used in `cdb2rabbit.py`. When a message is received, it creates a Packer build file (found in `/etc/packer-utils/build`) and starts the Packer process.

The build file is created from a template which contains the source image, network etc. It should contain the strings $NAME, $IMAGE and $METADATA which will be replaced by the name of the image, the source image ID (grabbed from `/etc/packer-utils/source-images.json`) and the instance metadata (currently AQ\_PERSONALITY, AQ\_OS, AQ\_OSVERSION, AQ\_DOMAIN, AQ\_ARCHETYPE).

## Template Map
The template file to be used is defined in the `PACKER_TEMPLATE_MAP` config variable (`/etc/packer-utils/template-map.json` by default) which is set out as follows:

```json
{
    "DEFAULT":
        [
                "/etc/packer-utils/templates/unmanaged.json",
                "/etc/packer-utils/templates/managed.json"
        ],
    "test-sl7x-x86_64": [ "/etc/packer-utils/templates/managed.json" ]
}
```

If the image has an entry (such as test-sl7x above) then that template will be used, otherwise the `DEFAULT` entry will be used. The key can be anything you like, but generally follows the pattern of `personality-os+os_version-architecture`. Multiple templates can be defined (as per `DEFAULT`) and they will all be built (currently one after another). Defining an entry prevents the default template(s) being built for that host.

## Source Images

The source image for each operating system type is defined in a separate config file (`/etc/packer-utils/source-images.json` by default). The file contains key-value pair structure, with the key being the `os+os_version-architecture` string, and the value being the image ID to use. For example:

```json
{
    "sl6x-x86_64" : "7eb100a3-680b-4544-99cc-950b8c4f6c74",
    "sl7x-x86_64" : "0b10e583-9e13-4878-9116-f4002846fa73",
    "osos_version-archetype" : "this-is-not-valid"
}
```

If there is no matching key for the image the build will be skipped. Otherwise, Packer will be started with the created build file.

## Packer Build

To begin the Packer process, a `packer.io build` is executed inside `rabbit2packer.py`, passing the build file and ensuring OpenStack commands can be executed (by using the `PACKER_AUTH_FILE` to give relevant permissions). See `run_packer_subprocess()` for this.

The instance metadata will be interpreted by a script running on our OpenStack 'stack' which will change the build hostname's personality in Aquilon to the one found in the message (https://github.com/stfc/SCD-OpenStack-Utils/tree/master/OpenStack-Rabbit-Consumer).

The Packer shell provisioned (default is using file provisioner to upload a script then a shell provisioner to execute it) then runs a Quattor fetch+configure with the new profile via the `update_ccm_conf.sh` script, which is executed on the instance spun up by Packer, and assuming that doesn't error, a Glance image will be created called $personality-$os.

By a Quattor fetch+configure, the following commands are meant. These may or may not require sudo to run:

```bash
quattor-fetch
quattor-configure --all
```

## rename-old-images

 If the Packer shell process exits without error, a separate shell script (`/usr/local/bin/rename-old-images.sh`) is called. This renames the previous image to 'warehoused-$image-name $date' and transfers the memberships from the old image to the new image. Membership transfer can only be performed if the image is a shared image (for SCD, most AQ images are shared, for example). There are a mix of OpenStack and Glance commands within the script. Glance commands have been replaced where possible with OpenStack as this allows the script to make use of the `-f` option, to format outputs into various format (json being useful as the output can be piped into jq).

 To check what whether an image is a shared image or not, use the following command and see the value of the visibility column:

 ```bash
openstack image show $image_uuid
 ```

The Packer build process is logged in separate log for each build, found in the `LOG_DIR`. Logs are stored for each build process - this is done by using Unix timestamps. If multiple builds are started sequentially (e.g. through a script), and they've started in the same second (therefore the Unix timestamp is the same), this can make logs confusing because multiple builds will be contained in one log file. If starting builds through a script, leave a second or two gap between the start of each process.

## Rally Integration

A new feature added to Packuilon is to make use of OpenStack Rally to test the images that Packer produces. As of writing, this all works and the test executed is a simple boot up and delete of a couple of VMs using the image just produced. With a little more time, a more complex test should be written, making use of a Rally plugin called `VMTasks.boot_runcommand_delete`. This allows Rally to inject a script into the VM in question. This would be useful as this script could contain tests which are currently done manually, but can quite easily be automated. For anyone looking to do this, plans of Bash commands to test images have been given to Alex. 

All this Rally work is contained in `etc/packer-utils/image-testing-rally`. There's a mixture of Python files and Bash scripts. The Bash scripts are used to start a Rally task and get the results (put into a json file) from the task. This json is put into Python and is used to make decisions regarding the quality of the image. The final yes/no decision of the image is logged using syslog. `rally_task_analysis.py` kicks off the Bash scripts using Subprocess.

# Installation

*this is mostly SCD specific*

The `image_factory` personality installs Packer, Packuilon, the SCD specific config and adds the ncm-cdispd hocks for cdb2rabbit. The host will need to be bound to an instance of the image-factory service to receive packets about profile rebuilds:

```bash
aq bind_server --service image-factory --instance scd-cloud-image-factory --hostname $hostname
```

The things you will need to source manually are the OpenStack credential files defined in the rabbit2packer section of the config. The `PACKER_AUTH_FILE` only needs to be able to create machines and images in its own project (which keeps things nicely partitioned). A separate admin auth file (likely to be stored at `/etc/packer-utils/admin-auth.sh`) is sourced in the post-processor section of the templates to update the memberships and rename the old images. Both of these files can be found in OpenStack, typically in Horizon in the API Access section of the site (one user to have admin authorities, the other doesn't require it).

Once that's done, restarting rabbit2packer with `systemctl restart rabbit2packer.service` should get you a working instance. Both cdb2rabbit and rabbit2packer log to syslog to it's usually fairly easy to se what's going wrong by keeping an eye on `/var/log/messages`, and you can just run both scripts from the command line if things are horribly broken.

How do you actually 'run' Packuilon? Every time a UDP packet is received from `cdp-listend`, `cdb2rabbit` should run and if there's a profile match (see the config for the match string), `rabbit2packer` will be run. A UDP packet is sent everytime a host is made in Aquilon (i.e. `aq make`). Try making some hosts in Aquilon with `/var/log/messages` open on the host with Packuilon installed and you should see this workflow being logged, something like:

```
16:30:45 host /usr/sbin/cdp-listend[3580]: Received UDP packet (cdb|1486571445) from xx.xx.xx.xx
16:30:45 host /usr/sbin/cdp-listend[3580]: /usr/local/bin/cdb2rabbit.py will be called in 0 seconds
16:30:45 host /usr/sbin/cdp-listend[3580]: Calling /usr/local/bin/cdb2rabbit.py with unix time 1486571445 (after 0 seconds)
16:30:45 host /cdb2rabbit.py: Starting
16:30:45 host /cdb2rabbit.py: CI profile rebuilt: image-factory-sl-7x-x86-64.ral-tier1.testing.internal.json
16:30:45 host /cdb2rabbit.py: Downloading profile image-factory-sl-7x-x86-64.ral-tier1.testing.internal.json
16:30:45 host /cdb2rabbit.py: Profile has updated: image-factory-sl-7x-x86-64.ral-tier1.testing.internal.json
16:30:45 host /cdb2rabbit.py: Pushing message to queue for build
16:30:45 host /cdb2rabbit.py: Updating cached profile_info
16:30:45 host /cdb2rabbit.py: Exiting normally
16:30:45 host /rabbit2packer.py: Thread-2 processing image-factory-sl7x-x86_64
16:30:45 host /rabbit2packer.py: packer build starting, see: /etc/packer-utils/log/image-factory-sl7x-x86_64.log for details
[...]
16:34:36 host /rabbit2packer.py: Thread-2: image built successfully
16:34:38 host /rabbit2packer.py: Thread-2: reconnecting to channel
```

# Getting Started with Packuilon

The above steps get the scripts within Packuilon installed but further configuration will be needed to get it working for specific images. First of all, look in `config.ini` and insert the details to a RabbitMQ host (hostname, port, username and password are needed here). Under the cdb2rabbit section, ensure the `PROFILE_INFO_URL` is correct. Everything in the rabbit2packer section should be good to start with.

To configure a new type of image requires some configuration too (found it `/etc/packer-utils`). As an example, let's take a Centos 7 image using the `nubesvms` personality (for SCD users, this is an AQ managed personality). As mentioned above for `source-images.json`, insert the key (`centos7x-x86_64` for example), and insert the corresponding value of a Centos 7 image UUID from OpenStack.

Next is `template-map.json`. Appending the file using a line in the format as below will suffice. One template file could be used for each image and personality combination or just one file per personality:

```json
"nubesvms-centos7x-x86_64": ["/etc/packer-utils/templates/nubesvms-centos7.json"]
```

From the value used in `template-map.json`, create a file of the same name in the relevant directory. This file should be a version of (un)managed.json, whichever is relevant (i.e. is the personality for a managed or an unmanaged image?). This file is essentially a Packer build file with some blanks, that are filled in during rabbit2packer. At this point, it's a good idea to restart the `rabbit2packer` systemctl service, just to make sure all updates to these files are seen. Any errors should appear in the logs so it's probably best to run Packuilon and see what comes from the logs and fix accordingly. The most probable things to be wrong are incorrect paths to files and UUIDs for OpenStack (networks and images). You can see the actual Packer build files (the ones without the blanks) in `/etc/packer-utils/build` once a build has been completed.
