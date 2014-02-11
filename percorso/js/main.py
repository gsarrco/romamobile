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
from util import StyledFixedColumnFlexTable, HTMLFlowPanel, DP, VP, HP, GP, SP, DeferrablePanel, DeferrableTabPanel
from util import get_checked_radio, HidingPanel, MyAnchor, LoadingButton, SearchBox
from util import wait_init, wait_start, wait_stop
from datetime import date, time, datetime, timedelta
from Calendar import Calendar, DateField, TimeField
from map import MapPanel, Layer, LayerPanel, get_location
from cerca_percorso import CercaPercorsoPanel
from cerca_linea import CercaLineaPanel
from cerca_luogo import CercaLuogoPanel
from info_traffico import InfoTrafficoPanel
from __pyjamas__ import JS

from DissolvingPopup import DissolvingPopup
from util import JsonHandler, redirect

client = JSONProxy('/json/', ['paline_percorso', 'urldecode', 'servizi_autocompleta_indirizzo', 'paline_smart_search'])


class SearchMapPanel(VerticalPanel, KeyboardHandler, FocusHandler, DeferrablePanel):
	def __init__(self, owner, map):
		VerticalPanel.__init__(self)
		DeferrablePanel.__init__(self)
		self.owner = owner
		self.base = VP(
			self,
			[
				{
					'class': VP,
					'style': 'search-help',
					'name': 'search_help',
					'sub': [
						{
							'class': HTML,
							'args': ["""
								<b>Una ricerca, tanti servizi</b><br />
								Per i tempi di attesa bus, il cerca linea e il cerca percorso usa la casella qui sotto.
								Inserisci il numero di fermata, la linea bus o l'indirizzo, oppure tocca la mappa.
							"""],
						},
						{
							'class': HP,
							'horizontal_alignment': HasAlignment.ALIGN_CENTER,
							'sub': [
								{
									'class': MyAnchor,
									'name': 'chiudi_help',
									'horizontal_alignment': HasAlignment.ALIGN_CENTER,
									'call_setWidget': ([HTML("Chiudi suggerimento")], {}),
									'call_addClickListener': ([self.onChiudiHelp], {}),
								},
								{
									'class': MyAnchor,
									'name': 'nascondi_help',
									'call_setWidget': ([HTML("Non mostrare pi&ugrave;")], {}),
									'call_addClickListener': ([self.onNascondiHelp], {}),
								},
							],
						},
					],
				},
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
										'call_addFocusListener': ([self], {}),
										'args': [client.servizi_autocompleta_indirizzo, None, 3, 100, False],
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
							'args': ['Cerca', self.onCerca],
							'width': '30%',
							'name': 'button',
							'style': 'over-map',
						},
					]
				},
			],
			add_to_owner=True,
		)
		JS("""if(localStorage && localStorage.nascondiHelp == '1') {self.onChiudiHelp();}""")
		self.map = map
		self.map.setSize('100%', '100%')
		self.add(map)
		self.setCellHeight(self.map, '100%')
		self.base.by_name('localizza').addClickListener(self.onLocalizza)

	def onChiudiHelp(self):
		self.base.remove(self.base.by_name('search_help'))

	def onNascondiHelp(self):
		self.onChiudiHelp()
		JS("""localStorage.nascondiHelp = 1;""")

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
		self.cercaLinea(self.base.by_name('query').getText())

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
		client.paline_smart_search(query, JsonHandler(self.onCercaDone))

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

	def onFocus(self, text):
		text.selectAll()

	def onKeyDown(self, sender, keycode, modifiers):
		if keycode == 13:
			self.onCerca()

	def onTabSelected(self):
		self.owner.map.relayout()


