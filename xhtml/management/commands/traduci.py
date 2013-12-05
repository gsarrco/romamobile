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

from django.core.management.base import BaseCommand, CommandError
import datetime 
import os, os.path, sys
import settings
from django.core.management.commands.makemessages import make_messages, handle_extensions

class Command(BaseCommand):
	args = '<poll_id poll_id ...>'
	help = '[app]'

	def handle(self, *args, **options):
		extensions = handle_extensions(['html'])
		if len(args) == 0:			
			for a in settings.XHTML_APPS:
				print a
				os.chdir(a)
				make_messages(all=True, extensions=extensions)
				os.chdir('..')
		else:
			os.chdir(args[0])
			make_messages(all=True, extensions=extensions)
			os.chdir('..')
