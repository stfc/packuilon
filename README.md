# Packuilon

A collection of scripts to allow OpenStack VM images to be automatically built based on personalities from Aquilon (http://www.quattor.org). It uses Packer (https://www.packer.io) to do the image building. 

I had to add some functionality to Packer to get this to work, if this PR is merged you can use mainline packer, otherwise you'll have to build it yourself from my branch: https://github.com/mitchellh/packer/pull/4361

# cdb2rabbit

Checks for changes to the continuous integration profiles (or profiles defined by a "name contains string" check), and pushes a message to a RabbitMQ queue. Can be called by cron, or by quattor (using ncm-cdispd). The message is just the profile object (json encoded).

#rabbit2packer

Listens to the RabbitMQ queue. When one is recieved it creates a packer build file and starts the packer process.

The build file is created from a template which contains the source image, network etc. It should contain the strings $NAME, $IMAGE and $METADATA which will be replaced by the name of the image, the source image and the instance metadata (currently just the AQ\_PERSONALITY).

The source image for each operating system type is defined in a separate config file defined in the main config.ini (`/etc/packer-utils/source-images.json` by default). The file contains key value pair, with the key being the OS (as defined by aquilon in system->aii->nbp->pxelinux->kernel) and the value being the image ID to use. For example:

```
{
    "sl7x-x86_64": "6a8e0908-0d8e-4f26-88bf-4c045421c30d",
    "ubuntu-14.04-ppc": "58739777-e429-856c-7d51-539a8610df0b"
}
```

If there is no matching key for the image the build will be skipped. Otherwise Packer will be started with the created build file.

The instance metadata will be intepreted by a script running on our openstack 'stack' which will change the build hostname's personality to the one found in the message (https://github.com/stfc/SCD-OpenStack-Utils/tree/master/OpenStack-Rabbit-Consumer)

The packer shell provisioner then runs a fetch+configure with the new profile, and assuming that doesn't error, a glance image will be created called $personality-$os