class ControlPanel(HidingPanel):
	def __init__(self, owner):
		super(ControlPanel, self).__init__()
		self.owner = owner
		self.dirty = False
		self.map = None
		self.map_tab = None
		self.small = False
		self.layers = None
		self.posizione = None
		self.split = VerticalSplitPanel()
		self.split.setSize('100%', '100%')
		self.split.setSplitPosition('90%')

		self.tab_holder = VerticalPanel()
		self.tab_holder.setSize('100%', '100%')
		
		self.tab = DeferrableTabPanel(self)
		self.tab.setSize('100%', '100%')
		self.tab_holder.add(self.tab)
		self.tab_holder.setCellHeight(self.tab, '100%')
		self.split.setTopWidget(self.tab_holder)
		p = DOM.getParent(self.tab.getElement())
		DOM.setStyleAttribute(p, 'overflow-x', 'hidden')

		self.cerca_percorso = CercaPercorsoPanel(self)
		self.tab.add(self.cerca_percorso, HTML("Percorso"))
		self.tab.selectTab(0)
		
		self.cerca_linea = CercaLineaPanel(self, self.map)
		self.cerca_linea.setSize('100%', '100%')
		self.tab.add(self.cerca_linea, HTML("Linea"))
			
		self.cerca_luogo = CercaLuogoPanel(self, self.map)
		self.cerca_luogo.setSize('100%', '100%')
		self.tab.add(self.cerca_luogo, HTML("Luogo"))

		self.add(self.split)

		self.old_width = self.tab.getClientWidth()
		wait_init(self.tab_holder)


	def relayout(self):
		width = self.tab.getClientWidth()
		if (not self.small) or (width != self.old_width):
			self.old_width = width
			self.cerca_percorso.do_or_defer(self.cerca_percorso.relayout)
			self.cerca_linea.do_or_defer(self.cerca_linea.relayout)
			self.cerca_luogo.do_or_defer(self.cerca_luogo.relayout)
			if self.small:
				self.map_tab.do_or_defer(self.map.relayout)

	def setDirty(self):
		self.dirty = True


	def center_and_zoom(self, layer):
		if self.small:
			self.map_tab.do_or_defer(layer.centerOnMap)
		else:
			layer.centerOnMap()
		
	def onUrldecode(self, params):
		"""
		if 'lf' in params and params['lf'] == 0:
			self.hide()
		"""
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
		if 'info_traffico' in params:
			self.info_traffico = InfoTrafficoPanel(self)
			self.tab.add(self.info_traffico, HTML("Traffico"))
			self.info_traffico.setMap(map)
			
	def setTabCercaPercorso(self):
		self.tab.selectTab(0)
		
	def setTabCercaLinea(self):
		self.tab.selectTab(1)
		
	def setTabCercaLuogo(self):
		self.tab.selectTab(2)
		
	def setTabMappaPercorso(self):
		if self.small:
			self.tab.selectTab(3)
			self.tab.star_tab(0)
		else:
			self.tab.selectTab(0)

	def setTabPercorsoMappa(self):
		if self.small:
			self.tab.selectTab(0)
			self.tab.star_tab(3)
		else:
			self.tab.selectTab(0)
			
	def setTabMappaLinea(self):
		if self.small:
			self.tab.selectTab(3)
			self.tab.star_tab(1)
		else:
			self.tab.selectTab(1)

	def setTabLineaMappa(self):
		if self.small:
			self.tab.selectTab(1)
			self.tab.star_tab(3)
		else:
			self.tab.selectTab(1)
			
	def setTabMappaLuogo(self):
		if self.small:
			self.tab.selectTab(3)
			self.tab.star_tab(2)
		else:
			self.tab.selectTab(2)

	def setTabMappa(self):
		if self.small:
			self.tab.selectTab(3)
		
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
	
	def setMap(self, map):
		self.map = map
		self.cerca_percorso.setMap(map)
		self.cerca_linea.setMap(map)
		self.cerca_luogo.setMap(map)
		self.layers = LayerHolder(map)
		self.split.setBottomWidget(self.layers)
		get_location(self.onLocation)

	def localizza(self):
		self.dirty = False
		wait_start()
		get_location(self.onLocation)

	def onLocation(self, lng, lat):
		wait_stop()
		self.posizione = 'Posizione attuale <punto:(%f,%f)>' % (lat, lng)
		if not self.dirty:
			self.cerca_linea.createClLayer()
			client.paline_smart_search(self.posizione, JsonHandler(self.cerca_linea.onCercaDone))

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
		
	def setLayers(self, layers):
		self.layers = layers
		
	def onBeforeTabSelected(self, sender, index):
		return True
	
	def setSmallLayout(self):
		self.small = True
		self.map_tab = SearchMapPanel(self, self.map)
		self.map_tab.setSize('100%', '100%')
		self.tab.add(self.map_tab, HTML("Mappa"))
		self.map_tab.setSize('100%', '100%') #self.tab.getClientHeight())
		# self.tab.add(self.layers, "Layer")
		self.map_tab.do_or_defer(self.map.relayout)
		self.relayout()
		self.setTabCercaPercorso()
		self.setTabCercaLinea()
		self.setTabCercaLuogo()
		self.setTabMappa()
		
	def setLargeLayout(self):
		self.small = False
		print self.tab.getTabBar().getSelectedTab()
		if self.tab.getTabBar().getSelectedTab() == 3: # Map
			self.setTabCercaPercorso()
		# self.tab.remove(self.layers)
		self.map_tab.remove(self.map)
		self.tab.remove(self.map_tab)
		self.split.setTopWidget(self.tab_holder)
		self.split.setBottomWidget(self.layers)
		self.layers.setVisible(True)
		self.relayout()
		
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
		
		titolo = HTML('Ora presenti sulla mappa')
		titolo.addStyleName('indicazioni-h1')
		titolo.setWidth('100%')
		vp.add(titolo)
		
		layer_panel = LayerPanel(map)
		vp.add(layer_panel)
		vp.setCellWidth(layer_panel, '100%')
		
		self.add(vp)
	

