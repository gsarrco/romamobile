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

from pyjamas.ui.FocusListener import FocusHandler
from pyjamas.ui.RootPanel import RootPanel
from pyjamas.ui.ScrollPanel import ScrollPanel
from pyjamas.ui.VerticalPanel import VerticalPanel
from pyjamas.ui.HorizontalPanel import HorizontalPanel
from pyjamas.ui.VerticalSplitPanel import VerticalSplitPanel
from pyjamas.ui.SimplePanel import SimplePanel
from pyjamas.ui.FlowPanel import FlowPanel
from pyjamas.ui.DisclosurePanel import DisclosurePanel
from pyjamas.ui.TabPanel import TabPanel
from pyjamas.ui.Grid import Grid
from pyjamas.ui.Frame import Frame
from pyjamas.ui.TextBox import TextBox
from pyjamas.ui.TextArea import TextArea
from pyjamas.ui.HTML import HTML
from pyjamas.ui.HTMLPanel import HTMLPanel
from pyjamas.ui.Anchor import Anchor
from pyjamas.ui.Label import Label
from pyjamas.ui.CheckBox import CheckBox
from pyjamas.ui.ListBox import ListBox
from pyjamas.ui.Button import Button
from pyjamas.ui.RadioButton import RadioButton
from pyjamas.ui.PopupPanel import PopupPanel
from pyjamas.ui.KeyboardListener import KeyboardHandler
from pyjamas.ui.Tree import Tree, TreeItem
from pyjamas.ui.Image import Image
from pyjamas.ui import HasAlignment
from pyjamas.ui.MenuBar import MenuBar
from pyjamas.ui.MenuItem import MenuItem
from pyjamas.ui.Widget import Widget
from pyjamas.ui.Hyperlink import Hyperlink
from pyjamas import Window
from pyjamas.Timer import Timer
from pyjamas.JSONService import JSONProxy
from pyjamas import History
from pyjamas import DOM
from prnt import prnt
from util import StyledFixedColumnFlexTable, HTMLFlowPanel, DP, VP, HP, GP, SP, DeferrablePanel, DeferrableTabPanel, \
	storage_get, storage_set, ScrollAdaptivePanel, QuestionDialogBox
from util import get_checked_radio, HidingPanel, MyAnchor, LoadingButton, SearchBox, setAttribute
from util import wait_init, wait_start, wait_stop, _, set_lang, get_lang, MenuPanel, GeneralMenuPanel
from datetime import date, time, datetime, timedelta
from Calendar import Calendar, DateField, TimeField
from map import MapPanel, Layer, LayerPanel, get_location
from cerca_percorso import CercaPercorsoPanel
from cerca_linea import CercaLineaPanel
from cerca_luogo import CercaLuogoPanel
from news import NewsPanel
from globals import base_url, make_absolute, flavor, set_user, set_control, ios
from __pyjamas__ import JS

from DissolvingPopup import DissolvingPopup
from util import JsonHandler, redirect

client = JSONProxy(base_url + '/json/', [
	'paline_percorso',
	'servizi_autocompleta_indirizzo',
	'paline_smart_search',
	'servizi_app_init',
	'servizi_app_login',
	'servizi_delete_fav',
	'lingua_set',
])


