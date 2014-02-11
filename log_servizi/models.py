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
from xmlrpclib import Fault
import json
from xmlrpchandler import dispatcher, rpc_handler
from django.conf.urls.defaults import url
import uuid
import hashlib
import datetime
import inspect
#from django.contrib.sessions.backends.db import SessionStore
from django.contrib.auth import get_user
import errors
from servizi.models import Servizio, Versione
import settings
import logging
import importlib
from jsonrpc import jsonrpc_method

session_engine = importlib.import_module(settings.SESSION_ENGINE)

from fz_SimpleXMLRPCServer import SimpleXMLRPCDispatcher
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

standard_logger = logging.getLogger('standard')

if settings.MONGO_ENABLED:
	from pymongo import Connection
	#mdbcon = Connection('192.168.90.88', 27017)
	mdbcon = Connection('127.0.0.1', 27017)
	invocazioni = mdbcon.log.invocazioni

dthandler = lambda obj: obj.isoformat() if isinstance(obj, datetime.datetime) else None


class Invocazione(models.Model):
	token = models.CharField(max_length=100)
	versione = models.ForeignKey(Versione)
	metodo = models.CharField(max_length=40)
	esito = models.IntegerField()
	orario = models.DateTimeField()
	
	def __unicode__(self):
		return u"%s, %s, %s" % (unicode(self.orario), unicode(self.versione), self.metodo)
	
	class Meta:
		verbose_name_plural = 'Invocazioni'	
		
class Parametro(models.Model):
	invocazione = models.ForeignKey(Invocazione)
	nome = models.CharField(max_length=31)
	valore = models.CharField(max_length=1023)
	
	def __unicode__(self):
		return u"%s, %s: %s" % (unicode(self.invocazione), self.nome, self.valore)
	
	class Meta:
		verbose_name_plural = 'Parametri'		
	
class Risposta(models.Model):
	invocazione = models.ForeignKey(Invocazione)
	valore = models.CharField(max_length=65000)
	
	def __unicode__(self):
		return u"%s, %s" % (unicode(self.invocazione), self.valore)
	
	class Meta:
		verbose_name_plural = 'Risposte'		
	
