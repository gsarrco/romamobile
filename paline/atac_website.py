# coding: utf-8
# Written by Luca Allulli

import requests
from BeautifulSoup import BeautifulStoneSoup
from pprint import pprint
from collections import defaultdict

def get_viaggiaconatac(id_palina):
	r = requests.get("http://viaggiacon.atac.roma.it/asp/orariFermata.asp?impianto={}".format(id_palina))
	return r.text


def parse_viaggiaconatac(xml):
	soup = BeautifulStoneSoup(xml, fromEncoding='iso-8859-1')
	fermate = soup.findAll('fermata')
	out = defaultdict(list)
	for f in fermate:
		linea = f.linea.text
		msg = f.mesg.text.lower()
		if "arrivo" in msg:
			d = 0
		elif "capolinea" in msg:
			d = None
		else:
			d = int(msg[:msg.find(' ')])
		out[linea].append(d)
	return out




if __name__ == '__main__':
	o = parse_viaggiaconatac(get_viaggiaconatac("81915"))
	pprint(o)
