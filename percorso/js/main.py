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

from pyjamas.ui.RootPanel import RootPanel
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
from util import StyledFixedColumnFlexTable, HTMLFlowPanel, DP, VP, HP, GP, SP
from util import get_checked_radio, HidingPanel, MyAnchor
from datetime import date, time, datetime, timedelta
from Calendar import Calendar, DateField, TimeField
from map import MapPanel, Layer, LayerPanel
from cerca_percorso import CercaPercorsoPanel
from cerca_linea import CercaLineaPanel
from cerca_luogo import CercaLuogoPanel
from info_traffico import InfoTrafficoPanel

from DissolvingPopup import DissolvingPopup
from util import JsonHandler, redirect

client = JSONProxy('/json/', ['paline_percorso', 'urldecode'])

class ControlPanel(HidingPanel):
	def __init__(self, owner):
		HidingPanel.__init__(self)
		self.owner = owner
		self.map = None
		self.split = VerticalSplitPanel()
		self.split.setSize('100%', '100%')
		self.split.setSplitPosition('90%')
		
		self.tab = TabPanel()
		self.tab.setSize('100%', '100%')
		self.split.setTopWidget(self.tab)
		p = DOM.getParent(self.tab.getElement())
		DOM.setStyleAttribute(p, 'overflow-x', 'hidden')
		
		self.cerca_percorso = CercaPercorsoPanel(self, self.map)
		self.cerca_percorso.setSize('100%', '100%')
		self.tab.add(self.cerca_percorso, "Cerca percorso")
		self.tab.selectTab(0)
		
		self.cerca_linea = CercaLineaPanel(self, self.map)
		self.cerca_linea.setSize('100%', '100%')
		self.tab.add(self.cerca_linea, "Cerca linea")
			
		self.cerca_luogo = CercaLuogoPanel(self, self.map)
		self.cerca_luogo.setSize('100%', '100%')
		self.tab.add(self.cerca_luogo, "Cerca luogo")			
			
		self.add(self.split)
		
	def onUrldecode(self, params):
		if 'lf' in params and params['lf'] == 0:
			self.hide()		
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
		if 'cl' in params or 'id_percorso' in params:
			self.tab.selectTab(1)
		if ('cr' in params or 'cr_da' in params or 'cr_lista_tipi' in params) and not 'cr_a' in params:
			self.tab.selectTab(2)
		if 'info_traffico' in params:
			self.info_traffico = InfoTrafficoPanel(self)
			self.tab.add(self.info_traffico, "Traffico")
			self.info_traffico.setMap(map)

			
	def setTabCercaPercorso(self):
		self.tab.selectTab(0)
		
	def setTabCercaLinea(self):
		self.tab.selectTab(1)
		
	def setTabCercaLuogo(self):
		self.tab.selectTab(2)
		
	def cercaPercorsoRisorse(self, da, tipi, a=None):
		self.setTabCercaPercorso()
		self.cerca_percorso.cercaPercorsoRisorse(da, tipi, a)
	
		
	def setMap(self, map):
		self.map = map
		self.cerca_percorso.setMap(map)
		self.cerca_linea.setMap(map)
		self.cerca_luogo.setMap(map)
		self.split.setBottomWidget(LayerHolder(map))
		

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


	def onHide(self, source):
		self.map.relayout()
		
def getRawParams():
	return Window.getLocation().getSearch()[1:]

class GeneralPanel(VerticalPanel):
	def __init__(self):
		VerticalPanel.__init__(self)
		raw_params = getRawParams()

		if raw_params.find('iframe=0') == -1:
			# header
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
		client.urldecode(getRawParams(), JsonHandler(self.onUrldecode))
		
	def onUrldecode(self, params):
		self.main.control.onUrldecode(params)
	
if __name__ == '__main__':
	rp = RootPanel()
	splash = DOM.getElementById("Loading-Message")
	par = DOM.getParent(splash)
	DOM.removeChild(par, splash)
	gp = GeneralPanel()
	#rp.add(gp.main.control.tab)
	rp.add(gp)

