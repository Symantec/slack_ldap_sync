#!/bin/bash
app_name=slack-ldap-sync
oc_secret_name=slack-ldap-secrets
oc_secret_file=./source
docker_registry_directory=slack_tools
docker_build_logfile=docker-build.log
openshift_template_file=./openshift_template.yml
# need to set OPENSHIFT_URL and DOCKER_REGISTRY_URL variables for this script.

function bash_validate_variables() {
  [ -z "$DOCKER_REGISTRY_URL" ] && log_stdout "Need to set env DOCKER_REGISTRY_URL" && exit 1
  [ -z "$OPENSHIFT_URL" ] && log_stdout "Need to set env OPENSHIFT_URL" && exit 1
}

function log_stdout() {
  echo "##########"
  echo "$(date) $1"
  echo "##########"
  echo " "
}

function oc_login() {
  login_msg="Logging in to $OPENSHIFT_URL"
  if ! oc whoami &> /dev/null; then
    log_stdout "$login_msg"
    oc login "$OPENSHIFT_URL"
  else
    current_openshift_server=$(oc version|grep Server|awk '{print $2}')
    if [ "$current_openshift_server" != "$OPENSHIFT_URL" ]; then
      log_stdout "Logging out of $current_openshift_server"
      oc logout
      log_stdout "$login_msg"
      oc login "$OPENSHIFT_URL"
    fi
  fi
}

function oc_switch_project() {
  if ! only_print_stdout_on_fail oc get project $app_name; then
    log_stdout "oc creating new project $app_name"
    oc new-project $app_name &> /dev/null
    log_stdout "oc project $app_name created"
  else
    log_stdout "oc $app_name set as the active project"
  fi
}

function oc_sync_secrets() {
  sync_msg="$oc_secret_name remote secret is synced with the local copy"
  if [ ! -f $oc_secret_file ]; then
    log_stdout "Missing required file $oc_secret_file, exiting"
    exit 1
  fi
    # if the secrets store doesn't exist, create it.
  if ! only_print_stdout_on_fail oc get secrets $oc_secret_name; then
    oc create secret generic $oc_secret_name --from-file=$oc_secret_file
  fi
  # check if the secret has changed locally, if so update it.
  server_secret_md5=$(oc export secrets $oc_secret_name|grep aws-secrets.yml|awk '{print $2}'|base64 --decode|md5)
  local_secret_md5=$(md5 < $oc_secret_file)
  if [ "$server_secret_md5" != "$local_secret_md5" ]; then
    oc delete secret $oc_secret_name &> /dev/null
    oc create secret generic $oc_secret_name --from-file=$oc_secret_file &> /dev/null
    log_stdout $sync_msg
  else
    log_stdout $sync_msg
  fi
}

function docker_tag_image() {
  if ! docker tag "$app_name" "$DOCKER_REGISTRY_URL"/"$docker_registry_directory"/"$app_name"; then
    log_stdout "Failed to tag the docker image $DOCKER_REGISTRY_URL/$docker_registry_directory/$app_name"
    exit 1
  else
    log_stdout "Tagged docker image $DOCKER_REGISTRY_URL/$docker_registry_directory/$app_name"
  fi
}

function docker_build_image() {
  docker_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
  if ! docker build -t "$app_name":latest "$docker_dir"/ &> "$docker_build_logfile"; then
    log_stdout "Failed to build the docker image. Check the log file $docker_build_logfile"
    exit 1
  else
    log_stdout "Successfully built the docker container $app_name (see docker images)"
  fi
}

function docker_push_image() {
  if ! only_print_stdout_on_fail docker push "$DOCKER_REGISTRY_URL/$docker_registry_directory/$app_name"; then
    log_stdout "Failed to push the docker image to the registry"
    exit 1
  else
    log_stdout "Successfully pushed docker image $DOCKER_REGISTRY_URL/$docker_registry_directory/$app_name"
  fi
}

# This is a helper function that lets me call commands, but only dump stdout if the command fails
function only_print_stdout_on_fail() {
  local t e; t=$("$@" 2>&1) || { e=$?; [[ $t ]] && printf '%s\n' "$t"; return "$e"; };
}

function oc_deploy() {
  sed -i.bak -e s/'{DOCKER_REGISTRY_URL}'/"$DOCKER_REGISTRY_URL"/g $openshift_template_file
  if ! oc process -f $openshift_template_file | oc apply -f -; then
    log_stdout "Failed to oc process $openshift_template_file"
    exit 1
  fi
  if oc deploy $app_name --latest=true; then
    log_stdout "Successfully deployed your docker image to openshift, $OPENSHIFT_URL/console/project/$app_name/overview?main-tab=openshiftConsole%2Foverview"
  fi
  sed -i.bak -e s/"$DOCKER_REGISTRY_URL"/'{DOCKER_REGISTRY_URL}'/g $openshift_template_file
  rm $openshift_template_file.bak
}

bash_validate_variables
log_stdout "Starting deployment of $app_name to $OPENSHIFT_URL"
oc_login
oc_switch_project
oc_sync_secrets
docker_build_image
docker_tag_image
docker_push_image
oc_deploy