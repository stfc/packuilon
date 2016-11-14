# packquilon

A collection of scripts to allow OpenStack VM images to be automatically built based on personalities from Aquilon (http://www.quattor.org). It uses Packer (https://www.packer.io) to do the image building.

# cdb2rabbit

Checks for changes to the continuous integration profiles (or profiles defined by a "name contains string" check), and pushes a message to a RabbitMQ queue. Can be called by cron, or by quattor (using ncm-cdispd).