class MainPanel(HorizontalPanel):
	def __init__(self):
		HorizontalPanel.__init__(self)
		
		# control panel
		self.control = ControlPanel(self)
		self.control.setSize('0', '100%')
		self.add(self.control)
		self.setCellHeight(self.control, '100%')
		#self.setCellWidth(self.control, '0')
		
		# map panel
		self.map = MapPanel(self)
		self.map.setSize('100%', '100%')
		self.add(self.map)
		self.setCellWidth(self.map, '100%')
		self.setCellHeight(self.map, '100%')

		# the end
		self.control.setMap(self.map)
		self.control.addHideListener(self.onHide)
		self.setSize("100%", "100%")

	def center_and_zoom(self, layer):
		self.control.center_and_zoom(layer)

	def onHide(self, source):
		self.map.relayout()
				
	def setSmallLayout(self):
		self.remove(self.control)
		self.remove(self.map)
		self.add(self.control.tab_holder)
		self.control.setSmallLayout()
		
	def setLargeLayout(self):
		self.control.setLargeLayout()
		self.add(self.control)
		self.setCellHeight(self.control, '100%')
		self.add(self.map)
		self.setCellWidth(self.map, '100%')
		self.setCellHeight(self.map, '100%')
		self.map.relayout()

	def createMap(self):
		self.map.create_map()
		
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
		self.main = MainPanel()
		self.add(self.main)
		self.setCellHeight(self.main, '100%')
		self.setSize('100%', '100%')

	def setSmallLayout(self):
		if not self.small:
			self.small = True
			if self.has_header:
				self.remove(self.header)
			self.main.setSmallLayout()
		
	def setLargeLayout(self):
		if self.small:
			self.small = False
			self.main.setLargeLayout()
			if self.has_header:
				self.insert(self.header, 0)
				self.setCellHeight(self.header, '58px')

		
	def onUrldecode(self, params):
		self.main.control.onUrldecode(params)
		
	def onWindowResized(self):
		if int(self.getClientWidth()) < 640:
			self.setSmallLayout()
		else:
			self.setLargeLayout()
		self.main.control.updateSplitter()
		self.relayout()

	def createMap(self):
		self.main.createMap()

	def relayout(self):
		self.main.control.relayout()
	
if __name__ == '__main__':
	rp = RootPanel()
	splash = DOM.getElementById("Loading-Message")
	par = DOM.getParent(splash)
	DOM.removeChild(par, splash)
	gp = GeneralPanel()
	rp.add(gp)
	gp.createMap()
	gp.relayout()

	if int(gp.getClientWidth()) < 640:
		gp.setSmallLayout()
	client.urldecode(getRawParams(), JsonHandler(gp.onUrldecode))
	Window.addWindowResizeListener(gp)
