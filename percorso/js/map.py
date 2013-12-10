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


from pyjamas.ui.Calendar import Calendar, DateField
from pyjamas.ui.RootPanel import RootPanel
from pyjamas.ui.VerticalPanel import VerticalPanel
from pyjamas.ui.HorizontalPanel import HorizontalPanel
from pyjamas.ui.SimplePanel import SimplePanel
from pyjamas.ui.FlowPanel import FlowPanel
from pyjamas.ui.DisclosurePanel import DisclosurePanel
from pyjamas.ui.TabPanel import TabPanel
from pyjamas.ui.Grid import Grid
from pyjamas.ui.Frame import Frame
from pyjamas.ui.TextBox import TextBox
from pyjamas.ui.TextArea import TextArea
from pyjamas.ui.HTML import HTML
from pyjamas.ui.Label import Label
from pyjamas.ui.CheckBox import CheckBox
from pyjamas.ui.ListBox import ListBox
from pyjamas.ui.Button import Button
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
from pyjamas.gmaps.Map import Map, MapTypeId, MapOptions
from pyjamas.gmaps.Base import LatLng
from pyjamas.ui.ContextMenuPopupPanel import ContextMenuPopupPanel
from datetime import date, time, datetime, timedelta
from __pyjamas__ import JS

from DissolvingPopup import DissolvingPopup
from util import JsonHandler, redirect, MenuCmd, HTMLFlowPanel, SearchPopup

from pyjamas.gmaps.Map import Map, MapTypeId, MapOptions

client = JSONProxy('/json/', ['mappa_layer'])

def list_to_point_array(l):
	JS("""punti = Array();""")
	for y, x in l:
		JS("""punti.push(new $wnd['google'].maps.LatLng(x, y));""")
	return punti

class MapPanel(SimplePanel):
	def __init__(self, owner, display_callback=None):
		SimplePanel.__init__(self)
		self.owner = owner
		self.owner.add(self)
		self.setSize('100%', '100%')
		self.layers = []
		self.layer_panels = []
		self.right_click_options = []
		options = MapOptions(zoom=12, center=LatLng(41.892055, 12.483559), mapTypeId=MapTypeId.ROADMAP)
		self.map = Map(self.getElement(), options)
		map = self.map
		func = self.onRightClick
		self.addStyleName('pyjsmapid')
		self.display_callback=display_callback
		JS("""
			$wnd['google'].maps.event.addListener(map, 'rightclick', function(event) {
				var lat = event.latLng.lat();
    		var lng = event.latLng.lng();
				func(lat, lng, event.pixel.x, event.pixel.y);
			});
		""")
		self.open_bubble = None
		
	def addRightClickOption(self, option, callback):
		self.right_click_options.append((option, callback))
		
	def rightClickHandlerFactory(self, cb, lat, lng):
		def handler():
			cb(lat, lng)
		return handler
		
	def onRightClick(self, lat, lng, x, y):
		mx = DOM.getAbsoluteLeft(self.getElement())
		my = DOM.getAbsoluteTop(self.getElement())
		menu = MenuBar(vertical=True)
		for opt, cb in self.right_click_options:
			menu.addItem(opt, MenuCmd(self.rightClickHandlerFactory(cb, lat, lng)))
		popup = ContextMenuPopupPanel(menu)
		popup.showAt(x + mx, y + my)
		
	def relayout(self):
		JS("""$wnd['google'].maps.event.trigger(self.map, "resize");""")
			
	def replace_bubble(self, new_bubble):
		if self.open_bubble is not None:
			self.open_bubble.closeBubble()
		self.open_bubble = new_bubble
		
	def display(self):
		if self.display_callback is not None:
			self.display_callback()
		
	def addLayerPanel(self, lp):
		self.layer_panels.append(lp)
		
	def addLayer(self, l):
		self.layers.append(l)
		self.notifyLayerPanels()
	
	def removeLayer(self, l):
		self.layers.remove(l)
		self.notifyLayerPanels()
		
	def notifyLayerPanels(self):
		for l in self.layer_panels:
			l.redraw()
			
	def notifyLayerPanelsChecked(self, name, checked):
		for l in self.layer_panels:
			l.setChecked(name, checked)
			
	def layerByName(self, name):
		for l in self.layers:
			if l.name == name:
				return l
		return None
			
	def onLoadNewLayerFactory(self, layer_name, onDone, info_panel, on_error):
		def onLoadLayer(res):
			if 'errore' in res:
				if on_error is not None:
					on_error(res['errore'])
				return
			l = Layer(layer_name, res['descrizione'], self)
			l.deserialize(res, info_panel=info_panel)
			l.centerOnMap()
			if onDone is not None:
				self.onDone(l)

		return onLoadLayer
			
	def loadNewLayer(self, layer_name, func_name, func_id, onDone=None, toggle=None, reload=False, info_panel=None, on_error=None):
		self.display()
		l = self.layerByName(layer_name)
		if l is not None:
			if reload:
				l.destroy()
			else:
				if toggle is None:
					l.toggleVisible()
				else:
					l.setVisible(toggle)
				if onDone is not None:
					onDone(l)
				return
		client.mappa_layer((func_name, func_id), JsonHandler(self.onLoadNewLayerFactory(layer_name, onDone, info_panel, on_error)))
		
	def hideAllLayers(self):
		for l in self.layers:
			l.setVisible(False)
			
