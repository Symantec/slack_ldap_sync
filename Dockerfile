FROM python:2-alpine
RUN apk update && apk add g++ libsasl libssl1.0 libldap openldap-dev && pip install python-ldap requests && apk del g++ openldap-dev libsasl libssl1.0 && rm -rf /var/cache/apk/*
ADD . /src
CMD ["/src/slack_ldap_sync.py"]

