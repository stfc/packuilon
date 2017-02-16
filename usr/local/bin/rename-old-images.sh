#!/bin/bash
set -eu

imagename=$*
DATE=`date +%Y-%m-%d`

#list all the images that have the same name as the one just added
imagesid=$(glance image-list --sort created_at:desc | grep " $imagename " | cut -d '|' -f 2)
newimageid=$(echo "$imagesid" | head -n 1)
echo $newimageid

#for each image that is not the newest image with this name
members=''
for id in $(echo "$imagesid" | tail -n +2)
do
    echo $id
    #rename
    glance image-update --name "archive-$imagename $DATE" $id

    #get list of members from old image
    for member in $(glance member-list --image-id $id | grep $id | cut -d '|' -f 3);
    do
        #only add if not already in list
        if [[ ${members} != *"$member"* ]]
            then
            	members="$members $member"
        fi
        #remove members from old image
        glance member-delete $id $member
    done
done

newimagemembers=$(glance member-list --image-id $newimageid | grep $newimageid | cut -d '|' -f 3)

# add memberships to new image
for member in $members;
do
    #don't create member if it's already there
    if [[ ${newimagemembers} != *"$member"* ]]
    then
        glance member-create $newimageid $member
    fi
    glance member-update $newimageid $member accepted	
done
