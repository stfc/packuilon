#!/bin/bash
set -eu

imagename=$*
DATE=`date +%Y-%m-%d`

# List all the images that have the same name as the one just added
echo $imagename
imagesid=$(openstack image list --sort created_at:desc -f value | grep " $imagename " | awk '{print $1}')
echo $imagesid

if [ -z "$imagesid" ]
then
    echo "Image name doesn't exist in the project, no work to do for rename-old-images.sh to do"
else
    echo "Image name already exists, renaming:"
    newimageid=$(echo "$imagesid" | head -n 1)
    echo $newimageid

    # For each image that is not the newest image with this name
    members=''
    for id in $(echo "$imagesid" | tail -n +2)
    do
        echo $id
        # Rename image to be at bottom of the list
        openstack image set $id --name "warehoused-$imagename $DATE"

        # Ensure visibility of image is 'shared' before attempting to manipulate members
        imagevisibility=$(openstack image show "$id" -f json | jq -r .visibility)
        echo $id

        if [ "$imagevisibility" == "shared" ]
        then
            # Get list of members from old image
            for member in $(glance member-list --image-id $id | grep $id | cut -d '|' -f 3);
            do
                # Only add if not already in list
                if [[ ${members} != *"$member"* ]]
                then
                    members="$members $member"
                fi
                # Remove members from old image
                glance member-delete $id $member
            done
        fi
    done
    
    newimagemembers=$(glance member-list --image-id $newimageid | grep $newimageid | cut -d '|' -f 3)

    # Add memberships to new image
    for member in $members;
    do
        # Don't create member if it's already there
        if [[ ${newimagemembers} != *"$member"* ]]
        then
            glance member-create $newimageid $member
        fi
        glance member-update $newimageid $member accepted
    done
fi