class InfoPanel(HorizontalPanel):
	def __init__(self, owner, icon, name, desc, distance, onClic=None):
		HorizontalPanel.__init__(self)
		self.addStyleName('palina')
		self.image = Image(icon)
		self.add(self.image)
		self.hfp = HTMLFlowPanel()
		self.hfp.addAnchor(name, self.onClic)
		if distance is not None:
			self.hfp.addHtml('&nbsp;a %s' % distance)
		self.hfp.addBr()
		self.hfp.addHtml(desc)
		self.add(self.hfp)
		self.onClicCallback = onClic
		
	def onClic(self):
		if onClicCallback is not None:
			self.onClicCallback()
		
	
		
class Layer:
	def __init__(self, name, label, map_panel, owner=None):
		self.name = name
		self.label = label
		self.map_panel = map_panel
		self.features = []
		self.visible = True
		self.sub = []
		self.owner = owner
		self.destroyed = False
		if self.owner is None:
			map_panel.addLayer(self)
		else:
			client.mappa_layer(name, JsonHandler(self.onMappaLayerDone))
			
	def onMappaLayerDone(self, res):
		self.deserialize(res)
		
	def getMap(self):
		return self.map_panel.map
	
	def deserialize(self, res, callbacks=None, info_panel=None):
		for f in self.features:
			f.setVisible(False)
		self.features = []		
		if 'markers' in res:
			for m in res['markers']:
				name = m['name'] if 'name' in m else None
				open = m['open'] if 'open' in m else False
				dc = None
				if 'drop_callback' in m and m['drop_callback'] != '':
					dc = callbacks[m['drop_callback']]
				infobox = "<b>%s</b>" % m['infobox']
				if m['desc'] != '':
					infobox += "<br /><br />%s" % m['desc']
				marker = Marker(self, m['point'], m['icon'], m['iconSize'], infobox, m['label'], m['anchor'], visible=self.visible, name=name, open=open, drop_callback=dc)
				if info_panel is not None:
					ip = InfoPanel(info_panel, m['icon'], m['infobox'], m['desc'], m['distance'], onClic=marker.openBubble)
					info_panel.add(ip)
		if 'polylines' in res:		
			for p in res['polylines']:
				Polyline(self, p['points'], p['opacity'], p['color'], p['thickness'], p['zIndex'], visible=self.visible)
		if 'sublayers' in res:
			for s in res['sublayers']:
				sl = Layer(s, None, self.map_panel, self)
				self.sub.append(sl)
		if 'refresh' in res:
			Timer(res['refresh'] * 1000, self.onRefresh)
			
	def onRefresh(self):
		client.mappa_layer(self.name, JsonHandler(self.onMappaLayerDone))
			 
	def setVisible(self, visible=True):
		self.visible = visible
		if self.owner is None:
			self.map_panel.notifyLayerPanelsChecked(self.name, visible)
		for f in self.features:
			f.setVisible(visible)
		for s in self.sub:
			s.setVisible(visible)
			
	def toggleVisible(self):
		self.setVisible(not self.visible)
		
	def destroy(self):
		if not self.destroyed:
			self.destroyed = True
			for s in self.sub:
				s.destroy()
			self.sub = []
			self.setVisible(False)
			self.features = []
			if self.owner is None:
				self.map_panel.removeLayer(self)
			else:
				self.owner = None
		
	def centerOnMap(self):
		bounds = JS("""new $wnd['google'].maps.LatLngBounds();""")
		map = self.map_panel.map
		n = 0
		for f in self.features:
			if isinstance(f, Marker):
				n += 1
				m = f.point
				JS("""bounds.extend(m);""")
		if n > 0:
			JS("""map.fitBounds(bounds);""")
			if n == 1:
				JS("""map.setZoom(16);""")
		
		
