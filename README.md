# packquilon

A collection of scripts to allow OpenStack VM images to be automatically built based on personalities from Aquilon (http://www.quattor.org). It uses Packer (https://www.packer.io) to do the image building.

# cdb2rabbit

Checks for changes to the continuous integration profiles (or profiles defined by a "name contains string" check), and pushes a message to a RabbitMQ queue. Can be called by cron, or by quattor (using ncm-cdispd). The message is just the new profile.

#rabbit2packer

Listens to the RabbitMQ queue. When one is recieved it creates a packer build file and starts the packer process.

The build file is created from a template which contains the source image, network etc. It should contain the strings $NAME and $METADATA which will be replaced by the name of the image and the instance metadata (currently just the AQ\_PERSONALITY).

The instance metadata will be intepreted by a script running on our openstack 'stack' which will change the build instances personality to the required. (https://github.com/stfc/SCD-OpenStack-Utils/tree/master/OpenStack-Rabbit-Consumer)

The packer shell provisioner then runs a fetch+configure with the new profile.