class SearchMapPanel(VerticalPanel, KeyboardHandler, FocusHandler, DeferrablePanel):
	def __init__(self, owner, map):
		VerticalPanel.__init__(self)
		DeferrablePanel.__init__(self, deferred_interval=200)
		self.owner = owner
		self.base = VP(
			self,
			[
				{
					'class': HP,
					'style': 'over-map-hp',
					'sub': [
						{
							'class': HP,
							'width': '70%',
							'sub': [
								{
									'class': Image,
									'name': 'localizza',
									'args': ['gps.png'],
									'width': '25px',
									'height': None,
									'vertical_alignment': HasAlignment.ALIGN_MIDDLE,
								},
								{
										'class': SearchBox,
										'name': 'query',
										'call_addKeyboardListener': ([self], {}),
										'args': [client.servizi_autocompleta_indirizzo, None, 0, 100, False],
										'style': 'over-map',
								},
								{
									'class': HP,
									'call_setVisible': ([False], {}),
									'name': 'query_list_holder',
									'sub': [
										{
											'class': ListBox,
											'name': 'query_list',
											'width': '100%',
											'style': 'over-map',
										},
										{
											'class': Button,
											'args': ['X', self.onChiudiQuery],
											'width': '40px',
											'style': 'over-map close-button',
										},
									]
								},
							],
						},
						{
							'class': LoadingButton,
							'args': [_('Cerca'), self.onCerca],
							'width': '30%',
							'name': 'button',
							'style': 'over-map',
						},
					]
				},
			],
			add_to_owner=True,
		)
		self.base.addStyleName('search-floating')
		self.base.setWidth('460px')
		# JS("""if(localStorage && localStorage.nascondiHelp == '1') {self.onChiudiHelp();}""")
		self.map = map
		self.map.setSize('100%', '100%')
		self.add(map)
		self.setCellHeight(self.map, '100%')
		self.base.by_name('localizza').addClickListener(self.onLocalizza)
		self.bottom = SimplePanel()
		self.add(self.bottom)
		self.preferiti = None
		setAttribute(self.base.by_name('query'), 'placeholder', _("Linea, fermata o indirizzo"))
		setAttribute(self.base.by_name('localizza'), 'title', _("Imposta posizione corrente"))

	def do_or_defer(self, o, *args, **kwargs):
		if not self.owner.small:
			o(*args, **kwargs)
		else:
			DeferrablePanel.do_or_defer(self, o, *args, **kwargs)


	def setBottomWidget(self, w=None):
		if w is None:
			self.bottom.clear()
		else:
			self.bottom.setWidget(w)
		self.map.relayout

	def onLocalizza(self):
		self.owner.localizza()

	def getWidgets(self):
		x = self.base.by_name('query')
		x_list = self.base.by_name('query_list')
		x_holder = self.base.by_name('query_list_holder')
		return x, x_list, x_holder

	def ripristinaWidgets(self):
		for x, x_list, x_holder in [self.getWidgets()]:
			x.removeStyleName('validation-error')
			if not x.getVisible():
				x.setText(x_list.getSelectedItemText()[0])
				x_holder.setVisible(False)
				x.setVisible(True)

	def onCerca(self):
		self.owner.setDirty()
		self.ripristinaWidgets()
		q = self.base.by_name('query')
		pk = q.pk
		if pk != -1 and not str(pk).startswith('A'):
			s = 'fav:' + pk
		else:
			s = q.getText()
		self.cercaLinea(s)

	def onCercaDone(self, res):
		self.base.by_name('button').stop()
		if res['errore']:
			self.onCercaErrore(res)
			return

		tipo = res['tipo']
		if tipo == 'Indirizzo ambiguo':
			self.onCercaErrore(res)

		self.owner.cerca_linea.onCercaDone(res, True)

	def cercaLinea(self, query, ):
		self.base.by_name('button').start()
		client.paline_smart_search(query, get_lang(), JsonHandler(self.onCercaDone))

	def onCercaErrore(self, el):
		x, x_list, x_holder = self.getWidgets()
		if el['tipo'] == 'Indirizzo ambiguo':
			x.setVisible(False)
			x_holder.setVisible(True)
			x_list.addStyleName('validation-error')
			x_list.clear()
			for i in el['indirizzi']:
				x_list.addItem(i)
		else:
			x.addStyleName('validation-error')


	def onChiudiQuery(self):
		x, x_list, x_holder = self.getWidgets()
		x_holder.setVisible(False)
		x.setVisible(True)

	def onChange(self, el):
		el.removeStyleName('validation-error')

	def onKeyDown(self, sender, keycode, modifiers):
		if keycode == 13:
			self.onCerca()

	def onTabSelected(self):
		self.owner.map.relayout()

	def setSmallLayout(self):
		self.base.setWidth('100%')
		self.base.removeStyleName('search-floating')
		self.base.addStyleName('search-fixed')

	def setLargeLayout(self):
		self.base.setWidth('460px')
		self.base.removeStyleName('search-fixed')
		self.base.addStyleName('search-floating')

