# coding: utf-8

#
#    Copyright 2013 Roma servizi per la mobilità srl
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
from servizi.utils import dict_cursor, project, datetime2mysql, group_required
from datetime import datetime, timedelta, time, date
from jsonrpc import jsonrpc_method
from urllib_transport import *
import xmlrpclib
import settings
login_ws_url = 'http://login.muoversiaroma.it/Handler.ashx'
logout_url = 'http://login.muoversiaroma.it/Logout.aspx?IdSito=%d' % settings.ID_SITO
password_sito = ''
from django.contrib.auth import login, authenticate
from django.contrib import auth

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
def set(request, pk, stato):
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
