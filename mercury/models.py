# coding: utf-8

#
#    Copyright 2013-2014 Roma servizi per la mobilità srl
#    Developed by Luca Allulli and Damiano Morosi
#
#    This file is part of Muoversi a Roma for Developers.
#
#    Muoversi a Roma for Developers is free software: you can redistribute it
#    and/or modify it under the terms of the GNU General Public License as
#    published by the Free Software Foundation, version 2.
#
#    Muoversi a Roma for Developers is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
#    or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
#    for more details.
#
#    You should have received a copy of the GNU General Public License along with
#    Muoversi a Roma for Developers. If not, see http://www.gnu.org/licenses/.
#


from django.db import models
import rpyc
from rpyc.utils.server import ThreadedServer
from threading import Thread
from Queue import Queue
import cPickle as pickle
from django.db.models import Q
from time import sleep
from datetime import date, time, datetime, timedelta
import os
import random
import settings

"""
Esempio 1: creazione di un servizio Operazioni
	class OperazioniListener(MercuryListener):
		@autopickle
		def exposed_somma(dict):
			return dict['a'] + dict['b']
	
	operazioni = PeerType.objects.get(name='operazioni') 
	m = Mercury(somma, OperazioniListener)


Esempio 2: creazione di un servizio Operazioni; registrazione demone e watchdog
	class OperazioniListener(MercuryListener):
		@autopickle
		def exposed_somma(dict):
			return dict['a'] + dict['b']
	
	operazioni = PeerType.objects.get(name='operazioni')
	operazioni_daemon = Daemon.get_process_daemon('operazioni_daemon')
	m = Mercury(somma, OperazioniListener, watchdog_daemon=operazioni_daemon)
	operazioni_daemon.set_ready()


Esempio 3: uso del proxy

Avvio del server proxy:
	python manage.py run_mercury_proxy MERCURY_PROXY_PORT
	
Uso come client del servizio peer_type:
	c = rpyc.connect(MERCURY_PROXY_HOST, MERCURY_PROXY_PORT)
	m = c.root.get_mercury_client(peer_type)
	# Chiamata sincrona:
	risultato = m.sync_any(metodo, parametri)
	# Chiamata asincrona:
	m.async_all(metodo, parametri)
	
"""

config = {
	'allow_public_attrs': True,
	'allow_pickle': True,
}

# Message broker

class PeerType(models.Model):
	name = models.CharField(max_length=31)
	
	def __unicode__(self):
		return self.name

class Route(models.Model):
	sender = models.ForeignKey(PeerType, related_name='fstar')
	receiver = models.ForeignKey(PeerType, related_name='bstar')
	active = models.BooleanField(default=True, blank=True)
	
	def __unicode__(self):
		return u"[%s] %s --> %s" % ('ON' if self.active else 'OFF', self.sender, self.receiver)

class Peer(models.Model):
	type = models.ForeignKey(PeerType)
	host = models.CharField(max_length=63)
	port = models.IntegerField()
	active = models.BooleanField(blank=True, default=True)
	blocked_until = models.DateTimeField(blank=True, null=True, db_index=True, default=None)
	daemon = models.ForeignKey('Daemon', blank=True, null=True, default=None)
	
	def __unicode__(self):
		return "%s" % self.type
	
	def get_receivers(self):
		routes = Route.objects.filter(sender=self.type, active=True)
		out = []
		for r in routes:
			out.extend(Peer.objects.filter(
				Q(blocked_until__isnull=True) | Q(blocked_until=datetime.now()),
				type=r.receiver,
				active=True
			))
		return out
	
	@classmethod
	def get_receivers_static(cls, name):
		routes = Route.objects.filter(sender__name=name, active=True)
		out = []
		for r in routes:
			out.extend(Peer.objects.filter(
				Q(blocked_until__isnull=True) | Q(blocked_until=datetime.now()),
				type=r.receiver,
				active=True
			))
		return out
		
	def connect_any(self):
		ss = self.get_receivers()
		random.shuffle(ss)
		for s in ss:
			try:
				return rpyc.connect(s.host, s.port, config=config)
			except Exception:
				#s.bloccato = datetime.now()
				#s.save()
				pass
		return None
	
	@classmethod
	def connect_any_static(cls, name):
		ss = cls.get_receivers_static(name)
		random.shuffle(ss)
		for s in ss:
			try:
				return rpyc.connect(s.host, s.port, config=config)
			except Exception:
				#s.bloccato = datetime.now()
				#s.save()
				pass
		return None
	
	def connect_all(self):
		ss = self.get_receivers()
		cs = []
		for s in ss:
			try:
				cs.append(rpyc.connect(s.host, s.port, config=config))
			except Exception:
				s.bloccato = datetime.now()
				s.save()
		return cs
	
	@classmethod	
	def connect_all_static(cls, name):
		ss = cls.get_receivers_static(name)
		cs = []
		for s in ss:
			try:
				cs.append(rpyc.connect(s.host, s.port, config=config))
			except Exception:
				s.bloccato = datetime.now()
				s.save()
		return cs	
	
class MercuryWorker(Thread):
	def __init__(self, owner):
		Thread.__init__(self)
		self.owner = owner
		self.start()
		
	def run(self):
		exit = False
		while not exit:
			try:
				el = self.owner.queue.get()
				if el is not None:
					method = el['method']
					c = el['connection']
					getattr(c.root, method)(el['param'])
				else:
					exit = True
			except Exception:
				pass
			
