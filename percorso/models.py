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

from django.db import models
from django.contrib.auth.models import User

"""
# TODO: Questa tabella era presente sul vecchio server web, nel db 'mobile'.
#       Deve essere ricreata nel nuovo server db

class StazioneRfi(models.Model):
	id_palina = models.IntegerField(primary_key=True)
	nome_stazione = models.CharField(max_length=30)
	codice_rfi_stazione = models.CharField(max_length=40)
	
	class Meta:
		db_table = u'stazioni_rfi'	
"""

# Preferiti
class IndirizzoPreferito(models.Model):
	user = models.ForeignKey(User)
	nome = models.CharField(max_length=63)
	indirizzo = models.CharField(max_length=127)
	luogo = models.CharField(max_length=63)

	def __unicode__(self):
		return self.nome
	
	def indirizzo_composito(self):
		if self.luogo == '':
			return self.indirizzo
		return u"%s, %s" % (self.indirizzo, self.luogo)