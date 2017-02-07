#!/bin/sh
#set -x
ip=$(hostname -I)
echo "Starting ccm update script, waiting for network"
until nslookup $ip
do
    echo "Networking not ready, sleeping"
    sleep 5
done

host=$(nslookup $ip | grep -v '^$'| tail -n 1 | rev | cut -d' ' -f1 | rev | sed "s/.ac.uk./.ac.uk/g")
template="retrieve_retries 3
profile http://aquilon.gridpp.rl.ac.uk/profiles/$host.json
get_timeout 30
world_readable 0
force 0
cache_root /var/lib/ccm
retrieve_wait 30
lock_retries 3
lock_wait 30
debug 0"


echo "$template" > /etc/ccm.conf
echo "Got hostname $host"

echo "Fetching profile"
until quattor fetch 
do
    echo "sleeping till quattor-fetch can lock"
    sleep 10
done

echo "Running quattor configure"
quattor configure --all
