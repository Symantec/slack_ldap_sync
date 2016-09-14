#Deactivate and expire sessions of users not active in your LDAP instance

##How to use

- docker build -t slack_ldap_sync .
- docker run -it -e SLACK_TOKEN='xoxp-123456' \
-e SLACK_SUBDOMAIN='https://example.slack.com' \
-e LDAP_USER='uid=slack_ldap_sync,ou=Services,dc=example,dc=com' \
-e LDAP_PASS='' \
-e LDAP_HOST='ldap.example.com' \
-e LDAP_PEOPLE_OU='ou=People,dc=example,dc=com' slack_ldap_sync 