class PreferitiPanel(SimplePanel, DeferrablePanel):
	def __init__(self, owner):
		SimplePanel.__init__(self)
		DeferrablePanel.__init__(self, owner)
		self.owner = owner
		self.menu = None

	def aggiorna_preferiti(self):
		d = [
			{
				'id': p[1],
				'text': p[2],
				'listener': self.onPreferitoClick,
				'action_listener': self.onPreferitoDelete,
				'action_icon': 'close.png',
			} for p in self.owner.preferiti
		]
		self.menu = MenuPanel(self.owner, d, title=None)
		self.setWidget(self.menu)

	def onPreferitoClick(self, mpi):
		query = self.owner.map_tab.base.by_name('query')
		query.setText(mpi.text)
		query.pk = mpi.id
		self.owner.setTabMappa()
		self.owner.map_tab.onCerca()

	def onPreferitoDeleteDone(self, res):
		pass

	def onPreferitoDeleteConferma(self, mpi):
		def f():
			mpi.setVisible(False)
			client.servizi_delete_fav(mpi.id, JsonHandler(self.onPreferitoDeleteDone))
		return f

	def onPreferitoDelete(self, mpi):
		QuestionDialogBox(_("Conferma"), _("Vuoi cancellare il preferito?"), [(_("S&igrave;"), self.onPreferitoDeleteConferma(mpi), None), (_("No"), None, None)]).show()



