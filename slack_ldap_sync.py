#!/usr/bin/env python

import ldap
import logging
import os
import requests
import time

logger = logging.getLogger('slack_ldap_sync')

SLACK_TOKEN          = os.environ['SLACK_TOKEN']
SLACK_SCIM_TOKEN     = 'Bearer %s' % SLACK_TOKEN
SLACK_API_HOST       = 'https://api.slack.com'
SLACK_SUBDOMAIN      = os.environ['SLACK_SUBDOMAIN']  # eg. https://foobar.slack.com
HEADERS              = {'content-type': 'application/json', 'Authorization': SLACK_SCIM_TOKEN}
LDAP_HOST            = os.environ['LDAP_HOST']
LDAP_PEOPLE_OU       = os.environ['LDAP_PEOPLE_OU']
LDAP_PASS            = os.environ['LDAP_PASS']
LDAP_PORT            = '636'
LDAP_URI             = 'ldaps://%s:%s' % (LDAP_HOST, LDAP_PORT)
LDAP_USER            = os.environ['LDAP_USER']


def get_all_slack_users():
  url = '%s/scim/v1/Users?count=999999' % SLACK_API_HOST
  http_response = requests.get(url=url, headers=HEADERS)
  http_response.raise_for_status()
  results = http_response.json()
  return results['Resources']


def get_all_ldap_users():
  ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
  ldap_obj = ldap.initialize(LDAP_URI)
  ldap_obj.protocol_version = ldap.VERSION3
  ldap_obj.set_option(ldap.OPT_X_TLS,ldap.OPT_X_TLS_DEMAND)
  ldap_obj.set_option(ldap.OPT_X_TLS_DEMAND, True)
  ldap_obj.simple_bind_s(LDAP_USER, LDAP_PASS)
  ldap_users = ldap_obj.search_s(LDAP_PEOPLE_OU, ldap.SCOPE_SUBTREE)
  ldap_users_hashmap = {}
  for ldap_user in ldap_users[1:]:
    if not ldap_user[1].get('uid') or not ldap_user[1].get('mail'):
      continue
    ldap_users_hashmap[ldap_user[1]['mail'][0].lower()] = ldap_user[1]
  return ldap_users_hashmap


def get_guest_users():
  url = '%s/api/users.list' % SLACK_SUBDOMAIN
  http_response = requests.get(url=url, params={'token': SLACK_TOKEN})
  http_response.raise_for_status()
  users = http_response.json()['members']
  guest_users = {}
  for user in users:
    # restricted users are guests.
    if user.get('is_ultra_restricted') or user.get('is_restricted'):
      guest_users[user['id']] = user['profile']['email']
  return guest_users


def get_owner_users():
  url = '%s/api/users.list' % SLACK_SUBDOMAIN
  http_response = requests.get(url=url, params={'token': SLACK_TOKEN})
  http_response.raise_for_status()
  users = http_response.json()['members']
  owner_users = {}
  for user in users:
    if user.get('is_owner'):
      owner_users[user['id']] = user['profile']['email']
  return owner_users


def slack_message_owners(message, slack_email, slack_id, reason, owners):
  url = '%s/api/chat.postMessage' % SLACK_SUBDOMAIN
  message = '```%s```' % message
  for owner in owners.keys():
    payload = {
      'token'     : SLACK_TOKEN,
      'channel'   : owner,
      'text'      : message,
      'username'  : 'slack reaper',
      'icon_emoji': ':reaper:'
    }
    http_response = requests.get(url=url, params=payload)
    http_response.raise_for_status()
  return True


def disable_slack_user(slack_id, slack_email, reason, owners):
  url = '%s/scim/v1/Users/%s' % (SLACK_API_HOST, slack_id)
  http_response = requests.delete(url, headers=HEADERS)
  http_response.raise_for_status()
  log_msg = 'slack_id: %s  email: %s  This user has had their sessions expired and is disabled because %s' % (slack_id, slack_email, reason)
  logger.info(log_msg)
  slack_message_owners(message=log_msg, slack_email=slack_email, slack_id=slack_id, reason=reason, owners=owners)
  return True


def sync_slack_ldap():
  logger.info('Looking for slack users to delete that do not exist or are not active in LDAP')
  guest_users = get_guest_users()

  all_slack_owners = get_owner_users()

  all_slack_users = get_all_slack_users()

  all_ldap_users = get_all_ldap_users()

  for slack_user in all_slack_users:
    slack_user_email = slack_user['emails'][0]['value'].lower()

    # skip slack users that are already disabled ( active: False )
    if not slack_user['active']:
      continue
    # skip guest / bot accounts
    if guest_users.get(slack_user['id']) or '@slack-bots.com' in slack_user_email:
      continue
    # disable users who aren't in ldap
    if not all_ldap_users.get(slack_user_email):
      disable_slack_user(slack_id=slack_user['id'], slack_email=slack_user_email, reason='they do not exist in LDAP.', owners=all_slack_owners)
    # Since slack has infinite web/mobile session cookies, we will disable those sessions if the users ldap accounts is disabled
    if all_ldap_users[slack_user_email]['loginShell'][0] == '/bin/false':
      disable_slack_user(slack_id=slack_user['id'], slack_email=slack_user_email, reason='their LDAP account has been disabled.', owners=all_slack_owners)


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
  logging.getLogger('requests').setLevel(logging.ERROR)
  while True:
    try:
      sync_slack_ldap()
    except:
      logger.exception('Error syncing users.')
    logger.info('Sleeping for 60 minutes')
    time.sleep(3600)
