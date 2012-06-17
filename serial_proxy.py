#!python

from __future__ import absolute_import, print_function, unicode_literals
import urlparse
from twisted.web import http, client
from twisted.web.http import Request, HTTPChannel
from twisted.internet import reactor, Protocol
from zope.interface import implements
from twisted.internet.defer import succeed
from twisted.web.iweb import IBodyProducer

class StringProducer(object):
    implements(IBodyProducer)

    def __init__(self, body):
        self.body = body
        self.length = len(body)

    def startProducing(self, consumer):
        consumer.write(self.body)
        return succeed(None)

    def pauseProducing(self):
        pass

    def stopProducing(self):
        pass


class SerialProtocol(Protocol):
    def __init__(self, request):
        self.request = request

    def dataReceived(self, data):
        self.request.write(data)

    def connectionLost(self, reason):
        if not reason.check(client.ResponseDone):
            if reason.check(http.PotentialDataLoss):
                print('Possible data loss ', reason.getErrorMessage())
            else:
                print('Error ', reason.getErrorMessage())
                self.request.setResponseCode(501, 'Gateway error')
        

class SerialRequest(Request):
    def __init__(self, channel, queued, reactor = reactor):
        Request.__init__(self, channel, queued)
        self.reactor = reactor

    def success(response, request):
        # t.web.server.Request sets default values for these headers in its
        # 'process' method. When these headers are received from the remote
        # server, they ought to override the defaults, rather than append to
        # them.
        for key, value in response.headers.getAllRawHeaders():
            if key.lower() in ['server', 'date', 'content-type']:
                self.responseHeaders.setRawHeaders(key, [value])
            else:
                self.responseHeaders.addRawHeader(key, value)
        self.setResponseCode(response.code)
        response.deliverBody(SerialProtocol(request))

    def error(data, request):
        request.setResponseCode(501, "Gateway error")
        request.responseHeaders.addRawHeader("Content-Type", "text/html")
        request.write("<H1>Could not connect</H1>")
        request.finish()

    def process(self):
        parsed = urlparse.urlparse(self.uri)
        protocol = parsed[0]
        host = parsed[1]
        port = self.ports[protocol]
        if ':' in host:
            host, port = host.split(':')
            port = int(port)
        rest = urlparse.urlunparse(('', '') + parsed[2:])
        if not rest:
            rest = rest + '/'
        class_ = self.protocols[protocol]
        headers = self.getAllHeaders().copy()
        if 'host' not in headers:
            headers['host'] = host
        headers.pop('proxy-connection', None)
        self.content.seek(0, 0)
        s = self.content.read()
        d = self.channel.factory.agent.request(self.method, self.rest, headers, StringProducer(s))
        d.addCallbacks(success, error, self, self)


class SerialProxy(HTTPChannel):
    requestFactory = SerialRequest


class SerialProxyFactory(HTTPFactory):
    protocol = SerialProxy
    def __init__(self):
        HTTPFactory.__init__(self)
        self.agent = client.Agent(self.reactor, pool = client.HTTPConnectionPool())


if __name__ == '__main__':
    f = SerialProxyFactory()
    reactor.ListenTcp(8080, f)