class ControlPanel(GeneralMenuPanel):
	def __init__(self, owner):
		GeneralMenuPanel.__init__(self)
		set_control(self)
		self.owner = owner
		self.user = None
		self.dirty = False
		self.small = False
		self.posizione = None
		self.preferiti = None

		self.tab_holder = VerticalPanel()
		self.tab_holder.setSize('100%', '100%')
		self.setMainPanel(self.tab_holder)
		
		self.tab = DeferrableTabPanel(self)
		self.tab.setSize('100%', '100%')
		self.tab_holder.add(self.tab)
		self.tab_holder.setCellHeight(self.tab, '100%')
		p = DOM.getParent(self.tab.getElement())
		DOM.setStyleAttribute(p, 'overflow-x', 'hidden')

		self.cerca_percorso = CercaPercorsoPanel(self)
		#self.tab.add(self.cerca_percorso, HTML(_("Percorso")))
		self.tab.add(self.cerca_percorso, Image(_('toolbar/percorso.png'), Width='48px', Height='48px'))
		self.tab.selectTab(0)
		
		self.cerca_linea = CercaLineaPanel(self)
		self.cerca_linea.setSize('100%', '100%')
		self.tab.add(self.cerca_linea,Image(_('toolbar/linea.png'), Width='48px', Height='48px'))
			
		self.cerca_luogo = CercaLuogoPanel(self)
		self.cerca_luogo.setSize('100%', '100%')
		self.tab.add(self.cerca_luogo, Image(_('toolbar/luogo.png'), Width='48px', Height='48px'))

		self.preferiti_tab = PreferitiPanel(self)
		self.preferiti_tab.setSize('100%', '100%')
		self.tab.add(self.preferiti_tab, Image(_('toolbar/preferiti.png'), Width='48px', Height='48px'))

		self.old_width = self.tab.getClientWidth()
		self.waiting = wait_init(self.tab_holder)
		self.mp = MenuPanel(self, [
			{
				'id': 'login',
				'text': _("Caricamento account utente"),
				'listener': self.onLogin,
			},
			{
				'id': 'news',
				'text': _("News"),
				'listener': self.onNews,
			},
			{
				'id': 'legacy',
				'text': _("Versione precedente"),
				'listener': self.onLegacy,
			},
			{
				'id': 'language',
				'text': _("Language"),
				'listener': self.onLanguage,
			},
			{
				'id': 'logout',
				'text': _("Esci"),
				'listener': self.onLogout,
			},],
			icon = 'toolbar/back.png',
		)
		self.mp.by_id('logout').setVisible(False)
		if flavor == 'app':
			self.mp.by_id('legacy').setVisible(False)
		if get_lang() != 'it':
			self.mp.by_id('news').setVisible(False)
		self.setMenuPanel(self.mp)
		self.waiting.setGeneralMenuPanel(self)

		self.map = MapPanel(self)
		self.map_tab = SearchMapPanel(self, self.map)
		self.map_tab.setSize('100%', '100%')
		self.cerca_percorso.setMap(self.map)
		self.cerca_linea.setMap(self.map)
		self.cerca_luogo.setMap(self.map)

		get_location(self.onLocation)

	def setBottomWidget(self, w=None):
		self.map_tab.setBottomWidget() #(w)

	def relayout(self):
		width = self.tab.getClientWidth()
		if (not self.small) or (width != self.old_width):
			self.old_width = width
			self.cerca_percorso.do_or_defer(self.cerca_percorso.relayout)
			self.cerca_linea.do_or_defer(self.cerca_linea.relayout)
			self.cerca_luogo.do_or_defer(self.cerca_luogo.relayout)
			# self.preferiti_tab.do_or_defer(self.preferiti_tab.relayout)
			if self.small:
				self.map_tab.do_or_defer(self.map.relayout)

	def setPreferiti(self, fav):
		self.preferiti = fav
		self.preferiti_tab.aggiorna_preferiti()

	def setDirty(self):
		self.dirty = True

	def isSmall(self):
		return self.small

	def center_and_zoom(self, layer):
		if self.small:
			self.map_tab.do_or_defer(layer.centerOnMap)
		else:
			layer.centerOnMap()
		
	def onAppInit(self, res):
		# Session
		storage_set('session_key', res['session_key'])

		# User
		self.user = res['user']
		set_user(self.user)
		if self.user is not None:
			l = self.mp.by_id('login')
			l.setText(_("Ciao, %s (Gestisci account)") % self.user['nome'])
			l.setListener(self.onGestisciAccount)
			self.mp.by_id('logout').setVisible(True)
		else:
			l = self.mp.by_id('login')
			l.setText(_("Accedi"))
			l.setListener(self.onLogin)
			self.mp.by_id('logout').setVisible(False)

		self.setPreferiti(res['fav'])

		# Parameters
		params = res['params']
		cp_params = self.cerca_percorso.availableParams()
		for p in cp_params:
			if p in params:
				self.cerca_percorso.setParam(p, params[p])
		cl_params = self.cerca_linea.availableParams()				
		for p in cl_params:
			if p in params:
				self.cerca_linea.setParam(p, params[p])
		cr_params = self.cerca_luogo.availableParams()				
		for p in cr_params:
			if p in params:
				self.cerca_luogo.setParam(p, params[p])
		if 'cl' in params and not ('query' in params or 'id_percorso' in params):
			self.tab.selectTab(1)
		if ('cr' in params or 'cr_da' in params or 'cr_lista_tipi' in params) and not 'cr_a' in params:
			self.tab.selectTab(2)

	def setTabCercaPercorso(self):
		self.tab.selectTab(0)
		if not self.small:
			self.owner.hide(False)
		
	def setTabCercaLinea(self):
		self.tab.selectTab(1)
		if not self.small:
			self.owner.hide(False)

	def setTabCercaLuogo(self):
		self.tab.selectTab(2)
		if not self.small:
			self.owner.hide(False)
		
	def setTabMappaPercorso(self):
		if self.small:
			self.tab.selectTab(4)
			self.tab.star_tab(0)
		else:
			self.tab.selectTab(0)

	def setTabPercorsoMappa(self):
		if self.small:
			self.tab.selectTab(0)
			self.tab.star_tab(4)
		else:
			self.tab.selectTab(0)
			self.owner.hide(False)
			
	def setTabMappaLinea(self):
		if self.small:
			self.tab.selectTab(4)
			self.tab.star_tab(1)
		else:
			self.tab.selectTab(1)

	def setTabLineaMappa(self):
		if self.small:
			self.tab.selectTab(1)
			self.tab.star_tab(4)
		else:
			self.tab.selectTab(1)
			self.owner.hide(False)
			
	def setTabMappaLuogo(self):
		if self.small:
			self.tab.selectTab(4)
			self.tab.star_tab(2)
		else:
			self.tab.selectTab(2)

	def setTabMappa(self):
		if self.small:
			self.tab.selectTab(4)
		
	def cercaPercorsoRisorse(self, da, tipi, a=None):
		self.setTabCercaPercorso()
		self.cerca_percorso.cercaPercorsoRisorse(da, tipi, a)

	def cercaLineaPercorso(self, id_percorso, su_mappa=False):
		if su_mappa:
			self.setTabMappaLinea()
		else:
			self.setTabLineaMappa()
		self.cerca_linea.cercaPercorso(id_percorso, su_mappa=su_mappa)
		
	def cercaLinea(self, query, su_mappa=False):
		if su_mappa:
			self.setTabMappaLinea()
		else:
			self.setTabLineaMappa()
		self.cerca_linea.cercaLinea(query, True, from_map=su_mappa)

	def localizza(self):
		self.dirty = False
		wait_start()
		get_location(self.onLocation)

	def onLocation(self, lng, lat):
		wait_stop()
		self.posizione = _('Posizione attuale <punto:(%f,%f)>') % (lat, lng)
		if not self.dirty:
			self.cerca_linea.createClLayer()
			client.paline_smart_search(self.posizione, get_lang(), JsonHandler(self.cerca_linea.onCercaDone))

	def cercaPercorsoDa(self, da):
		self.cerca_percorso.impostaDa(da)
		self.setTabCercaPercorso()

	def cercaPercorsoA(self, a):
		self.cerca_percorso.impostaA(a)
		if self.posizione is not None:
			self.cerca_percorso.impostaDa(self.posizione)
			self.cerca_percorso.cercaPercorso(su_mappa=True)
		else:
			self.setTabCercaPercorso()

	def cercaLuogo(self, luogo):
		self.cerca_luogo.cercaLuogo(luogo, set_input=True)
		self.setTabCercaLuogo()

	def onBeforeTabSelected(self, sender, index):
		return True
	
	def setSmallLayout(self):
		self.map.animation_enabled = False
		self.small = True
		self.tab.add(self.map_tab, Image(_('toolbar/mappa.png'), Width='48px', Height='48px'))
		self.map_tab.setSize('100%', '100%') #self.tab.getClientHeight())
		# self.tab.add(self.layers, "Layer")
		self.map_tab.do_or_defer(self.map.relayout)
		self.map_tab.setSmallLayout()
		self.relayout()
		self.setTabCercaPercorso()
		self.setTabCercaLinea()
		self.setTabCercaLuogo()
		self.setTabMappa()
		
	def setLargeLayout(self):
		self.small = False
		if self.tab.getTabBar().getSelectedTab() == 3: # Map
			self.setTabCercaPercorso()
		self.tab.remove(self.map_tab)
		self.map_tab.setLargeLayout()
		self.relayout()
		self.map.animation_enabled = True

	def onLoginWsDone(self, res):
		storage_set('session_key', '')
		self.restartApp()

	def loginWs(self, url, ref):
		if url.find('login_app_landing') != -1:
			JS("""ref.close();""")
			t = url.find('Token=')
			token = url[t + 6:]
			client.servizi_app_login(token, JsonHandler(self.onLoginWsDone))

	def hide(self, hide=True):
		self.owner.hide(hide)

	def onLogin(self):
		wait_start()
		if flavor == 'web':
			storage_set('session_key', '')
			Window.setLocation('/servizi/login?IdSubSito=3')
		else:
			url = 'http://login.muoversiaroma.it/Login.aspx?IdSito=13'
			JS("""
				try {
					ref = $wnd.open(url, '_blank', 'location=no');
					ref.addEventListener('loadstop', function(event) {
						self.loginWs(event.url, ref);
					});
				}
				catch (err) {
					alert("Generic error: " + err);
				}
			""")

	def onNews(self):
		news = NewsPanel(self)
		self.display_menu(alternative_menu=news)

	def onLegacy(self):
		if flavor == 'web':
			Window.setLocation('/base')

	def onLinguaSetDone(self):
		self.restartApp()

	def onLanguageSet(self, mpi):
		client.lingua_set(mpi.id, JsonHandler(self.onLinguaSetDone))
		storage_set('hl', mpi.id)
		wait_start()

	def onLanguage(self):
		lmp = MenuPanel(self, [
			{
				'id': 'it',
				'text': _("Italiano"),
				'listener': self.onLanguageSet,
			},
			{
				'id': 'en',
				'text': _("English"),
				'listener': self.onLanguageSet,
			},],
			icon='toolbar/back.png',
			title='Language',
		)
		self.display_menu(alternative_menu=lmp)


	def onLogout(self):
		if flavor == 'web':
			Window.setLocation('/servizi/logout?IdSubSito=3')
		else:
			client.servizi_app_init('-', '', JsonHandler(self.onAppInit))


	def onGestisciAccount(self):
		url = 'http://login.muoversiaroma.it/GestioneAccount.aspx'
		if flavor == 'web':
			Window.setLocation(url)
		else:
			JS("""
				try {
					$wnd.open(url, '_blank', 'location=yes');
				}
				catch (err) {
					alert("Generic error: " + err);
				}
			""")

	def restartApp(self):
		JS("""$wnd.location.reload();""")

