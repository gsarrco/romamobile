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

from models import *
from django.db import models, connections, transaction
from django.db.models import Q
from paline.models import IndirizzoAutocompl, ParolaIndirizzoAutocompl, PalinaPreferita
from percorso.models import IndirizzoPreferito
from autenticazione.models import TokenApp, TOKEN_APP_LENGTH
from servizi.utils import dict_cursor, project, datetime2mysql, group_required, generate_key
from servizi.views import get_fav, login_app_id_sito, delete_fav
from datetime import datetime, timedelta, time, date
from jsonrpc import jsonrpc_method
from urllib_transport import *
import xmlrpclib
import settings
import urlparse
from pprint import pprint
import importlib
from carpooling import models as carpooling
session_engine = importlib.import_module(settings.SESSION_ENGINE)
from django.contrib.auth import login, authenticate, logout, get_user
import traceback

login_ws_url = 'http://login.muoversiaroma.it/Handler.ashx'
logout_url = 'http://login.muoversiaroma.it/Logout.aspx?IdSito=%d' % settings.ID_SITO
password_sito = ''


@jsonrpc_method('servizi_autocompleta_indirizzo')
def autocompleta_indirizzo(request, cerca):
	parole = cerca.split()
	parole.sort(key=lambda x: -len(x))
	if len(parole) == 0:
		return {'cerca': cerca, 'risultati': []}
	maxlength = len(parole[0])
	if maxlength >= 3:
		pias = IndirizzoAutocompl.objects
	else:
		pias = IndirizzoAutocompl.objects.none()
	u = request.user
	auth = False
	if u.is_authenticated():
		auth = True
		pps = PalinaPreferita.objects.filter(gruppo__user=u)
		ips = IndirizzoPreferito.objects.filter(user=u)

	rrs = RicercaRecente.by_request(request, limit=False)

	for p in parole:
		# print p
		if auth:
			pps = pps.filter(Q(id_palina__icontains=p) | Q(nome__icontains=p))
			ips = ips.filter(Q(indirizzo__icontains=p) | Q(nome__icontains=p))
		rrs = rrs.filter(descrizione__icontains=p)
		if maxlength >= 3:
			pias = pias.filter(parolaindirizzoautocompl__parola__startswith=p.lower())

	# print "Fuori dal ciclo"
	rrs = rrs.order_by('-orario')[:RICERCHE_RECENTI_MAX_LENGTH]
	rrs_list = [("R%d" % u.pk, u.descrizione) for u in rrs]
	if auth:
		pps_list = [("P%d" % u.pk, u.nome) for u in pps]
		ips_list = [("I%d" % u.pk, u.nome) for u in ips]
		preferiti_list = pps_list + ips_list + rrs_list
	else:
		preferiti_list = rrs_list

	pias = pias.order_by('indirizzo')
	pias_list = [("A%d" % u.pk, u.indirizzo) for u in pias[:10]]
	return {'cerca': cerca, 'risultati': preferiti_list + pias_list}


@jsonrpc_method('servizi_get_tutti')
@group_required('operatori')
def get(request):
	"""
	Restituisce lo stato di tutti i servizi per i quali esista un servizio frontend
	
	Formato output:
	[
		{
			'pk': pk,
			'nome': nome,
			'stato': stato,
			'descrizione': descrizione del rispettivo servizio frontend,
		}
	]
	"""
	ss = ServizioFrontEnd.objects.all()
	out = []
	for sf in ss:
		s = sf.servizio
		out.append({
			'pk': s.pk,
			'nome': s.nome,
			'descrizione': sf.descrizione,
			'stato': s.abilitato,
		})
	return out



@jsonrpc_method('servizi_set_servizio')
@group_required('operatori')
def servizi_set_servizio(request, pk, stato):
	"""
	Imposta lo stato del servizio
	"""
	s = Servizio.objects.get(pk=pk)
	s.abilitato = stato
	s.save()

@jsonrpc_method('get_user_groups')
def get_user_groups(request):
	"""
	Restituisce i nomi dei gruppi dell'utente autenticato
	"""
	if request.user is None:
		return ''
	return [g.name for g in request.user.groups.all()]


