FROM python:2-alpine
RUN apk update && apk add ca-certificates g++ libsasl libssl1.0 libldap openldap-dev && update-ca-certificates && echo "TLS_CACERTDIR /etc/ssl/certs" >> /etc/openldap/ldap.conf && pip install python-ldap requests && apk del g++ openldap-dev libsasl libssl1.0 && rm -rf /var/cache/apk/*
ADD . /src
CMD ["/src/slack_ldap_sync.py"]