class LeftPanel(HidingPanel):
	def __init__(self, owner):
		HidingPanel.__init__(self, False)
		self.owner = owner
		self.small = False
		self.split = VerticalSplitPanel()
		self.split.setSize('100%', '100%')
		self.split.setSplitPosition('90%')
		self.control = ControlPanel(self)
		self.control.setSize('100%', '100%')
		self.split.setTopWidget(self.control)
		self.add(self.split)
		self.layers = LayerHolder(self.control.map)
		self.split.setBottomWidget(self.layers)

	def relayout(self):
		self.control.relayout()

	def setSmallLayout(self):
		pass

	def setLargeLayout(self):
		self.split.setTopWidget(self.control)

	def updateSplitter(self):
		if not self.small:
			self.split.setSplitPosition('90%')


class LayerHolder(SimplePanel):
	def __init__(self, map):
		SimplePanel.__init__(self)
		self.setSize('100%', '100%')
		self.addStyleName('indicazioni-bg')
		
		vp = VerticalPanel()
		vp.setWidth('100%')
		vp.addStyleName('indicazioni')
		
		titolo = HTML(_('Ora presenti sulla mappa'))
		titolo.addStyleName('indicazioni-h1')
		titolo.setWidth('100%')
		vp.add(titolo)
		
		layer_panel = LayerPanel(map)
		vp.add(layer_panel)
		vp.setCellWidth(layer_panel, '100%')
		
		self.add(vp)
	