def _servizi_app_init(request, session_or_token, urlparams):
	"""
	Inizializzazione app: recupera la sessione e restituisce info su utente e parametri.

	session_or_token è il token_app (persistente) per gli utenti registrati, oppure una chiave di sessione (temporanea)
	Se session_or_token vale '', utilizza i cookie per recuperare la sessione.
	Se session_or_token vale '-', effettua il logout e crea una nuova sessione
	"""
	out = {}

	old_user = request.user

	print "Input session key:", session_or_token

	# Logout and clear session
	if session_or_token == '-':
		logout(request)
		out['session_key'] = request.session.session_key
	# Restore session, if any
	elif session_or_token == '':
		# La sessione è stata aperta implicitamente (tramite cookie). Se l'utente è autenticato,
		# rendila persistente generando un token_app
		# print "Nessun token esplicito, cerco implicitamente"
		if request.user.is_authenticated():
			# print "Autenticato, genero token"
			t = TokenApp(
				user=request.user,
				token_app=generate_key(TOKEN_APP_LENGTH),
				ultimo_accesso=datetime.now(),
			)
			t.save()
			out['session_key'] = t.token_app
		else:
			out['session_key'] = request.session.session_key
	else:
		# session_or_token passato esplicitamente, determina se è un token o una sessione
		try:
			# print "Cerco token esplicito"
			if len(session_or_token) == TOKEN_APP_LENGTH:
				t = TokenApp.objects.get(token_app=session_or_token)
				t.ultimo_accesso = datetime.now()
				t.user.backend='django.contrib.auth.backends.ModelBackend'
				login(request, t.user)
				out['session_key'] = session_or_token
			else:
				raise Exception()
		except:
			# traceback.print_exc()
			# print "Cerco sessione"
			try:
				request.session = session_engine.SessionStore(session_key=session_or_token)
				request.user = get_user(request)
				request.session.modified = True
			except:
				pass
				# print "Sessione non trovata"
			out['session_key'] = request.session.session_key

	# Params decode
	d = urlparse.parse_qs(urlparams)
	out['params'] = dict([(k, d[k][0]) for k in d])

	# User
	u = request.user
	if u.is_authenticated():
		out['user'] = {
			'username': u.username,
			'nome': u.first_name,
			'cognome': u.last_name,
			'email': u.email,
			'groups':[g.name for g in u.groups.all()],
		}
	else:
		out['user'] = None

	out['utente_cambiato'] = u != old_user

	# Favorites
	fav = get_fav(request)
	fav_list = [(k, fav[k][0], fav[k][1]) for k in fav]
	out['fav'] = fav_list

	# print "Output session key:", out['session_key']

	return {
		'res': out,
		'user': u,
	}


@jsonrpc_method('servizi_app_init', safe=True)
def servizi_app_init(request, session_or_token, urlparams):
	risposta = _servizi_app_init(request, session_or_token, urlparams)
	return risposta['res']


@jsonrpc_method('servizi_app_init_2', safe=True)
def servizi_app_init_2(request, opzioni, urlparams):
	session_or_token = opzioni['session_or_token']
	risposta = _servizi_app_init(request, session_or_token, urlparams)
	res = risposta['res']
	if 'os' in opzioni:
		os = opzioni['os']
	else:
		os = None
	try:
		v = VersioneApp.objects.get(versione=opzioni['versione'], os=os)
	except VersioneApp.DoesNotExist:
		v = VersioneApp.objects.get(versione=opzioni['versione'], os=None)
	res['deprecata'] = False
	res['aggiornamento'] = False
	res['messaggio_custom'] = v.messaggio_custom
	n = datetime.now()
	if v.orario_deprecata is not None and v.orario_deprecata <= n:
		res['deprecata'] = True
	elif len(VersioneApp.objects.filter(Q(os=None) | Q(os=os), beta=False, orario_rilascio__gt=v.orario_rilascio, orario_rilascio__lt=n)) > 0:
		res['aggiornamento'] = True
	u = risposta['user']
	if not u.is_authenticated():
		u = None
	l = LogAppInit(
		orario=n,
		versione=v,
		session_key=res['session_key'],
		user=u,
	)
	# l.save()
	return res


@jsonrpc_method('servizi_app_login', safe=True)
def app_login(request, temp_token):
	try:
		ut = UrllibTransport()
		server = xmlrpclib.ServerProxy(login_ws_url, transport=ut)
		resp = server.GetUser(temp_token, login_app_id_sito, password_sito)
		u = authenticate(user_data=resp)
		if u is not None:
			if u.is_active:
				login(request, u)
				carpooling.verifica_abilitazione_utente(u)
			return 'OK'
	except Exception, e:
		pass
	return 'KO'

@jsonrpc_method('servizi_delete_fav', safe=True)
def servizi_delete_fav(request, pk):
	delete_fav(request, pk)
	return 'OK'