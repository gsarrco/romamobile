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
from django.template.response import TemplateResponse
from log_servizi.models import ServerVersione
import errors
from utils import dict_cursor, project, messaggio, populate_form, hist_redirect, giorni_settimana
from utils import AtacMobileForm, permission_links, restore_login_params
import uuid
import hashlib
import datetime
import gettext
from news import models as news
from xhtml import middleware
from xmlrpclib import Server
from urllib_transport import *
from django.contrib import auth
from django.http import HttpResponseRedirect
from django.contrib.auth import login, authenticate
from xhtml.middleware import get_back_url
from django import forms
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext as _
import django.contrib.auth.views
from django.db.models import Q
from django.template.defaultfilters import date as datefilter, urlencode
from percorso.views import _validate_address, calcola_percorso_dinamico
from paline.views import _default
from paline.models import PalinaPreferita #, PercorsoSalvato
from percorso.models import IndirizzoPreferito
import settings
from carpooling import models as carpooling
from pprint import pprint
from mercury.models import Mercury
from autenticazione.models import Sottosito

from django.views.defaults import page_not_found, server_error

login_ws_url = ''
login_url = 'http://login.muoversiaroma.it/Login.aspx?IdSito=%d' % settings.ID_SITO
logout_url = 'http://login.muoversiaroma.it/Logout.aspx?IdSito=%d' % settings.ID_SITO
password_sito = ''
login_app_id_sito = 13

gettext.bindtextdomain('views', 'locale')

servizi3 = ServerVersione("servizi", 3)

def get_translator(lang):
	t = gettext.translation('views', 'servizi/locale', [lang], fallback=True)
	return t.gettext
			
servicesToHide = {
	'en': {
		'news': True,
	},
}
def serviceHidden(service, lang):
	return (lang in servicesToHide) and (service in servicesToHide[lang]) and (servicesToHide[lang][service] == True)


@servizi3.metodo('Stato')
def stato(request, token, prodotto, lingua):
	
	try:
		servizi = ServizioLingua.objects.filter(lingua__codice=lingua).order_by('servizio__ordine')
	except ServizioLingua.DoesNotExist:
		raise errors.XMLRPC['XRE_DB']
	
	ret = []

	for s in servizi:
		ret.append({
			'servizio': s.servizio.servizio.nome,
			'visibile': int(not s.get_nascosto()),
			'attivo': int(s.get_attivo())
		})
	
	return ret

@servizi3.metodo('Menu')
def menu(request, token, prodotto, lingua):
	
	try:
		servizi = ServizioLingua.objects.filter(lingua__codice=lingua).order_by('servizio__ordine')
	except ServizioLingua.DoesNotExists:
		raise errors.XMLRPC['XRE_DB']
	
	ret = []

	for s in servizi:
		ret.append({
			'nome': s.descrizione,
			'servizio': s.servizio.servizio.nome,
		})
		
	return ret


@servizi3.metodo('Utente')
def info_utente(request, token):
	u = request.user
	fav = get_fav(request)
	fav_list = [(k, fav[k][0], fav[k][1]) for k in fav]
	fav_list.sort(key=lambda x: x[2])	
	if u.is_authenticated():
		return {
			'user': {
				'username': u.username,
				'nome': u.first_name,
				'cognome': u.last_name,
				'email': u.email,
			},
			'fav': fav_list,
		}
	else:
		return {
			'fav': fav_list,
		}
		
@servizi3.metodo('LoginApp')
def login_app(request, dummy, temp_token):
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



@servizi3.metodo("Servizio")
def servizio(request, token, prodotto, servizio, lingua, apertoDalMenu):
	
	try:
		s = ServizioLingua.objects.get(lingua__codice=lingua, servizio__servizio__nome=servizio)
	except ServizioLingua.DoesNotExist:
		raise errors.XMLRPC['XRE_DB']
	
	ret = []

	return {
		'nome': s.descrizione,
		'servizio': s.servizio.servizio.nome,
	}
		

