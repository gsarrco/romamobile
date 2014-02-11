from fabric.api import cd, run, env, sudo, execute, put, local, lcd
from time import sleep
import os, os.path

"""
run: fab command:environment

Available commands: deploy, deploy_percorso, deploy_all
Available environments: test, pre, pro
"""

env.user = 'root'

flavs = {
	'pro': {
		'dir': '/home/python/atacmobile/atacmobile',
		'restart': './restart-pro',
		'hosts': ['192.168.90.38', '192.168.90.39']
	},
	'pre': {
		'dir': '/home/python/atacmobile-pre/atacmobile',
		'restart': './restart-pre',
		'hosts': ['192.168.90.39']
	},
	'test': {
		'dir': '/home/python/atacmobile-test/atacmobile',
		'restart': '',
		'hosts': ['192.168.90.39']
	}
}

interval = 40

# Workers

def do_deploy(f, nosleep=False):
	with cd(f['dir']):
		sudo("svn up --config-dir /home/python/.subversion/", user='python')
	if f['restart'] != '':
		run(f['restart'], pty=False)
	if len(f['hosts']) > 1 and not nosleep:
		sleep(interval)

def do_deploy_percorso(f):
	with cd(f['dir']):
		base = 'percorso/js/output'
		for k in os.listdir(base):
			if k != 'lib':
				put(os.path.join(base, k), 'percorso/js/output')

def do_deploy_all(f):
	do_deploy(f, True)
	do_deploy_percorso(f)
	if len(f['hosts']) > 1:
		sleep(interval)

def do_pyjs(debug=False):
	with lcd('percorso/js'):
		local('pyjsbuild main.py' + (' -d' if debug else ''))
		local('python update_cache.py' + (' -d' if debug else ''))

# Commands

def deploy(flav):
	f = flavs[flav]
	execute(do_deploy, f, hosts=f['hosts'])

def deploy_percorso(flav):
	f = flavs[flav]
	execute(do_deploy_percorso, f, hosts=f['hosts'])

def deploy_all(flav):
	f = flavs[flav]
	execute(do_deploy_all, f, hosts=f['hosts'])

def pyjs():
	execute(do_pyjs)

def pyjsd():
	execute(do_pyjs, True)