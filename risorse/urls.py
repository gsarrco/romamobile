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

from django.conf.urls.defaults import patterns, include, url
import views

urlpatterns = patterns('',
	url('^$', views.default),
	#url(r'^dettaglio$', views.dettaglio),
	url(r'^mappa$', views.mappa),
	url(r'^mappacmd/(\w+)', views.mappacmd),
	url(r'^mappaimg$', views.mappaimg),
	url(r'^percorso/(\d+)', views.percorso),
)