def from_fav(request, fav):
	t, pk = fav[0], int(fav[1:])
	if t == 'R':
		rrs = RicercaRecente.get_queryset_by_request(request)
		return rrs.get(pk=pk).ricerca
	elif t == 'P':
		p = PalinaPreferita.objects.get(gruppo__user=request.user, gruppo__singleton=True, pk=pk)
		return 'fermata:%s' % p.id_palina
	elif t == 'I':
		p = IndirizzoPreferito.objects.get(user=request.user, pk=pk)
		return p.indirizzo_composito()
		
	
def get_fav(request):
	u = request.user
	fav = {}
	if u.is_authenticated():
		fav.update(dict([('fermata:%s' % p.id_palina, ('P%d' % p.pk, p.nome)) for p in PalinaPreferita.objects.filter(gruppo__user=u, gruppo__singleton=True)]))
		fav.update(dict([(i.indirizzo_composito(), ('I%d' % i.pk, i.nome)) for i in IndirizzoPreferito.objects.filter(user=u)]))
	
	rrs = RicercaRecente.by_request(request)
	fav.update(dict([(r.ricerca, ("R%d" % r.pk, r.descrizione)) for r in rrs]))

	return fav
	


def servizi_new(request):
	ctx = {}
	servizi_pubblico = ['news', 'risorse', 'bike', 'carpooling', 'paline', 'percorso']
	servizi_privato = ['news', 'ztl', 'bollettino', 'tempi', 'parcheggi', 'telecamere']
	servizi_altro = ['lingua', 'contatti']
		
	# se lo sfondo non e' impostato, lo imposta a scuro
	if 'theme' not in request.session:
		request.session['theme'] = ''

	fav = get_fav(request)
	fav_list = [fav[k] for k in fav]
	fav_list.sort(key=lambda x: x[1])	
	

	
	fav_list = [('-', _('Ricerche recenti:'))] + fav_list	


			
	class CercaForm(AtacMobileForm):
		start_address = forms.CharField(widget=forms.TextInput(attrs={'size':'24'}))
		start_fav = forms.TypedChoiceField(choices=fav_list)
		stop_address = forms.CharField(widget=forms.TextInput(attrs={'size':'24'}))
		stop_fav = forms.TypedChoiceField(choices=fav_list)
		
	f = populate_form(request, CercaForm,
		start_address='',
		stop_address='',
	)
		
	# Servizi da mostrare nel menu
	ctx['servizi_pubblico'] = [s for s in ServizioLingua.objects.filter(lingua=request.lingua, servizio__servizio__nome__in=servizi_pubblico).order_by('servizio__ordine') if s.servizio.servizio.utente_abilitato(request.user)]
	ctx['servizi_privato'] = [s for s in ServizioLingua.objects.filter(lingua=request.lingua, servizio__servizio__nome__in=servizi_privato).order_by('servizio__ordine') if s.servizio.servizio.utente_abilitato(request.user)]	
	ctx['servizi_altro'] = [s for s in ServizioLingua.objects.filter(lingua=request.lingua, servizio__servizio__nome__in=servizi_altro).order_by('servizio__ordine') if s.servizio.servizio.utente_abilitato(request.user)]
	
	# News in prima pagina
	ns = news.News.objects.filter(primo_piano=True, codice_lingua=request.lingua.codice)
	us = []
	for n in ns:
		us.append({
			'link': '/news/dettaglio/%d/%d' % (n.prima_categoria().id_categoria,  n.id_news),
			'messaggio': n.titolo,
		})
	
	
	# Percorsi salvati
	try:
		utente_generico = UtenteGenerico.by_request(request)
		#pss = PercorsoSalvato.objects.filter(utente_generico=utente_generico)
		#pas = Mercury.sync_any_static(settings.MERCURY_WEB, 'attualizza_percorsi', {'pk_percorsi': [ps.pk for ps in pss]})
	except UtenteGenerico.DoesNotExist:
		pass

	
	
	error_messages = []
	error_fields = []
		
	if f.is_bound and 'Avanzate' in request.GET:
		cd = f.data
		n = datetime.datetime.now()
		return hist_redirect(request, '/percorso?start_address=%(start)s&stop_address=%(stop)s&quando=0&wd=%(wd)d&hour=%(hour)d&minute=%(minute)d&mezzo=1&piedi=1&max_distanza_bici=5.0&bus=on&metro=on&fc=on&fr=on' % {
			'start': cd['start_address'],
			'stop': cd['stop_address'],
			'wd': n.weekday(),
			'hour': n.hour,
			'minute': (n.minute / 10) * 10,
		}, offset=0)

	
	if f.is_bound and ('Submit' in request.GET or 'Inverti' in request.GET):
		cd = f.data
		if cd['start_fav'] != '-':
			start_address = from_fav(request, cd['start_fav'])
		else:
			start_address = cd['start_address'].strip()
		if cd['stop_fav'] != '-':
			stop_address = from_fav(request, cd['stop_fav'])
		else:			
			stop_address = cd['stop_address'].strip()
		
		if 'Inverti' in request.GET:
			start_address, stop_address = stop_address, start_address		
		
		if stop_address == '':
			if start_address == '':
				f.set_error(['start_address'])
			else:
				return hist_redirect(request, '/paline/?cerca=%s' % (start_address, ), offset=0)
				# return _default(request, start_address, ctx, False)

		else:
			return hist_redirect(request, '/percorso/?start_address=%s&stop_address=%s&Submit=Cerca&bus=on&metro=on&fr=on&fc=on&mezzo=1&piedi=1&quando=0&max_distanza_bici=5' % (start_address, stop_address), offset=0)
		
	ctx['form'] = f
	middleware.set_menu_nav(request)
	return TemplateResponse(request, 'servizi_new.html', ctx)



