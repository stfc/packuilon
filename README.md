# Packuilon

A collection of scripts to allow OpenStack VM images to be automatically built based on personalities from Aquilon. It uses Packer (https://www.packer.io) to do the image building. 

# cdb2rabbit

Checks for changes to the continuous integration profiles (or profiles defined by a "PROFILE_MATCH" string, which can be left blank for all profiles), and pushes a message to a RabbitMQ queue. Can be called by cron, or by quattor (using ncm-cdispd). The message is just the profile object (json encoded).

# rabbit2packer

Listens to the RabbitMQ queue. When one is received it creates a packer build file and starts the packer process.

The build file is created from a template which contains the source image, network etc. It should contain the strings $NAME, $IMAGE and $METADATA which will be replaced by the name of the image, the source image and the instance metadata (currently just the AQ\_PERSONALITY, AQ\_OS and AQ\_OSVERSION).

The template file to be used is defined in `PACKER_TEMPLATE_MAP` (`/etc/packer-utils/template-map.json` by default) which is set out as follows:


```
{
    "DEFAULT":
        [
                "/etc/packer-utils/templates/unmanaged.json",
                "/etc/packer-utils/templates/managed.json"
        ],
    "test-sl7x-x86_64": [ "/etc/packer-utils/templates/managed.json" ]
}
```

If the image has an entry (such as test-sl7x above) then that template will be used, otherwise the `DEFAULT` entry will be used. Multiple templates can be defined and they will all be built (currently one after another). Defining an entry prevents the default template(s) being built for that host.


The source image for each operating system type is defined in a separate config file defined in the main config.ini (`/etc/packer-utils/source-images.json` by default). The file contains key value pair structure, with the key being the `os+os_version-arch` string, and the value being the image ID to use. For example:

```
{
    "sl6x-x86_64" : "7eb100a3-680b-4544-99cc-950b8c4f6c74",
    "sl7x-x86_64" : "0b10e583-9e13-4878-9116-f4002846fa73",
    "osos_version-archetype" : "this-is-not-valid"
}
```

If there is no matching key for the image the build will be skipped. Otherwise Packer will be started with the created build file.

The instance metadata will be interpreted by a script running on our openstack 'stack' which will change the build hostname's personality to the one found in the message (https://github.com/stfc/SCD-OpenStack-Utils/tree/master/OpenStack-Rabbit-Consumer).

The packer shell provisioned then runs a fetch+configure with the new profile via the `update_ccm_conf.sh` script, which is executed on the instance, and assuming that doesn't error, a glance image will be created called $personality-$os. If the packer shell process exits without error a separate shell script (rename-old-images.sh) is called which renames the previous image to 'archive $image-name $date' and transfers the memberships from the old image to the new image.

This process is logged in separate log for each build, found in the `LOG_DIR`. Bear in mind that these are overwritten when a new build of that image starts, so there are no historical build logs kept. This is a area for improvement if anyone is bored.

# Installation

*this is mostly SCD specific*

The `image_factory` personality installs packer, packuilon, the SCD specific config and adds the ncm-cdispd hocks for cdb2rabbit. The host will need to be bound to an instance of the image-factory service to receive packets about profile rebuilds:

```
aq bind_server --service image-factory --instance scd-cloud-image-factory --hostname $hostname
```

The things you will need to source manually are the openstack credential files defined in the rabbit2packer section of the config. The `PACKER_AUTH_FILE` only needs to be able to create machines and images in its own project (which keeps things nicely partitioned). A separate admin auth file is sourced in the post-processor section of the templates to update the memberships and rename the old images.

Currently you also need to sort the certbundle out so packer can talk to openstack. Manually copying over `/etc/ssl/certs/ca-bundle.crt` from a openstack machine does the trick.

Once that's done, restarting rabbit2packer with `systemctl restart rabbit2packer.service` should get you a working instance. Both cdb2rabbit and rabbit2packer log to syslog to it's usually fairly easy to se what's going wrong by keeping an eye on `messages`, and you can just run both scripts from the command line if things are horribly broken.

A normal run should look something like:

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