class LargeLayoutPanel(HorizontalPanel):
	def __init__(self):
		HorizontalPanel.__init__(self)
		
		# left panel
		self.left = LeftPanel(self)
		self.left.setSize('0', '100%')
		self.add(self.left)
		self.setCellHeight(self.left, '100%')
		self.control = self.left.control

		# map panel
		self.map = self.control.map
		self.search_map = self.control.map_tab
		self.add(self.search_map)
		self.setCellWidth(self.search_map, '100%')
		self.setCellHeight(self.search_map, '100%')

		# the end
		self.left.addHideListener(self.onHide)
		self.setSize("100%", "100%")

	def onHide(self, source):
		self.map.relayout()
		self.left.split.setSplitPosition('90%')
		self.left.relayout()
				
	def setSmallLayout(self):
		pass
		
	def setLargeLayout(self):
		#self.add(self.left)
		self.left.setLargeLayout()
		self.setCellHeight(self.left, '100%')
		self.add(self.search_map)
		self.setCellWidth(self.search_map, '100%')
		self.setCellHeight(self.search_map, '100%')
		self.map.relayout()

	def createMap(self):
		self.map.create_map()
		raw_params = getRawParams()
		if raw_params.find('vms=1') != -1:
			Layer(['pannelli', 0], _('Pannelli VMS'), self.map, self)

	def getControlPanel(self):
		return self.left.control

	def updateSplitter(self):
		self.left.updateSplitter()
		
