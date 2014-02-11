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


from django.db import models
from servizi.models import Luogo
from gis import models as gis
from django.contrib.auth.models import User
import os, os.path
from django.core.files import File
import settings


modelli_risorse = set([])
		
def registra_modello_risorsa(klass):
	modelli_risorse.add(klass)
	return klass


class TipoRisorsa(models.Model):
	nome = models.CharField(max_length=255, db_index=True)
	padre = models.ForeignKey('TipoRisorsa', null=True, blank=True, db_index=True, default=None)
	icon = models.CharField(max_length=1023, default='pin_red.png')
	icon_width = models.IntegerField(default=32)
	icon_height = models.IntegerField(default=32)
	
	def __unicode__(self):
		return self.nome
	
	class Meta:
		verbose_name = u'Tipo risorsa'
		verbose_name_plural = u'Tipi risorsa'	
		
class TipoRisorsaCustom(TipoRisorsa):
	utente = models.ForeignKey(User)
	
	def __unicode__(self):
		return self.nome
	
	class Meta:
		verbose_name = u'Tipo risorsa custom'
		verbose_name_plural = u'Tipi risorsa custom'	

class Risorsa(Luogo):
	tipo_auto = None
	tipo = models.ForeignKey(TipoRisorsa, db_index=True)
	icon_auto = ''
	icon_size_auto = (16, 16)

	def __init__(self, *args, **kwargs):
		if self.tipo_auto is not None and not 'tipo' in kwargs:
			tipo, created = TipoRisorsa.objects.get_or_create(nome=self.tipo_auto)
			kwargs['tipo'] = tipo
			if created:
				tipo.icon = icon_auto
				tipo.icon_width, tipo.icon_height = self.icon_size_auto
				tipo.save()
				
		Luogo.__init__(self, *args, **kwargs)
		self.icon = self.tipo.icon
		self.icon_size = (self.tipo.icon_width, self.tipo.icon_height)
		

@registra_modello_risorsa
class RisorsaCustom(Risorsa):
	GeoModel = gis.Punto
	indirizzo = models.CharField(max_length=255, blank=True, default='')
	note = models.CharField(max_length=1023, blank=True, default='')
	
	def __unicode__(self):
		return self.nome_luogo
	
	def descrizione(self):
		d = """
			<b>Indirizzo</b>: %(indirizzo)s
		""" % {
			'indirizzo': unicode(self.indirizzo),
		}
		if len(self.note) > 0:
			d += '<br /><b>Note:</b>: %s' % self.note
		return d

@registra_modello_risorsa
class EsercizioCommerciale(Risorsa):
	GeoModel = gis.Punto
	indirizzo = models.CharField(max_length=255)
	icon_auto = 'parcheggi.gif'
	icon_size_auto = (16, 16)
	
	def __unicode__(self):
		return self.nome_luogo
	
	def descrizione(self):
		return """
			<b>Indirizzo</b>: %(indirizzo)s<br />
		""" % {
			'tipo': unicode(self.tipo),
			'indirizzo': self.indirizzo,
		}
	
	class Meta:
		verbose_name = u'Esercizio commerciale'
		verbose_name_plural = u'Esercizi commerciali'
		
@registra_modello_risorsa
class Farmacia(Risorsa):
	tipo_auto = 'Farmacie'
	GeoModel = gis.Punto
	indirizzo = models.CharField(max_length=255)
	telefono = models.CharField(max_length=255)
	icon_auto = 'farmacia.png'
	icon_size_auto = (20, 20)
	
	def __unicode__(self):
		return self.nome_luogo
	
	def descrizione(self):
		return """
			<b>Indirizzo</b>: %(indirizzo)s<br />
			<b>Tel/Fax</b>: %(tel)s<br />
		""" % {
			'tel': self.telefono,
			'indirizzo': self.indirizzo,
		}
	
	class Meta:
		verbose_name = u'Farmacia'
		verbose_name_plural = u'Farmacie'
		
@registra_modello_risorsa
class CarSharing(Risorsa):
	tipo_auto = 'Parcheggi car sharing'
	GeoModel = gis.Punto
	icon_auto = 'carsharing.png'
	icon_size_auto = (16, 16)
	
	def __unicode__(self):
		return self.nome_luogo
	
	def descrizione(self):
		return self.nome_luogo
	
	class Meta:
		verbose_name = u'Parcheggio car sharing'
		verbose_name_plural = u'Parcheggi car sharing'

try:
	CAR_SHARING = TipoRisorsa.objects.get(nome='Parcheggi car sharing').pk
except Exception:
	CAR_SHARING = -1