class LayerPanel(VerticalPanel):
	def __init__(self, map):
		VerticalPanel.__init__(self)
		self.map = map
		self.cbs = []
		self.names = {}
		self.map.addLayerPanel(self)
		self.no_layers = HTML("Cerca un percorso, una linea o una fermata per mostrarla sulla mappa.")
		self.add(self.no_layers)
		self.setWidth('100%')
		
	def redraw(self):
		if self.no_layers is not None:
			self.remove(self.no_layers)
			self.no_layers = None
		for c in self.cbs:
			self.remove(c)
		self.cbs = []
		self.names = {}
		for l in self.map.layers:
			hp = HorizontalPanel()
			cb = CheckBox(l.label)
			cb.setChecked(l.visible)
			cb.addClickListener(self.onCB)
			cb.layer = l
			hp.add(cb)
			i = Image('close.png')
			i.addClickListener(self.onCloseLayerFactory(l))
			hp.add(i)
			hp.setCellHorizontalAlignment(i, HasAlignment.ALIGN_RIGHT)
			hp.setCellVerticalAlignment(i, HasAlignment.ALIGN_MIDDLE)
			hp.setWidth('100%')
			self.add(hp)
			self.setCellWidth(hp, '100%')
			self.names[l.name] = cb
			self.cbs.append(hp)
			
	def onCloseLayerFactory(self, layer):
		def onCloseLayer():
			layer.destroy()
			
		return onCloseLayer
		
	def onCB(self, source):
		source.layer.setVisible(source.isChecked())
		
	def setChecked(self, name, checked):
		if name in self.names:
			cb = self.names[name]
			cb.setChecked(checked)
			

class Marker:
	def __init__(
		self,
		layer,
		point,
		icon_path,
		icon_size=(20, 20),
		infobox=None,
		label=None,
		anchor=None,
		infobox_listener=None,
		visible=True,
		name=None,
		open=False,
		drop_callback=None
	):
		self.layer = layer
		self.visible = visible
		self.name = name
		layer.features.append(self)
		map = layer.getMap() if visible else None
		lb = label
		x = point[1]
		y = point[0]
		self.bubble = None
		if anchor is not None:
			ax = anchor[0]
			ay = anchor[1]
			JS("""ajs = new $wnd['google'].maps.Point(ax, ay);""")
		else:
			ajs = None
		draggable = False if drop_callback is None else True
		self.marker = JS("""
			self.point = new $wnd['google'].maps.LatLng(x, y);
			mImg = new $wnd['google'].maps.MarkerImage(icon_path, null, null, ajs);
			mOpt = {
				position: self.point,
				title: lb,
				icon: mImg,
				draggable: draggable,
				map: map
			};
			self.marker = new $wnd['google'].maps.Marker(mOpt);
		""")
		marker = self.marker
		if drop_callback is not None:
			JS("""
				$wnd['google'].maps.event.addListener(marker, 'dragend', function() {
					var latlng = marker.getPosition();
					drop_callback(latlng.lat(), latlng.lng());
				});
			""")
		if infobox is not None or infobox_listener is not None:
			if infobox is not None:
				infobox_listener = self.openBubble
			else:
				infobox = ''
			JS("""
				mInfoOpt = {
					content: infobox,
					position: new $wnd['google'].maps.LatLng(x, y),
					pixelOffset: new $wnd['google'].maps.Size(0, 0),
					visible: true
				};
			""")
			self.bubble = JS("""new $wnd['google'].maps.InfoWindow(mInfoOpt);""")	
			JS("""$wnd['google'].maps.event.addListener(self.marker, "click", function() {infobox_listener(); });""")
		if open:
			self.openBubble()
			

	def openBubble(self, new_content=None):
		self.layer.map_panel.replace_bubble(self)
		self.layer.map_panel.display()
		map = self.layer.getMap()
		if new_content is not None:
			self.bubble.setContent(new_content)
		elif self.name is not None:
			client.mappa_layer(self.name, JsonHandler(self.onMappaLayerDone))
		JS("""self.bubble.open(map, self.marker);""")
		
	def onMappaLayerDone(self, res):
		self.bubble.setContent(res)
		
	def closeBubble(self):
		JS("""self.bubble.close();""")
		
	def setVisible(self, visible):
		self.visible = visible
		if visible:
			map = self.layer.getMap()
		else:
			map = None
		self.marker.setMap(map)


