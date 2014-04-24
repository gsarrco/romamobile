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
from servizi.utils import dict_cursor, project, datetime2mysql, group_required, autodump
from servizi.utils import model2contenttype
from servizi import infopoint
from servizi.models import Luogo
from parcheggi import models as parcheggi
from mercury.models import Mercury
from risorse import models as risorse
from datetime import datetime, timedelta, time, date
from pannelli import backviews as pannellibw
from django.template.defaultfilters import date as datefilter, urlencode
from jsonrpc import jsonrpc_method
import rpyc
import cPickle as pickle
import gmaps
import views
from paline.views import paline7, _dettaglio_paline
from pprint import pprint
from percorso.views import infopoint_to_cp
from django.utils import translation
from servizi.views import get_fav
import logging
import settings


@jsonrpc_method('palinePercorsoMappa', safe=True)
def percorso_mappa(request, id_percorso, *args, **kwargs):
	c = Mercury.rpyc_connect_any_static(settings.MERCURY_WEB)
	out = pickle.loads(c.root.percorso_su_mappa_special(id_percorso, '/paline/s/img/'))
	return out

@jsonrpc_method('paline_percorso_fermate', safe=True)
def percorso_fermate(request, id_percorso, id_veicolo, lang):
	p = Percorso.objects.by_date().get(id_percorso=id_percorso)
	fs = Fermata.objects.by_date().filter(percorso=p).order_by('progressiva')
	# ps = []
	# for fr in fs:
	# 	f = fr.palina
	# 	if not f.soppressa:
	# 		ps.append({
	# 			'id_palina': f.id_palina,
	# 			'nome': f.nome_ricapitalizzato(),
	# 		})
	translation.activate(lang)
	giorni = []
	t = date.today()
	for i in range(7):
		giorni.append({
			'giorno': t.strftime('%Y-%m-%d'),
			'nome': datefilter(t, "l j F").capitalize(),
		})
		t += timedelta(days=1)

	percorso = views._percorso(request, id_percorso, id_veicolo=id_veicolo, as_service=True)

	return {
		'fermate': percorso['fermate'],
		'giorni': giorni,
		'id_percorso': id_percorso,
		'percorso': percorso['percorso'],
		'percorsi':  percorso['percorsi'],
	}
	
@jsonrpc_method('paline_orari', safe=True)
def percorso_orari(request, id_percorso, data, lang):
	translation.activate(lang)
	orari = views.trovalinea_orari(None, '', id_percorso, data)
	#print orari 
	return orari


@jsonrpc_method('stato_traffico', safe=True)
def stato_traffico(request, verso):
	if verso == 'out':
		percorsi = ['13116', '53771', '2598', '502A', '11436', '11592', '52300', '766A', '2039', '12115', '7288', '53422', '53670', '53861', '52596', '53489', '11574', '53715', '53762', '53776', '50744', '10273', '50329', '53554', '51668', '13085', '50499', '53466', '50046', '52265', '701A', '52968', '51828']
	else:
		percorsi = ['50595', '53770', '2597', '502R', '52632', '11591', '218R', '5404', '2038', '12118', '7287', '53423', '53671', '53860', '52597', '53488', '11573', '53864', '53763', '53778', '51379', '10274', '50594', '53553', '50963', '13084', '50065', '53464', '50047', '808A', '701R', '52969', '51829']
	
	c = Mercury.rpyc_connect_any_static(settings.MERCURY_WEB)

	mappa = {
		'markers': [],
		'polylines': [],
		'sublayers': [],
	}
	
	for id_percorso in percorsi:
		try:
			m = pickle.loads(c.root.percorso_su_mappa(id_percorso, None, '/paline/s/img/', con_stato=True, con_fermate=False, con_bus=False))
			mappa['markers'].extend(m['markers'])
			mappa['polylines'].extend(m['polylines'])
			mappa['sublayers'].append(('traffico_bus', id_percorso))			
		except Exception, e:
			logging.error("Mappa centrale: Errore percorso %s" % id_percorso)
			
	out = {
		'mappa': mappa,
	}
	
	return out	
	
