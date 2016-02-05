# coding: utf-8

from django.core.management.base import BaseCommand, CommandError
from paline.caricamento_rete.caricamento_rete import carica_rete, scarica_rete, scarica_orari_partenza, scarica_stat_passaggi
from paline.tpl import calcola_frequenze

class Command(BaseCommand):
	args = """
	"""

	help = """
		Scarica da Muoveri a Roma:
		* rete
		* orari di partenza
		* frequenze misurate
		e aggiorna il db locale
	"""
	

	def handle(self, *args, **options):
		print "\n\n1 di 5: Download orari partenza"
		scarica_orari_partenza()
		print "\n\n2 di 5: Ricalcolo frequenze da timetable"
		calcola_frequenze(percorsi_da_rete=False)
		print "\n\n3 di 5: Download statistiche passaggi"
		scarica_stat_passaggi()		
		print "\n\n4 di 5: Download rete"
		scarica_rete()
		print "\n\n5 di 5: Aggiornamento rete nel database"
		carica_rete(no_validate=True)

