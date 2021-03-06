#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


from testrunner import testhelp

import errno
import logging
import socket
from conary.lib import log
from conary.lib import timeutil
from conary.lib import util
from conary.lib.compat import namedtuple
from conary.lib.http import http_error
from conary.lib.http import opener as opener_mod


class OpenerTest(testhelp.TestCase):

    def setUp(self):
        testhelp.TestCase.setUp(self)

        # Silence Conary logger
        self._savedHandlers = log.logger.handlers
        log.logger.handlers = [logging.StreamHandler(open('/dev/null', 'w'))]

    def tearDown(self):
        # Restore Conary logger
        log.logger.handlers = self._savedHandlers
        self._savedHandlers = []

        testhelp.TestCase.tearDown(self)

    def testProxyErrors(self):
        """Opener automatically retries on gateway errors."""
        self.mock(timeutil.BackoffTimer, 'sleep', lambda self: None)
        badResponse = MockResponse(502, 'Bad Gateway')
        responses = []
        class MockConnection(object):
            def __init__(self, *args, **kwargs):
                pass
            def request(self, *args, **kwargs):
                return responses.pop(0)
        opener = opener_mod.URLOpener()
        opener.connectionFactory = MockConnection

        # Eventually succeeds
        responses = [badResponse] * 2 + [MockResponse.OK]
        fobj = opener.open('http://nowhere./')

        # Fails enough to run out of retries
        responses = [badResponse] * 3 + [MockResponse.OK]
        err = self.assertRaises(socket.error, opener.open, 'http://nowhere./')
        # Proxy errors are thrown as socket.error(ECONNREFUSED)
        self.assertEqual(err.args[0], errno.ECONNREFUSED)

    def testRetriableErrors(self):
        """Opener automatically retries on socket errors."""
        self.mock(timeutil.BackoffTimer, 'sleep', lambda self: None)
        failures = []
        failure = socket.error(errno.ECONNREFUSED, 'Connection refused')
        class MockConnection(object):
            def __init__(self, *args, **kwargs):
                pass
            def request(self, *args, **kwargs):
                if failures:
                    try:
                        raise failures.pop(0)
                    except:
                        raise http_error.RequestError(util.SavedException())
                else:
                    return MockResponse.OK
        opener = opener_mod.URLOpener()
        opener.connectionFactory = MockConnection

        # Eventually succeeds
        failures = [failure] * 2
        fobj = opener.open('http://nowhere./')

        # Fails enough to run out of retries
        failures = [failure] * 3
        err = self.assertRaises(socket.error, opener.open, 'http://nowhere./')
        self.assertEqual(err.args[0], errno.ECONNREFUSED)

    def testFatalErrors(self):
        """Opener does not retry on post-request errors."""
        self.mock(timeutil.BackoffTimer, 'sleep', lambda self: None)
        failures = []
        failure = socket.error(errno.ECONNRESET, 'Connection reset by peer')
        class MockConnection(object):
            def __init__(self, *args, **kwargs):
                pass
            def request(self, *args, **kwargs):
                if failures:
                    raise failures.pop(0)
                else:
                    return MockResponse.OK
        opener = opener_mod.URLOpener()
        opener.connectionFactory = MockConnection

        # Eventually succeeds, but we give up immediatey
        failures = [failure]
        err = self.assertRaises(socket.error, opener.open, 'http://nowhere./')
        self.assertEqual(err.args[0], errno.ECONNRESET)


class MockResponse(namedtuple('MockResponse', 'status reason')):
    msg = read = None
    version = 11
    def getheader(self, name, default=None):
        return None
MockResponse.OK = MockResponse(200, 'OK')