def getRawParams():
	return Window.getLocation().getSearch()[1:]

class GeneralPanel(VerticalPanel):
	def __init__(self):
		VerticalPanel.__init__(self)
		raw_params = getRawParams()
		self.small = False
		self.has_header = False

		if False and raw_params.find('iframe=0') == -1:
			# header
			self.has_header = True
			self.header = HorizontalPanel()
			self.header.setSize('100%', '58px')
			self.add(self.header)
			self.setCellHeight(self.header, '58px')
			
			self.header.add(Image('logo-sx.png'))
			self.header.addStyleName('logo')
			
			self.copy = HTML('<a href="http://www.agenziamobilita.roma.it">&copy; %d Roma servizi per la mobilit&agrave; s.r.l.</a>' % datetime.now().year)
			self.copy.addStyleName('copy')
			self.header.add(self.copy)
			self.header.setCellHorizontalAlignment(self.copy, HasAlignment.ALIGN_RIGHT)

		# main
		self.llp = LargeLayoutPanel()
		self.control = self.llp.getControlPanel()

		if len(raw_params) > 0:
			self.control.setDirty()
		self.add(self.llp)
		self.setCellHeight(self.llp, '100%')
		self.setSize('100%', '100%')

	def onAppInit(self, res):
		self.control.onAppInit(res)

	def setSmallLayout(self):
		if not self.small:
			self.small = True
			if self.has_header:
				self.remove(self.header)
			self.remove(self.llp)
			self.add(self.control)
			self.control.setSmallLayout()
			self.llp.setSmallLayout()
		
	def setLargeLayout(self):
		if self.small:
			self.small = False
			self.remove(self.control)
			self.llp.setLargeLayout()
			self.control.setLargeLayout()
			self.add(self.llp)
			if self.has_header:
				self.insert(self.header, 0)
				self.setCellHeight(self.header, '58px')
		
	def onWindowResized(self):
		if int(self.getClientWidth()) < 800:
			self.setSmallLayout()
		else:
			self.setLargeLayout()
		self.llp.updateSplitter()
		self.relayout()

	def createMap(self):
		self.llp.createMap()

	def relayout(self):
		self.control.relayout()

# def test():
# 	print "Aggiungo listener"
# 	JS("""
# 		$wnd.document.addEventListener(
# 			"pause",
# 			function() {alert("Paused");},
# 			false
# 		);
# 		$wnd.document.addEventListener(
# 			"resume",
# 			function() {alert("Resumed");},
# 			false
# 		);
# 	""")
# 	print "Lister aggiunti"
	
if __name__ == '__main__':
	raw_params = getRawParams()
	lang = 'it'
	store_lang = False
	stored_lang = storage_get('hl', '-')
	if stored_lang != '-':
		lang = stored_lang
	elif raw_params.find('hl=it') != -1:
		lang = 'it'
		store_lang = True
	elif raw_params.find('hl=en') != -1 or raw_params.find('HL=EN') != -1:
		lang = 'en'
		store_lang = True
	if store_lang:
		storage_set('hl', lang)
	set_lang('it', lang)

	# Workaround: don't show status bar on iOS, to avoid overlapping with app tool bar on iOS 7
	if ios():
		JS("""
			$wnd.StatusBar.hide();
		""")

	rp = RootPanel()
	splash = DOM.getElementById("Loading-Message")
	par = DOM.getParent(splash)
	DOM.removeChild(par, splash)
	gp = GeneralPanel()
	rp.add(gp)
	gp.createMap()
	gp.relayout()

	if int(gp.getClientWidth()) < 800:
		gp.setSmallLayout()

	session_key = storage_get('session_key', '')
	client.servizi_app_init(session_key, getRawParams(), JsonHandler(gp.onAppInit))

	Window.addWindowResizeListener(gp)
	gp.getElement().scrollIntoView()


