#!/usr/bin/env python

import json
import logging
import ldap
import os
import requests
import time
from ldap.controls.libldap import SimplePagedResultsControl

logger = logging.getLogger('slack_ldap_sync')

# configurable as a float from 0 to 1
# will raise exception if you try to delete more slack users than 20% of the total slack users.
# This is in case ldap returns an empty list, or a truncated list.
# We don't want LDAP issues to cause everyone in slack to be deleted.
max_delete_failsafe = float(os.environ.get('SLACK_MAX_DELETE_FAILSAFE', 0.2))
slack_token         = os.environ.get('SLACK_TOKEN')
slack_scim_token    = 'Bearer %s' % slack_token
slack_api_host      = 'https://api.slack.com'
slack_subdomain     = os.environ.get('SLACK_SUBDOMAIN')  # eg. https://foobar.slack.com
slack_http_header   = {'content-type': 'application/json', 'Authorization': slack_scim_token}
slack_icon_emoji    = os.environ.get('SLACK_ICON_EMOJI', ':scream_cat:')
# 'ldaps://ad.example.com:636', make sure you always use ldaps
ad_url              = os.environ.get('AD_URL')
ad_basedn           = os.environ.get('AD_BASEDN')
ad_binddn           = os.environ.get('AD_BINDDN')
ad_bindpw           = os.environ.get('AD_BINDPW')
ad_email_attribute  = os.environ.get('AD_EMAIL_ATTRIBUTE', 'mail')
# note: make sure you only search the directory for active employees. This step is critical to the sync process.
search_flt          = os.environ.get('AD_SEARCH_FILTER_FOR_ACTIVE_EMPLOYEES_ONLY')
page_size           = 5000
trace_level         = 0
# '["uid", "active_employee_attribute"]'
searchreq_attrlist  = json.loads(os.environ.get('AD_SEARCHREQ_ATTRLIST'))
sync_run_interval   = float(os.environ.get('SLACK_SYNC_RUN_INTERVAL', '3600'))


def get_all_slack_scim_users(count=500):

  def get_page_of_scim_users(start_index, page_size):
    url = '%s/scim/v1/Users?count=%s&startIndex=%s' % (slack_api_host, page_size, start_index)
    http_response = requests.get(url=url, headers=slack_http_header)
    http_response.raise_for_status()
    return http_response.json()
  current_index = 1
  all_slack_users_qty = 2  # just to bootstrap the while loop.
  all_slack_users = []
  # use pagination, since we're about to get over 1k users. This should be supported anyway.
  while current_index < all_slack_users_qty:
    new_page_results = get_page_of_scim_users(start_index=current_index, page_size=count)
    # on the first page get, set the total number of slack users from scim
    if all_slack_users_qty == 2:
      all_slack_users_qty = new_page_results['totalResults']
    all_slack_users += new_page_results['Resources']
    current_index += count
  return all_slack_users


def get_all_active_ad_users():
  l = ldap.initialize(ad_url, trace_level=trace_level)
  l.set_option(ldap.OPT_REFERRALS, 0)
  l.set_option(ldap.OPT_X_TLS_DEMAND, True)
  l.protocol_version = 3
  l.simple_bind_s(ad_binddn, ad_bindpw)

  req_ctrl              = SimplePagedResultsControl(True,size=page_size,cookie='')
  known_ldap_resp_ctrls = {SimplePagedResultsControl.controlType:SimplePagedResultsControl}
  attrlist              = [s.encode('utf-8') for s in searchreq_attrlist]
  msgid                 = l.search_ext(ad_basedn, ldap.SCOPE_SUBTREE, search_flt, attrlist=attrlist, serverctrls=[req_ctrl])
  all_active_ad_users   = {}
  pages                 = 0

  while True:
    pages += 1
    rtype, rdata, rmsgid, serverctrls = l.result3(msgid,resp_ctrl_classes=known_ldap_resp_ctrls)
    for entry in rdata:
      if 'mail' in entry[1] and entry[1]['mail'][0]:
        email = entry[1]['mail'][0]
        all_active_ad_users[email.lower()] = True
    pctrls = [
      c
      for c in serverctrls
      if c.controlType == SimplePagedResultsControl.controlType
    ]
    if pctrls:
      if pctrls[0].cookie:
        # Copy cookie from response control to request control
        req_ctrl.cookie = pctrls[0].cookie
        msgid = l.search_ext(ad_basedn, ldap.SCOPE_SUBTREE, search_flt, attrlist=attrlist, serverctrls=[req_ctrl])
      else:
        break
    else:
      raise Exception("AD query Warning: Server ignores RFC 2696 control.")
      break
  l.unbind_s()
  return all_active_ad_users


