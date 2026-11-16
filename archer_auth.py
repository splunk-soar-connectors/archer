# File: archer_auth.py
#
# Copyright (c) 2016-2026 Splunk Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under
# the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
# either express or implied. See the License for the specific language governing permissions
# and limitations under the License.

import requests

import archer_consts as consts


class ArcherAPIError(Exception):
    """An Archer API failure that action handlers must preserve."""


class ArcherAuthenticationError(ArcherAPIError):
    """Archer rejected the configured authentication credential."""


class ArcherPermissionError(ArcherAPIError):
    """Archer denied permission to perform an operation."""


class ArcherConfigurationError(ValueError):
    """The selected Archer authentication configuration is invalid."""


def request_failure_reason(error):
    """Return a controlled description for an HTTP request failure."""
    if isinstance(error, requests.Timeout):
        return "timed out"
    if isinstance(error, requests.ConnectionError):
        return "could not connect"
    return "failed"


def controlled_error_message(error):
    """Describe expected failures without including arbitrary exception text."""
    if isinstance(error, ArcherAPIError):
        return str(error)
    if isinstance(error, ArcherConfigurationError):
        return str(error)
    if isinstance(error, (KeyError, IndexError, TypeError)):
        return consts.ARCHER_ERR_RESPONSE_FORMAT
    if isinstance(error, ValueError):
        return consts.ARCHER_ERR_INVALID_DATA
    if isinstance(error, OSError):
        return consts.ARCHER_ERR_LOCAL_RESOURCE
    return consts.ARCHER_ERR_UNEXPECTED


class ArcherAuth:
    """Select credentials for both transports without persisting the configured PAT."""

    def __init__(self, config):
        self.mode = config.get("auth_type", consts.ARCHER_AUTH_PASSWORD)
        self._pat = config.get("personal_access_token")
        self.session_token = None

        if self.mode not in (consts.ARCHER_AUTH_PASSWORD, consts.ARCHER_AUTH_PAT):
            raise ArcherConfigurationError("Select a supported authentication type")
        if self.is_pat:
            if not isinstance(self._pat, str) or not self._pat:
                raise ArcherConfigurationError("Personal access token is required")
        else:
            username, password = config.get("username"), config.get("password")
            if not isinstance(username, str) or not username.strip() or not isinstance(password, str) or not password:
                raise ArcherConfigurationError("Username and password are required for username/password authentication")

    @property
    def is_pat(self):
        return self.mode == consts.ARCHER_AUTH_PAT

    @property
    def token(self):
        token = self._pat if self.is_pat else self.session_token
        if not token:
            raise ArcherAuthenticationError("No Archer authentication credential is available")
        return token

    def headers(self, transport):
        if transport == "soap" and not self.is_pat:
            return {}
        return {"Authorization": f'Archer session-id="{self.token}"'}

    def authentication_error(self):
        if self.is_pat:
            return ArcherAuthenticationError(
                "PAT authentication was rejected by Archer. Verify the configured token and its expiration or revocation status"
            )
        return ArcherAuthenticationError("Archer session authentication failed. Verify the asset credentials")
