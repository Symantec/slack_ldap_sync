#!/bin/bash
[ -z "$DOCKER_REGISTRY_URL" ] && echo "Need to set env DOCKER_REGISTRY_URL" && exit 1
[ -z "$OPENSHIFT_URL" ] && echo "Need to set env OPENSHIFT_URL" && exit 1
oc project slack-ldap-sync
if [[ $? -ne 0 ]] ; then
  echo "You need to login to openshift: "
  oc login `echo $OPENSHIFT_URL`
  oc project slack-ldap-sync
fi
echo "oc is set to project slack-ldap-sync"
docker build -t slack-ldap-sync .
if [[ $? -ne 0 ]] ; then
  echo "\n\nFailed to build the docker image.\n\n"
  exit 1
fi
echo "Successfully built the docker container"
if [[ -z "$DOCKER_REGISTRY_URL" ]]; then
  echo "DOCKER_REGISTRY_URL ENV variable is not set, so the build script did not tag the docker image. Though the docker image did build. Check docker images."
  exit 1
fi
docker tag slack-ldap-sync $DOCKER_REGISTRY_URL/slack_tools/slack_ldap_sync
if [[ $? -ne 0 ]] ; then
  echo "Failed to tag the docker image."
  exit 1
fi
echo "Tagged docker image."
docker push $DOCKER_REGISTRY_URL/slack_tools/slack_ldap_sync
if [[ $? -ne 0 ]] ; then
  echo "Failed to push the docker image to the registry."
  exit 1
fi
echo "Pushing docker image  ..."
sed -i.bak -e s/{DOCKER_REGISTRY_URL}/$DOCKER_REGISTRY_URL/g openshift_template.yml
echo "Deploying to openshift..."
oc process -f openshift_template.yml | oc apply -f -
if [[ $? -ne 0 ]] ; then
  echo "oc process -f openshift_template.yml | oc apply -f - HAS FAILED"
  exit 1
fi
oc deploy slack-ldap-sync --latest=true
if [[ $? -ne 0 ]] ; then
  echo "oc deploy slack-ldap-sync --latest=true HAS FAILED"
  exit 1
fi
sed -i.bak -e s/$DOCKER_REGISTRY_URL/'{DOCKER_REGISTRY_URL}'/g openshift_template.yml
rm openshift_template.yml.bak
echo ""
echo "Successfully deployed your docker image to openshift, `echo $OPENSHIFT_URL`/console/project/slack-ldap-sync/overview?main-tab=openshiftConsole%2Foverview"
