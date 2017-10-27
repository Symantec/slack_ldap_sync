# Deactivate and expire sessions of users not active in your LDAP instance

## How to use with just docker.

```
docker build -t slack_ldap_sync .
docker run -it -e SLACK_MAX_DELETE_FAILSAFE="0.2" \
-e SLACK_TOKEN="xoxp-exampletokenfoobarbazqux" \
-e SLACK_SUBDOMAIN="https://team.slack.com" \
-e SLACK_SYNC_RUN_INTERVAL="1800" \
-e AD_URL="ldaps://ldap.example.com:636" \
-e AD_BASEDN="ou=people,DC=example,DC=com" \
-e AD_SEARCH_FILTER_FOR_ACTIVE_EMPLOYEES_ONLY='(&(uid=*)(employee_status=active))' \
-e AD_BINDDN="foo\user_name" \
-e AD_BINDPW="password" \
-e AD_SEARCHREQ_ATTRLIST='["mail", "active_employee_attribute=True"]' \
-e AD_EMAIL_ATTRIBUTE="mail" slack_ldap_sync /src/slack_ldap_sync.py
```


## How to use with docker/openshift

- edit the `source.example` file and set the variables how you want

- then run:

```
oc new-project slack-ldap-sync
oc create secret generic slack-ldap-secrets --from-file=source.example
```

- run `./deploy.sh` to deploy to openshift