def get_guest_users():
  url = '%s/api/users.list' % slack_subdomain
  http_response = requests.get(url=url, params={'token': slack_token})
  http_response.raise_for_status()
  users = http_response.json()['members']
  guest_users = {}
  for user in users:
    # restricted users are guests.
    if user.get('is_ultra_restricted') or user.get('is_restricted'):
      guest_users[user['id']] = user['profile']['email']
  return guest_users


def get_owner_users():
  url = '%s/api/users.list' % slack_subdomain
  http_response = requests.get(url=url, params={'token': slack_token})
  http_response.raise_for_status()
  users = http_response.json()['members']
  owner_users = {}
  for user in users:
    if user.get('is_owner'):
      owner_users[user['id']] = user['profile']['email']
  return owner_users


def slack_message_owners(message, owners):
  url = '%s/api/chat.postMessage' % slack_subdomain
  message = '```%s```' % message
  for owner in owners.keys():
    payload = {
      'token'     : slack_token,
      'channel'   : owner,
      'text'      : message,
      'username'  : 'slack reaper',
      'icon_emoji': slack_icon_emoji
    }
    http_response = requests.get(url=url, params=payload)
    http_response.raise_for_status()
  return True


def enable_slack_user(slack_user, owners):
  url = '%s/scim/v1/Users/%s' % (slack_api_host, slack_user['id'])
  payload = {'id': slack_user['id'], 'active': True}
  slack_user_email = get_primary_slack_email(slack_user['emails'])
  response = requests.patch(url, data=json.dumps(payload), headers=slack_http_header)
  response.raise_for_status()
  log_msg = 'slack_id: %s email: %s has been brought back from the dead according to AD' % (slack_user['id'], slack_user_email)
  logger.info(log_msg)
  slack_message_owners(message=log_msg, owners=owners)
  return True


def disable_slack_user(slack_id, slack_email, reason, owners):
  url = '%s/scim/v1/Users/%s' % (slack_api_host, slack_id)
  http_response = requests.delete(url, headers=slack_http_header)
  http_response.raise_for_status()
  log_msg = 'slack_id: %s email: %s has had their session(s) expired and is disabled because %s' % (slack_id, slack_email, reason)
  logger.info(log_msg)
  slack_message_owners(message=log_msg, owners=owners)
  return True


def get_primary_slack_email(emails):
  for email in emails:
    if email['primary']:
      return email['value']


def sync_slack_ldap():
  logger.info('Looking for slack users to delete that do not exist or are not active in corp LDAP')
  guest_users               = get_guest_users()
  all_slack_owners          = get_owner_users()
  all_slack_scim_users      = get_all_slack_scim_users()
  all_active_ad_users       = get_all_active_ad_users()
  slack_users_to_be_deleted = {}

  # Collect all the users who should be deleted.
  for slack_user in all_slack_scim_users:
    slack_user_email = get_primary_slack_email(slack_user['emails'])
    # if a slack user is disabled, but they're active in AD, activate them in slack
    if not slack_user['active'] and all_active_ad_users.get(slack_user_email):
      enable_slack_user(slack_user, all_slack_owners)
    # skip slack users that are already disabled ( active: False )
    if not slack_user['active']:
      continue
    # skip guest / bot accounts
    if guest_users.get(slack_user['id']) or '@slack-bots.com' in slack_user_email:
      continue
    # Since slack has infinite web/mobile session cookies, we will disable those sessions if the users ldap account doesn't exist
    if not all_active_ad_users.get(slack_user_email):
      slack_users_to_be_deleted[slack_user_email] = {'slack_id': slack_user['id'], 'reason': 'they do not exist in corp LDAP.'}

  percent_slack_users_deleted = float(len(slack_users_to_be_deleted)) / len(all_slack_scim_users)
  # raise exception if we try to delete too many users as a failsafe.

  if percent_slack_users_deleted > max_delete_failsafe:
    raise Exception('The failsafe threshold for deleting too many slack users was reached. No users were deleted.')

  # After the failsafe is over, go through and delete all the users who should be deleted.
  for slack_email, value in slack_users_to_be_deleted.iteritems():
    disable_slack_user(slack_id=value['slack_id'], slack_email=slack_email, reason=value['reason'], owners=all_slack_owners)


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
  logging.getLogger('requests').setLevel(logging.ERROR)
  error_counter = 0
  while True:
    try:
      sync_slack_ldap()
      error_counter = 0
    except Exception as error:
      logger.exception(error)
      # if we regularly have exceptions, let slack owners know about it once per day.
      error_counter += 1
      if error_counter % 48 == 4:
        slack_error = 'This exception is being sent to slack since it is the 4th one is a row. %s' % error
        owners = get_owner_users()
        slack_message_owners(slack_error, owners)
    sleep_message = 'Sleeping for %s minutes' % str(int(sync_run_interval) / 60)
    logger.info(sleep_message)
    time.sleep(sync_run_interval)
