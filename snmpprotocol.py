"""SNMP Protocol for Twisted

This protocol exposes most of the functionality of the pysnmp
manager side operations, with the notable exceptions of traps,
and retrieval from large numbers of agents.

Parallel retrieval from large numbers of agents should be
doable simply by creating ports for each agent and calling
get on that port's protocol.
"""
from twisted.internet import protocol, reactor
from twisted.internet import error as twisted_error
from pysnmp.proto import v2c, v1, error
import traceback
from twistedsnmp import datatypes, agentproxy

class SNMPProtocol(protocol.DatagramProtocol):
	"""Base class for SNMP datagram protocol

	attributes:
		requests -- dictionary holding request-key: df,timer
			where request-keys are calculated by our getRequestKey
			method, df is the defer for callbacks to the request,
			and timer is the timeout timer for the request.
	"""
	def __init__(self, port=20000 ):
		"""Initialize the SNMPProtocol object

		port -- port on which we are listening...
		"""
		self.port = port
		self.requests = {}
		
	# Twisted entry points...
	def datagramReceived(self, datagram, address):
		"""Process a newly received datagram

		Converts the message to a pysnmp response
		object, then dispatches it to the appropriate
		callback based on the message ID as determined
		by self.getRequestKey( response, address ).

		Passes on the response object itself to the
		callback, as the response object is needed for
		table download and the like.
		"""
		response = self.decode(datagram)
		if response is None:
			print 'Bad response', address, repr(datagram)
			return
		key = self.getRequestKey( response, address )
		if key in self.requests:
			df,timer = self.requests[key]
			if hasattr( timer, 'cancel' ):
				try:
					timer.cancel()
				except (twisted_error.AlreadyCalled,twisted_error.AlreadyCancelled):
					pass
			del self.requests[key]
			try:
				if not df.called:
					reactor.callLater(
						0.001, df.callback, response
					)
			except :
				print response
				raise
##		else:
##			# is a timed-out response that finally arrived
##			print 'timed out response for key %r'%(key,), response
##			print 'pending', self.requests.keys()
	def send(self, request, target):
		"""Send a request (string) to the network"""
		return self.transport.write( request, target )
		
	# implementation details...
	def getRequestKey( self, request, target ):
		"""Get the request key from a request/response"""
		for key in [
			'get_request', 'get_response',
			'get_next_request', 'get_bulk_request',
			'response', 'set_request',
		]:
			try:
				return target, request['pdu'][key]['request_id']
			except KeyError:
				pass
			except TypeError:
				import pdb
				pdb.set_trace()
				print key
				print request['pdu']
				print request['pdu'][key]
				print request['pdu'][key]['request_id']
		raise KeyError( """Unable to get a request key id from %s for target %s"""%( request, target))

	def decode( self, message ):
		"""Decode a datagram message"""
		for implementation in v2c, v1:
			try:
				response = implementation.GetResponse()
				response.decode( message )
				return response
			except Exception, err:
				pass
				##traceback.print_exc()
		return None

def port( portNumber=-1, protocolClass=SNMPProtocol ):
	"""Create a new listening TwistedSNMP port (with attached protocol)

	portNumber -- a numeric port specifier, or a sequence of
		numeric port specifiers to search
		if not specified, defaults to range(20000,30000)
	protocolClass -- the protocol class to create, will
		be called with default arguments () to create the
		protocol instance
		
		XXX should that be an instance? this is a convenience
		method, but seems silly to restrict it to protocols
		that have the same initialiser.  Oh well.

	This is a convenience function which allows you to specify
	a range of UDP ports which will be searched in order to
	create a new TwistedSNMP protocol.  Since the client-side
	protocol's port number is of minimal interest it is often
	handy to have this functionality available.

	returns Twisted UDP port object, with the SNMPProtocol
		instance available as port.protocol on that object
	"""
	if portNumber == -1:
		ports = xrange(25000,30000)
	elif isinstance( portNumber, (int,long)):
		ports = [portNumber]
	else:
		ports = portNumber
	for port in ports:
		try:
			return reactor.listenUDP(
				port, protocolClass(),
			)
		except twisted_error.CannotListenError:
			pass
	raise twisted_error.CannotListenError(
		"""Could not listen on *any* port in our range of potential ports! %s"""%(
			repr(ports)[:30],
		),
	)

def test():
	port = reactor.listenUDP(20000, SNMPProtocol() )
	proxy = agentproxy.AgentProxy(
		"205.207.149.252", 161, protocol = port.protocol,
	)
	def onSuccess( value ):
		print 'Success:'
		if isinstance( value, dict ):
			value = value.items()
		for key,item in value:
			print key, len(item)
	def onFailure( reason ):
		print 'Failure:', reason
	d = proxy.get( ['.1.3.6.1.2.1.1.1.0', '.1.3.6.1.2.1.1.5.0', '.1.3.6.1.2.1.1.6.0'] )
	d.addCallbacks( onSuccess, onFailure )

	d = proxy.getTable( [ '.1.3.6.1.4.1.1456.2.2.6.1.3' ] )
	d.addCallbacks( onSuccess, onFailure )

	proxy2 = agentproxy.AgentProxy(
		"205.207.149.252",
		community = 'public',
		snmpVersion = 'v2',
		protocol = port.protocol,
	)
	d = proxy2.getTable( [
		'.1.3.6.1.4.1.1456.2.2.6.1.2',
		'.1.3.6.1.4.1.1456.2.3.2.1.18',
	] )
	d.addCallbacks( onSuccess, onFailure )
	
	

def main():
	reactor.callLater( 1, test)
	reactor.run()

if __name__ == "__main__":
	main()