# Autenticazione
def login_ws(request):
	ut = UrllibTransport()
	server = xmlrpclib.ServerProxy(login_ws_url, transport=ut)
	resp = server.GetUser(request.REQUEST['Token'], settings.ID_SITO, password_sito)
	u = authenticate(user_data=resp)
	if u is not None:
		if u.is_active:
			login(request, u)
			carpooling.verifica_abilitazione_utente(u)
	id = None
	if 'login_id_sub_sito' in request.session:
		id = request.session['login_id_sub_sito']
		request.session['login_id_sub_sito'] = None
	if id is None:
		path = restore_login_params(request)
		if path is not None:
			return HttpResponseRedirect(path)
		return HttpResponseRedirect(get_back_url(request, len(request.session['history']) - 1))
	ss = Sottosito.objects.get(id_sottosito=id)
	return HttpResponseRedirect(ss.url_login)

def login_page(request):
	id = None
	if 'IdSubSito' in request.GET:
		id = request.GET['IdSubSito']
	request.session['login_id_sub_sito'] = id
	return HttpResponseRedirect(login_url)

def login_app_landing(request):
	return messaggio(request, _("Accesso effettuato"))

def logout(request):
	auth.logout(request)
	id = None
	if 'IdSubSito' in request.GET:
		id = request.GET['IdSubSito']
	request.session['login_id_sub_sito'] = id	
	return HttpResponseRedirect(logout_url)

def logout_return(request):
	id = None
	if 'login_id_sub_sito' in request.session:
		id = request.session['login_id_sub_sito']
		request.session['login_id_sub_sito'] = None
	if id is None:
		return HttpResponseRedirect('/')
	ss = Sottosito.objects.get(id_sottosito=id)	
	return HttpResponseRedirect(ss.url_logout)