class ServerVersione(SimpleXMLRPCDispatcher):
	def __init__(self, nome_servizio, numero_versione):
		SimpleXMLRPCDispatcher.__init__(self, allow_none=True)
		servizio, created = Servizio.objects.get_or_create(nome=nome_servizio)
		self.versione, created = Versione.objects.get_or_create(servizio=servizio, numero=numero_versione)
		self.numero_versione = numero_versione
		
	def refresh(self):
		self.versione = Versione.objects.get(pk=self.versione.pk)
	
	def logger(self, nome):
		def decorator(f):
			try:
				nomi_parametri = f.saved_argspec[0]				
			except AttributeError, e:
				nomi_parametri = inspect.getargspec(f)[0]
			def g(*args):
				self.refresh()
				if not self.versione.is_attiva():
					# todo: usare file con la definizione dei fault
					raise Fault(799, "Servizio non accessibile")
				inv = None
				if self.versione.log_invocazioni or self.versione.log_parametri or self.versione.log_risposte:
					i = Invocazione(
						token=args[1],
						metodo=nome,
						versione=self.versione,
						esito=0,
						orario=datetime.datetime.now(),
					)
					i.save()
					inv = {
						'token': args[1],
						'servizio': self.versione.servizio.nome,
						'versione': self.versione.numero,
						'metodo': nome,
						'esito': 0,
						'orario': datetime.datetime.now(),
					}
					if self.versione.log_parametri:
						param = {}
						for j in range(1, len(args)):
							Parametro(
								invocazione=i,
								nome=nomi_parametri[j],
								valore=json.dumps(args[j], default=dthandler),
							).save()
							param[nomi_parametri[j]] = args[j]
							inv['parametri'] = param
				try:
					res = f(*args)
					if self.versione.log_risposte:
						Risposta(
							invocazione=i,
							valore=json.dumps(res, default=dthandler),
						).save()
						inv['risposta'] = res
					if inv is not None and settings.MONGO_ENABLED:
						invocazioni.insert(inv)
					return res
				except Fault as ft:
					if inv is not None:
						i.esito = ft.faultCode
						inv['esito'] = ft.faultCode
						i.save()
						if settings.MONGO_ENABLED:
							invocazioni.insert(inv)						
					raise ft	
				return res
			# Make g a well-behaved decorator
			g.__name__ = f.__name__
			g.__doc__ = f.__doc__
			g.__dict__.update(f.__dict__)
			return g
		return decorator
	
	def service_reply(self, f):
		def g(*args):
			ret = {}
			ret['id_richiesta'] = hashlib.md5(uuid.uuid1().hex).hexdigest()
			ret['risposta'] = f(*args)
			return ret
		# Make g a well-behaved decorator
		g.__name__ = f.__name__
		g.__doc__ = f.__doc__
		g.__dict__.update(f.__dict__)
		g.saved_argspec = inspect.getargspec(f)
		return g
	
	def enforce_login(self, group_required=None):
		"""
		Decorator. Enforce that 2nd param (token) was assigned to a logged user
		"""
		def decoratore(f):
			def g(*args):
				request = args[0]
				token = args[1]
				# Request may be None in order to call methods directly (via code/python console)
				if request is None:
					return f(*args)
				request.session = session_engine.SessionStore(session_key=token)
				u = get_user(request)
				if u.is_authenticated():
					if group_required is None:
						return f(*args)
					print "Autenticato, verifico gruppo"
					if type(group_required) not in [list, tuple, set]:
						groups_required = [group_required]
					else:
						groups_required=group_required 
					if len(u.groups.filter(name__in=groups_required)) > 0:
						return f(*args)
				raise errors.XMLRPC['XRE_NOT_LOGGED']
			# Make g a well-behaved decorator
			g.__name__ = f.__name__
			g.__doc__ = f.__doc__
			g.__dict__.update(f.__dict__)
			return g
		return decoratore
	
	def log_on_file(self, f, name):
		"""
		Decorator. Log on standard logger
		"""		
		def g(*args):
			dt_inizio_invocazione = datetime.datetime.now()
			standard_logger.debug("Invocato metodo %s" % name)
			res = f(*args)
			standard_logger.debug("Uscita dal metodo %s. Tempo impiegato: %s" % (name, unicode(datetime.datetime.now() - dt_inizio_invocazione)))
			return res
		
		# Make g a well-behaved decorator
		g.__name__ = f.__name__
		g.__doc__ = f.__doc__
		g.__dict__.update(f.__dict__)
		return g
	
	@csrf_exempt
	def rpc_handler(self, request):
		"""
		the actual handler:
		if you setup your urls.py properly, all calls to the xml-rpc service
		should be routed through here.
		If post data is defined, it assumes it's XML-RPC and tries to process as such
		Empty post assumes you're viewing from a browser and tells you about the service.
		"""
		#dt_inizio_invocazione = datetime.datetime.now()
		#standard_logger.debug("Invocato metodo")
		if request.method == 'POST':
			response = HttpResponse(mimetype="application/xml")
			response.write(self._marshaled_dispatch(request.raw_post_data, request=request))
		else:
			response = HttpResponse()
			response.write("<b>This is an XML-RPC Service.</b><br>")
			response.write("You need to invoke it using an XML-RPC Client!<br>")
			response.write("The following methods are available:<ul>")
			methods = self.system_listMethods()
	
			for method in methods:
				# right now, my version of SimpleXMLRPCDispatcher always
				# returns "signatures not supported"... :(
				# but, in an ideal world it will tell users what args are expected
				sig = self.system_methodSignature(method)
	
				# this just reads your docblock, so fill it in!
				help =  self.system_methodHelp(method)
	
				response.write("<li><b>%s</b>: [%s] %s" % (method, sig, help))
	
			response.write("</ul>")
			response.write('<a href="http://www.djangoproject.com/"> <img src="http://media.djangoproject.com/img/badges/djangomade124x25_grey.gif" border="0" alt="Made with Django." title="Made with Django."></a>')
	
		response['Content-length'] = str(len(response.content))
		#standard_logger.debug("Uscita dal metodo. Tempo impiegato: %s" % unicode(datetime.datetime.now() - dt_inizio_invocazione))
		return response
	
	def xmlrpc(self, name, require_token=True, group_required=None):
		"""
		Decorator. Turns a function into an xml-rpc method
		"""
		def decoratore(f):
			if require_token:
				f = self.enforce_login(group_required=group_required)(f)
			f = self.log_on_file(f, name)
			self.register_function(f, name)
			return f
		return decoratore
	
	def togli_token(self, f):
		def g(request, *args):
			return f(request, '', *args)
		return g
	
	def jsonrpc(self, nome):
		"""
		Decorator. Register a function as a json-rpc method. It discards token parameter
		"""
		def decoratore(f):
			nome_completo = str("%s%d_%s" % (self.versione.servizio.nome, self.numero_versione, nome))
			print nome_completo
			jsonrpc_method(nome_completo)(self.togli_token(f))
		return decoratore		
		
	
	def metodo(self, nome, require_token=True, group_required=None, json=True):
		print "Registro", nome
		def decoratore(f):
			if json and not group_required:
				self.jsonrpc(nome)(f)
			f = self.logger(nome)(self.service_reply(f))
			return self.xmlrpc(str("%s.%s" % (self.versione.servizio.nome, nome)), require_token=require_token, group_required=group_required)(f)
		return decoratore
		
	def get_url_entry(self):
		return url('^%d$' % self.versione.numero, self.rpc_handler)
		
	
def times2string(el):
	"""
	Analizza la struttura el e trasforma gli elementi di tipo time in stringhe HH:MM
	"""
	if isinstance(el, datetime.time):
		return el.strftime('%H:%M')
	elif isinstance(el, dict):
		return dict([(k, times2string(el[k])) for k in el])
	elif isinstance(el, list):
		return [times2string(k) for k in el]
	else:
		return el

def convert_times_to_string(f):
	def g(*args, **kwargs):
		res = f(*args, **kwargs)
		return times2string(res)
	# Make g a well-behaved decorator
	g.__name__ = f.__name__
	g.__doc__ = f.__doc__
	g.__dict__.update(f.__dict__)
	return g