@jsonrpc_method('mappa_layer', safe=True)
def mappa_layer(request, nome, lang):
	#pprint(nome)
	translation.activate(lang)
	tipo = nome[0]
	id = nome[1]
	c = Mercury.rpyc_connect_any_static(settings.MERCURY_WEB)
	
	if tipo == 'traffico_bus':
		out = pickle.loads(c.root.percorso_su_mappa(id, None, '/paline/s/img/', con_stato=True, con_fermate=False, con_percorso=False, con_bus=False))
		out['refresh'] = 2 * 60
		
	if tipo == 'traffico_bus_tiny':
		out = pickle.loads(c.root.percorso_su_mappa(id, None, '/paline/s/img/', con_stato=True, con_fermate=False, con_percorso=False, con_bus=False, fattore_thickness=0.5))
		out['refresh'] = 2 * 60		
		
	elif tipo == 'palina':
		return views.trovalinea_veicoli_locale(request, *id)
	
	elif tipo == 'palina-singola':
		palina = Palina.objects.by_date().get(id_palina=id)
		out = pickle.loads(c.root.palina_su_mappa(id, None, '/paline/s/img/'))
		out['descrizione'] = u"%s (%s)" % (palina.nome_ricapitalizzato(), palina.id_palina)
	
	elif tipo == 'posizione_bus':
		out = pickle.loads(c.root.percorso_su_mappa(id, None, '/paline/s/img/', con_stato=False, con_fermate=False, con_percorso=False, con_bus=False, con_bus_immediato=True))
		out['refresh'] = 30
		
	elif tipo == 'arrivi_veicolo':
		p = Percorso.objects.by_date().get(id_percorso=id[1])
		vs = p.get_veicoli(True, id[0])
		out = ''
		if len(vs) > 0:
			out = vs[0]['infobox']
	
	elif tipo == 'percorso':
		p = Percorso.objects.by_date().get(id_percorso=id)
		out = pickle.loads(c.root.percorso_su_mappa(id, None, '/paline/s/img/', con_stato=False, con_bus=False, con_fermate=True))
		out['sublayers'] = [
			('traffico_bus', id),
			('posizione_bus', id),
		]
		out['descrizione'] = p.getNomeCompleto()
		
	elif tipo == 'percorso_tiny':
		p = Percorso.objects.by_date().get(id_percorso=id)
		out = pickle.loads(c.root.percorso_su_mappa(id, None, '/paline/s/img/', con_stato=False, con_bus=False, con_fermate=False, fattore_thickness=0.3))
		out['sublayers'] = [
			('traffico_bus_tiny', id),
			('posizione_bus', id),
		]
		out['descrizione'] = p.getNomeCompleto()
		
	elif tipo == 'risorsa':
		print "Cerco una risorsa"
		pprint(id)
		address = id[0]
		tipi_ris = id[1]
		start = infopoint_to_cp(request, address)
		if start['stato'] != 'OK':
			out = {'errore': start}
		else:
			max_distanza = id[2]
			max_distanza = 2000
			out = pickle.loads(c.root.risorse_vicine(start, tipi_ris, 5, max_distanza))
			out['descrizione'] = 'Luoghi trovati'

	elif tipo == 'pannelli':
		out = pannellibw.mappa_layer(request, nome)
	
	# pprint(out)
	return out


@jsonrpc_method('paline_smart_search', safe=True)
def paline_smart_search(request, query, lang):
	translation.activate(lang)
	#print "Smart"
	ctx = {
		'errore': False,
		'tipo': '',
		'id_palina': '',
		'indirizzi': [],
		'paline_semplice': [],
		'paline_extra': [],
		'percorsi': [], 	
	}
	out = views._default(request, query, ctx, True)
	# pprint(out)
	return out

@paline7.metodo("Mappa")
def ws_mappa(request, token, tipo, id):
	return mappa_layer(request, (tipo, id), 'it')

@jsonrpc_method('paline_previsioni', safe=True)
def previsioni(request, id_palina, lingua):
	translation.activate(lingua)
	try:
		p = Palina.objects.by_date().get(id_palina=id_palina)
	except:
		raise errors.XMLRPC['XRE_NO_ID_PALINA']
	prev = _dettaglio_paline(request, p.nome, [p], aggiungi=p.id_palina, as_service=True)
	prev['collocazione'] = p.descrizione
	if request.user.is_authenticated():
		preferito = PalinaPreferita.objects.filter(gruppo__user=request.user, id_palina=id_palina).count() > 0
	else:
		preferito = False
	prev['esiste_preferito'] = preferito
	return prev

@jsonrpc_method('paline_previsioni', safe=True)
def previsioni(request, id_palina, lingua):
	translation.activate(lingua)
	try:
		p = Palina.objects.by_date().get(id_palina=id_palina)
	except:
		raise errors.XMLRPC['XRE_NO_ID_PALINA']
	prev = _dettaglio_paline(request, p.nome, [p], aggiungi=p.id_palina, as_service=True)
	prev['collocazione'] = p.descrizione
	if request.user.is_authenticated():
		preferito = PalinaPreferita.objects.filter(gruppo__user=request.user, id_palina=id_palina).count() > 0
	else:
		preferito = False
	prev['esiste_preferito'] = preferito
	return prev

@jsonrpc_method('paline_preferiti', safe=True)
def preferiti(request, tipo, nome, descrizione, esiste):
	out = {}
	if esiste:
		g = GruppoPalinePreferite(user=request.user, nome=descrizione, singleton=True)
		g.save()
		p = PalinaPreferita(id_palina=nome, nome=descrizione, gruppo=g)
		p.save()
	else:
		p = PalinaPreferita.objects.filter(gruppo__user=request.user, id_palina=nome)[0]
		g = p.gruppo
		if g.palinapreferita_set.count() == 1:
			g.delete()
		else:
			p.delete()

	# Get new favorites
	fav = get_fav(request)
	fav_list = [(k, fav[k][0], fav[k][1]) for k in fav]
	fav_list.sort(key=lambda x: x[2])
	out['fav'] = fav_list

	return out
