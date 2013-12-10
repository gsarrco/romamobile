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

from django.core.urlresolvers import reverse
from django.conf.urls.defaults import patterns, include, url, handler404, handler500
from django.http import HttpResponseRedirect
import os, os.path
import settings
from jsonrpc import jsonrpc_site
from servizi.utils import group_required, autodiscover
from xhtml.views import ga as google_analytics, ping
import django.views.static
import servizi.views
import django
if django.get_version() >= '1.5.1':
	from django.views.generic.base import RedirectView
	redirect_to = RedirectView.as_view()
else:
	from django.views.generic.simple import redirect_to
	
# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

# Autodiscover backviews
autodiscover('backviews')
autodiscover('views')

def url_xhtml(servizi):
	return [url('^%s/' % s, include('%s.urls' % s)) for s in servizi]

def url_servizi(servizi):
	return [url('^ws/xml/%s/' % s, include('%s.wsurls' % s)) for s in servizi]

url_opendata = [
		url(r'opendata/retetpl', django.views.static.serve, {'path': 'opendata/rete_tpl.zip', 'document_root': settings.TROVALINEA_PATH_RETE})
]

pattern_list = [
	url(r'^static/admin/(?P<path>.*)$', django.views.static.serve, {'document_root': os.path.join(os.path.dirname(__file__),'admin_media').replace('\\','/')}),
	url(r'^admin/', include(admin.site.urls)),
	url(r'^json/browse/', 'jsonrpc.views.browse', name="jsonrpc_browser"),
	url(r'^json/$', jsonrpc_site.dispatch, name='jsonrpc_mountpoint'),
	url(r'^js/(?P<path>.*)$', group_required(['operatori', 'utt'], HttpResponseRedirect('/backend'))(django.views.static.serve),
		{'document_root': os.path.join(os.path.dirname(__file__), 'javascript/output').replace('\\','/')}),
	url(r'^cercapercorso/', lambda req: HttpResponseRedirect('/percorso/js')),
	url(r'^backend$', servizi.views.backend),
	url(r'^backend/logout$', servizi.views.backend_logout),
	url(r'^backend/password/change/$', 'django.contrib.auth.views.password_change', {'template_name': 'password_change_form.html', 'post_change_redirect': '/backend/password/change/done/'}),
	url(r'^backend/password/change/done/$', 'django.contrib.auth.views.password_change_done', {'template_name': 'password_change_done.html'}),
	url(r'^media/(?P<path>.*)$', group_required(['doc'], HttpResponseRedirect('/backend'))(django.views.static.serve),
			{'document_root': settings.MEDIA_ROOT}),	
	url(r'^facebook$', redirect_to, {'url': 'https://www.facebook.com/pages/Muoversi-a-Roma/202373936538862'}),
	url(r'^twitter$', redirect_to, {'url': 'http://twitter.com/romamobilita'}),	
	url(r'^$', 'servizi.views.servizi_new'),
	url(r'^i18n/', include('django.conf.urls.i18n')),
	url('^favicon.ico', django.views.static.serve,
		{'document_root': os.path.join(os.path.dirname(__file__), 'xhtml/static').replace('\\','/'), 'path': 'img/favicon.ico'},
	),
	url(r'^xhtml/ga$', google_analytics),
	url(r'^ws/xml/lingue/', include('lingua.wsurls')), # Workaround temporaneo
] + [
	url(r'^%s/s/(?P<path>.*)$' % x, 'django.views.static.serve',
		{'document_root': os.path.join(os.path.dirname(__file__), '%s/static' % x).replace('\\','/')}) for x in settings.LOCAL_APPS
] + url_servizi(settings.WS_APPS) + url_xhtml(settings.XHTML_APPS) + url_opendata

urlpatterns = patterns('', *pattern_list)

handler404 = 'xhtml.views.handler404'
# handler500 = 'xhtml.views.handler500'
