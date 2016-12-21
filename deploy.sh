#!/bin/bash
[ -z "$OPENSHIFT_URL" ] && echo "Need to set env OPENSHIFT_URL" && exit 1
oc project slack-ldap-sync 
echo "Building docker image ..."
docker build -t slack-ldap-sync .
docker tag `docker images|grep slack-ldap-sync|tail -1|awk '{print $3}'` $OPENSHIFT_URL/slack_tools/slack_ldap_sync
echo "Tagging docker image  ..."
docker push $OPENSHIFT_URL/slack_tools/slack_ldap_sync
echo "Pushing docker image  ..."
sed -i.bak -e s/{OPENSHIFT_URL}/$OPENSHIFT_URL/g openshift_template.yml
echo "Deploying to openshift..."
oc process -f openshift_template.yml | oc apply -f -
oc deploy slack-ldap-sync --latest=true
sed -i.bak -e s/$OPENSHIFT_URL/'{OPENSHIFT_URL}'/g openshift_template.yml
rm openshift_template.yml.bak