class Polyline:
	def __init__(self, layer, points, opacity=1, color='#000000', thickness=1, zIndex=0, visible=True):
		pt = list_to_point_array(points)
		self.visible = visible
		self.layer = layer
		layer.features.append(self)
		map = layer.getMap() if visible else None
		JS("""
			var myPolyOpt = {
					strokeColor: color,
					strokeOpacity: opacity,
					strokeWeight: thickness,
					visible: true,
					zIndex: zIndex
			}
			self.myPoly = new $wnd['google'].maps.Polyline(myPolyOpt);
			self.myPoly.setPath(pt);
			self.myPoly.setMap(map);
		""")
		
	def setVisible(self, visible):
		self.visible = visible
		if visible:
			map = self.layer.getMap()
		else:
			map = None
		self.myPoly.setMap(map)
	
		
		
class Geocoder(KeyboardHandler):
	def __init__(self, search, method, map=None, pin_url='partenza_percorso.png', pin_size=(32, 32), lngBox=None, latBox=None, callback=None):
		self.search = search
		self.map = map
		self.search.addKeyboardListener(self)
		self.search.addChangeListener(self.onSearchChange)
		self.method = method
		self.lngBox = lngBox
		self.latBox = latBox
		if self.lngBox is not None:
			self.lngBox.addKeyboardListener(self)
			self.lngBox.addChangeListener(self.onLngLatChange)
			self.latBox.addKeyboardListener(self)
			self.latBox.addChangeListener(self.onLngLatChange)
		self.lat = None
		self.lng = None
		self.valid = False
		self.layer = None
		self.marker = None
		self.pin_url = pin_url
		self.pin_size = pin_size
		self.popup = None
		self.callback = callback
		
	def onSearchChange(self):
		if not self.valid:
			self.disambiguate()
			
	def onLngLatChange(self):
		self.parseLngLatFromBoxes()
		
	def onKeyUp(self, sender, keycode, modifiers):
		self.search.removeStyleName('validation-error')
		if sender == self.search:
			self.valid = False
			if keycode == 40 and self.popup is not None:
				self.popup.setFocus()
			elif self.popup is not None:
				self.popup.hide()
			if keycode == 13:
				self.disambiguate()
		else:
			self.parseLngLatFromBoxes()
				
	def parseLngLatFromBoxes(self):
		try:
			lat = float(self.latBox.getText())
			self.lng = float(self.lngBox.getText())
			self.lat = lat
			self.valid = True
			self.updateMap()
		except Exception:
			self.valid = False		
			
	def onSearchPopupSelected(self, pk, address):
		self.search.setText(address)
		self.popup.hide()
		self.disambiguate()
			
	def onDisambiguateDone(self, res):
		if res['stato'] == 'OK':
			self.valid = True
			self.lat = res['lat']
			self.lng = res['lng']
			self.search.setText(res['indirizzo'])
			self.updateCoordBoxes()
			self.updateMap()
		elif res['stato'] == 'Ambiguous':
			self.valid = False
			res = [(x, x) for x in res['indirizzi']]
			if self.popup is not None:
				self.popup.update(res)
			else:
				self.popup = SearchPopup(res, self.onSearchPopupSelected)
			self.popup.setPopupPosition(self.search.getAbsoluteLeft(), self.search.getAbsoluteTop() + 20)
			self.popup.show()
		else:
			self.valid = False
			
	def disambiguate(self):
		place = self.search.getText()
		if len(place) >= 3:
			self.method(place, JsonHandler(self.onDisambiguateDone))
	
	def coordToString(self, coord):
		if coord is None:
			return ''
		return "%f" % coord
	
	def updateCoordBoxes(self):
		if self.lngBox is not None:
			self.lngBox.setText(self.coordToString(self.lng))
			self.latBox.setText(self.coordToString(self.lat))
			
	def updateMap(self):
		if self.map is not None:
			if self.layer is not None:
				self.layer.destroy()
			self.layer = Layer('geocoder_layer', 'Indirizzo trovato', self.map)
			m = Marker(
				self.layer,
				(self.lng, self.lat),
				self.pin_url,
				icon_size=self.pin_size,
				drop_callback=self.onDrop
			)
			self.layer.centerOnMap()
		if self.callback is not None:
			self.callback()
			
	def onDrop(self, lat, lng):
		self.lng = lng
		self.lat = lat
		self.updateCoordBoxes()
		if self.callback is not None:
			self.callback()
		
	def setAddress(self, address, lng, lat):
		self.search.setText(address)
		self.lng = lng
		self.lat = lat
		self.valid = True
		self.updateCoordBoxes()
		self.updateMap()
		
	def getAddress(self):
		if self.valid:
			return self.search.getText(), self.lng, self.lat
		else:
			return None
		
	def setValidationError(self):
		self.search.addStyleName('validation-error')
		
	def destroy(self):
		if self.layer is not None:
			self.layer.destroy()
		
		