def backend(request):
	ctx = {}
	if not request.user.is_authenticated():
		return django.contrib.auth.views.login(request)
	menu = [{
			'url': '/js/index.html',
			'caption': 'Backend di gestione di Muoversiaroma mobile',
			'groups': ['operatori', 'utt'],
		},
		{
			'url': '/carpooling/abilitamanager',
			'caption': 'Abilita mobility manager Car Pooling',
			'groups': ['operatori'],
		},
		{
			'url': '/paline/carica_rete',
			'caption': 'Caricamento rete',
			'groups': ['carica_rete'],
		}, {
			'url': '/tempi/rapporti_diagnostica_telecamere',
			'caption': 'Consultazione rapporti telecamere UTT',
			'groups': ['utt_read'],
		}, {
			'url': '/backend/password/change',
			'caption': 'Cambia password',
			'groups': ['carica_rete', 'operatori', 'utt_read', 'utt', 'utt_admin'],
		}, {
			'url': '/doc/s/index.html',
			'caption': 'Documentazione',
			'groups': ['doc'],		
		}, {			
			'url': '/backend/logout',
			'caption': 'Logout',
			'groups': ['carica_rete', 'operatori', 'utt_read', 'utt', 'utt_admin', 'doc'],
		},	
	]
	redirect, menu = permission_links(request.user, menu)
	if redirect is not None:
		return HttpResponseRedirect(redirect)
	ctx['menu'] = menu
	print menu
	return TemplateResponse(request, 'backend.html', ctx)

def backend_logout(request):
	auth.logout(request)
	return HttpResponseRedirect('/backend')

# Notifiche
def notifiche_fasce(request, id_notifica):
	class FasciaForm(AtacMobileForm):
		ora_inizio = forms.TimeField(widget=forms.TextInput(attrs={'size':'5'}))
		ora_fine = forms.TimeField(widget=forms.TextInput(attrs={'size':'5'}))

		def __init__(self, *args, **kwargs):
			super(FasciaForm, self).__init__(*args, **kwargs)
			for i in range(0, 7):
				self.fields['giorno%d' % i] = forms.BooleanField(required=False)

		def giorni(self):
			out = []
			giorni = giorni_settimana()
			for i in range(0, 7):
				out.append(unicode(self["giorno%d" % i]) + " " + giorni[i].capitalize() )
			return mark_safe('<br />'.join(out))

	ctx = {}
	giorni = {}
	try:
		rn = RichiestaNotifica.objects.get(pk=id_notifica, user=request.user)
	except RichiestaNotifica.DoesNotExist:
		return messaggio(request, _("La notifica non esiste"))
	ctx['fasce'] = rn.fasce.all()
	for i in range(0, 6):
		giorni['giorno%d' % i] = i <= 4
	f = populate_form(
		request,
		FasciaForm,
		ora_inizio='07:00',
		ora_fine='09:00',
		**giorni
	)
	if f.is_valid():
		cd = f.cleaned_data
		giorni = {}
		frn = FasciaRichiestaNotifica(
			con_fasce=rn,
			ora_inizio=cd['ora_inizio'],
			ora_fine=cd['ora_fine'],
			giorni="".join([str(i) for i in range(0, 7) if cd['giorno%d' % i]])
		)
		frn.save()
		return hist_redirect(request, '/servizi/notifiche/fasce/%s' % id_notifica, msg=(u"Fascia oraria impostata"))
	ctx['form'] = f
	return TemplateResponse(request, 'notifiche_fasce.html', ctx)

def notifiche_fasce_elimina(request, id):
	try:
		f = FasciaRichiestaNotifica.objects.get(con_fasce__user=request.user, pk=id)
		id_notifica = f.con_fasce.pk
		f.delete()
		return hist_redirect(request, '/servizi/notifiche/fasce/%d' % id_notifica, msg=(u"Fascia oraria eliminata"))
	except FasciaRichiestaNotifica.DoesNotExist: 
		return messaggio(request, _("La fascia non esiste"))

def notifiche(request, pk):
	try:
		n = RichiestaNotifica.objects.get(user=request.user, pk=pk)
		n.nascosta = True
		n.save()
		return hist_redirect(request, n.downcast().get_url())
	except FasciaRichiestaNotifica.DoesNotExist: 
		return messaggio(request, _("La notifica non esiste"))
	

def tema(request):
	try:
		if request.session['theme'] == '':
			request.session['theme'] = '-light'
		else:
			request.session['theme'] = ''
	except:
		request.session['theme'] = '-light'
	return HttpResponseRedirect('/')