class MercuryWatchdog(Thread):
	def __init__(self, owner, daem):
		Thread.__init__(self)
		self.owner = owner
		self.daem = daem
		self.start()
		
	def run(self):
		while True:
			try:
				c = rpyc.connect(self.owner.peer.host, self.owner.peer.port, config=config)
				assert(c.root.ping() == 'OK')
				c.close()
			except Exception:
				self.daem.action = 'R'
				self.daem.save()
			sleep(10)
			
class Watchdog(Thread):
	def __init__(self, name):
		Thread.__init__(self)
		self.name = name
		
	def run(self):
		while True:
			sleep(10)
			print "Watchdog cycle"
			ss = Peer.get_receivers_static(self.name)
			for s in ss:
				try:
					print "Testing"
					c = rpyc.connect(s.host, s.port, config=config)
					assert(c.root.ping() == 'OK')
					c.close()
					print "Test ok"
				except Exception, e:
					print e
					print "Test KO"
					if s.daemon is not None:
						s.daemon.action = 'R'
						s.daemon.save()
					print "Restart scheduled"

class Mercury(Thread):
	def __init__(self, type, listener, nworkers=3, daemon=None, watchdog_daemon=None):
		Thread.__init__(self)
		self.queue = Queue()
		self.workers = [MercuryWorker(self) for i in range(nworkers)]
		if not isinstance(type, PeerType):
			type = PeerType.objects.get(name=type)
		self.type = type
		self.listener = listener
		if listener is not None:
			self.server = ThreadedServer(listener, port=0, protocol_config=config)
			self.peer = Peer(
				type=type,
				host=settings.LOCAL_IP,
				port=self.server.port,
				daemon=daemon,
			)
			self.peer.save()
			self.start()
		else:
			self.server = None
			self.peer = None
		self.watchdog = None
		if watchdog_daemon is not None:
			self.watchdog = MercuryWatchdog(self, watchdog_daemon)

		
	# API
	def async_all(self, method, param):
		if self.peer is not None:
			cs = self.peer.connect_all()
		else:
			cs = Peer.connect_all_static(self.type.name)
		for c in cs:
			self.queue.put({
				'connection': c,
				'method': method,
				'param': pickle.dumps(param, protocol=2),
			})
	
	def sync_any(self, method, param):
		if self.peer is not None:
			c = self.peer.connect_any()
		else:
			c = Peer.connect_any_static(self.type.name)
		return pickle.loads(getattr(c.root, method)(pickle.dumps(param, 2)))
	
	@classmethod
	def sync_any_static(cls, name, method, param):
		c = Peer.connect_any_static(name)
		return pickle.loads(getattr(c.root, method)(pickle.dumps(param, 2)))
	
	def rpyc_connect_any(self):
		if self.peer is not None:
			c = self.peer.connect_any()
		else:
			c = Peer.connect_any_static(self.type.name)
		return c
	
	def rpyc_connect_all(self):
		if self.peer is not None:
			cs = self.peer.connect_all()
		else:
			cs = Peer.connect_all_static(self.type.name)
		return cs
	
	@classmethod
	def rpyc_connect_any_static(cls, name):
		return Peer.connect_any_static(name)	
	
	@classmethod
	def rpyc_connect_all_static(cls, name):
		return Peer.connect_all_static(name)	
	
	def close(self):
		if self.peer is not None:
			self.peer.delete()
		if self.server is not None:
			self.server.close()
		for w in self.workers:
			self.queue.put(None)
		
	def run(self):
		print "Server listening"
		self.server.start()
		print "Server closed"
	
def autopickle(f):
	def g(self, param):
		return pickle.dumps(f(self, pickle.loads(param)), 2)
	return g

class MercuryListener(rpyc.Service):
	def exposed_ping(self):
		return 'OK'
	
class MercuryProxy(MercuryListener):
	def exposed_delete_mercury_clients(self, type):
		Peer.objects.filter(type__name=type).delete()
	
	def exposed_get_mercury_client(self, type):
		return Mercury(PeerType.objects.get(name=type), None)
	
	
# Daemon management

control_action_choices = [
	('N', 'Normal mode'),
	('F', 'Freeze current state'),
	('S', 'Stop all (do not restart)'),
	('R', 'Restart all'),
]

class DaemonControl(models.Model):
	name = models.CharField(max_length=31, db_index=True, unique=True)
	instances = models.IntegerField()
	restart_from = models.TimeField()
	restart_to = models.TimeField()
	restart_timeout = models.IntegerField()
	max_restart_time = models.IntegerField(default=3)
	command = models.CharField(max_length=1023)
	action = models.CharField(max_length=1, default='F', choices=control_action_choices)
	
	def __unicode__(self):
		return self.name

daemon_action_choices = [
	('N', 'Normal mode'),
	('F', 'Freeze (suspend restart)'),
	('R', 'Restart'),
]

class Daemon(models.Model):
	control = models.ForeignKey(DaemonControl)
	active_since = models.DateTimeField(db_index=True, auto_now_add=True)
	ready = models.BooleanField(blank=True, default=False)
	pid = models.IntegerField(default=-1)
	action = models.CharField(max_length=1, default='N', choices=daemon_action_choices)
	
	@classmethod
	def get_process_daemon(cls, name):
		return cls.objects.get(control__name=name, pid=os.getpid()) 
	
	def set_ready(self):
		self.ready = True
		self.save()
	
	def __unicode__(self):
		return u"[%s] %s (%s)" % (self.active_since, self.control, self.pid)

	