# -*- coding: utf-8 -*-

import aiohttp
import json
import logging

from aiohttp.client import ClientTimeout


class APIError(Exception):
    pass


class MIClient(object):
    """
    Base Direct Device Integration API client providing GET, POST and PUT
    helpers as well as access to next level API resources.
    """

    error_responses = {
        400: 'Bad Request - e.g. invalid parameters',
        401: 'The request requires user authentication.',
        403: 'Insufficient permissions or data volume restriction applies.',
        404: 'Resource not available or device unknown.',
        405: 'Method Not Allowed',
        406: 'Accept header is specified and is not application/json.',
        429: 'Too many requests.'
    }

    def __init__(self, session, timeout=10, **kwargs):
        self.logger = logging.getLogger('hbloader')
        self.logger.info('')

        self.session = session
        self.host = '{}:{}'.format(kwargs['ip'],kwargs['port'])
        self.ssl = kwargs['ssl']
        auth_str = '{}\\{}'.format(kwargs['tenant_id'], kwargs['login'])
        self.auth = aiohttp.BasicAuth(auth_str, kwargs['password'])
        self.logger.debug('auth_str: {}\n{}\n'.format(auth_str, self.auth))
        self.tenant = kwargs['tenant_id']
        self.target_name = kwargs['target_name']
        self.controller_id = kwargs['controller_id']
        self.timeout = timeout
        self.headers = {}

    async def __call__(self):
        """
        Get controller data
        """
        self.logger.info('')
        return await self.get_resource('/rest/v1/targets')

    async def register_target(self):
        '''
        Manually register target on controller 
        '''

        self.logger.info('')

        data = {}
        data['controllerId'] = self.controller_id
        data['name'] = self.target_name

        post_data = []
        post_data.append(data)

        self.logger.debug("post_data {}".format(post_data))

        await self.post_resource('/rest/v1/targets', post_data)

    #async def  get_target_details(self, )
    #   return await self.get_resource('/rest/v1/targets/{controllerId}')

    def build_api_url(self, api_path):
        """
        Build the actual API URL.

        Args:
            api_path(str): REST API path

        Returns:
            Expanded API URL with protocol (http/https) and host prepended
        """
        self.logger.info('')
        protocol = 'https' if self.ssl else 'http'
        return '{protocol}://api.{host}{api_path}'.format(
            protocol=protocol, host=self.host, api_path=api_path)


    async def get_resource(self, api_path, query_params={}, **kwargs):
        """
        Helper method for HTTP GET API requests.

        Args:
            api_path(str): REST API path
        Keyword Args:
            query_params: Query parameters to add to the API URL
            kwargs: Other keyword args used for replacing items in the API path

        Returns:
            Response JSON data
        """
        self.logger.info('')
        get_headers = {
            'Accept': 'application/json',
            **self.headers
        }
        self.logger.info(get_headers)
        
        url = self.build_api_url(
                api_path.format(
                    tenant=self.tenant,
                    controllerId=self.controller_id,
                    **kwargs))

        self.logger.info(self.auth)

        self.logger.debug('GET {} {}'.format(url, get_headers))
        async with self.session.get(url, headers=get_headers,
                                    params=query_params,
                                    auth=self.auth,
                                    timeout=ClientTimeout(self.timeout)) as resp:
            await self.check_http_status(resp)
            json = await resp.json()
            return json


    async def post_resource(self, api_path, data, **kwargs):
        """
        Helper method for HTTP POST API requests.

        Args:
            api_path(str): REST API path
            data: JSON data for POST request
        Keyword Args:
            kwargs: keyword args used for replacing items in the API path
        """
        self.logger.info('')

        post_headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        url = self.build_api_url(
                api_path.format(
                    tenant=self.tenant,
                    controllerId=self.controller_id,
                    **kwargs))
        self.logger.debug('POST {}'.format(url))

        async with self.session.post(url, headers=post_headers,
                                     data=json.dumps(data),
                                     auth=self.auth,
                                     timeout=ClientTimeout(self.timeout)) as resp:
            await self.check_http_status(resp)


    async def check_http_status(self, resp):
        """Log API error message."""

        self.logger.info('')
        
        if resp.status not in [200, 201]:
            error_description = await resp.text()
            if error_description:
                self.logger.debug('API error: {}'.format(error_description))

            if resp.status in self.error_responses:
                reason = self.error_responses[resp.status]
            else:
                reason = resp.reason

            raise APIError('{status}: {reason}'.format(
                status=resp.status, reason=reason))
