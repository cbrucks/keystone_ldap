# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 OpenStack LLC
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from __future__ import absolute_import
import copy

import memcache

from keystone import config
from keystone import exception
from keystone import token
from keystone.common import utils


CONF = config.CONF
config.register_str('servers', group='memcache', default='localhost:11211')


class Token(token.Driver):
    def __init__(self, client=None):
        self._memcache_client = client

    @property
    def client(self):
        return self._memcache_client or self._get_memcache_client()

    def _get_memcache_client(self):
        memcache_servers = CONF.memcache.servers.split(',')
        self._memcache_client = memcache.Client(memcache_servers, debug=0)
        return self._memcache_client

    def _prefix_token_id(self, token_id):
        return 'token-%s' % token_id.encode('utf-8')

    def _prefix_user_id(self, user_id):
        return 'usertokens-%s' % user_id.encode('utf-8')

    def get_token(self, token_id):
        ptk = self._prefix_token_id(token_id)
        token = self.client.get(ptk)
        if token is None:
            raise exception.TokenNotFound(token_id=token_id)

        return token

    def create_token(self, token_id, data):
        data_copy = copy.deepcopy(data)
        ptk = self._prefix_token_id(token_id)
        if 'expires' not in data_copy:
            data_copy['expires'] = self._get_default_expire_time()
        kwargs = {}
        if data_copy['expires'] is not None:
            expires_ts = utils.unixtime(data_copy['expires'])
            kwargs['time'] = expires_ts
        self.client.set(ptk, data_copy, **kwargs)
        if 'id' in data['user']:
            token_data = token_id
            user_id = data['user']['id']
            user_key = self._prefix_user_id(user_id)
            if not self.client.append(user_key, ',%s' % token_data):
                if not self.client.add(user_key, token_data):
                    if not self.client.append(user_key, ',%s' % token_data):
                        msg = _('Unable to add token user list.')
                        raise exception.UnexpectedError(msg)
        return copy.deepcopy(data_copy)

    def delete_token(self, token_id):
        # Test for existence
        self.get_token(token_id)
        ptk = self._prefix_token_id(token_id)
        result = self.client.delete(ptk)
        return result

    def list_tokens(self, user_id, tenant_id=None):
        tokens = []
        user_key = self._prefix_user_id(user_id)
        user_record = self.client.get(user_key) or ""
        token_list = user_record.split(',')
        for token_id in token_list:
            ptk = self._prefix_token_id(token_id)
            token_ref = self.client.get(ptk)
            if token_ref:
                if tenant_id is not None:
                    if 'tenant' not in token_ref:
                        continue
                    if token_ref['tenant'].get('id') != tenant_id:
                        continue
                tokens.append(token_id)
        return tokens
