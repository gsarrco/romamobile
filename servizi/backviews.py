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
from paline.models import IndirizzoAutocompl, ParolaIndirizzoAutocompl, PalinaPreferita
from percorso.models import IndirizzoPreferito
from servizi.utils import dict_cursor, project, datetime2mysql, group_required
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


@jsonrpc_method('servizi_app_init', safe=True)
def servizi_app_init(request, session_key, urlparams):
	"""
	Inizializzazione app: recupera la sessione e restituisce info su utente e parametri.

	Se session_key vale '', utilizza i cookie per recuperare la sessione.
	Se session_key vale '-', effettua il logout e crea una nuova sessione
	"""
	out = {}

	# print "Input session key:", session_key

	# Logout and clear session
	if session_key == '-':
		logout(request)
	# Restore session, if any
	elif False: #session_key != '': # TODO: aggiornato il client, ripristinare
		try:
			request.session = session_engine.SessionStore(session_key=session_key)
			request.user = get_user(request)
		except:
			pass

	request.session.modified = True
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

	# Favorites
	fav = get_fav(request)
	fav_list = [(k, fav[k][0], fav[k][1]) for k in fav]
	out['fav'] = fav_list

	# print "Output session key:", out['session_key']

	return out

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