from __pyjamas__ import JS

flavors = ['app', 'web']
flavor_id = JS("""$wnd.flavor_id""")
flavor = flavors[flavor_id]

base_url = ['http://muovi.roma.it', ''][flavor_id]

def make_absolute(url):
	if not url.startswith('http://'):
		return base_url + url
	return url

users = [None]
controls = [None]

def set_user(u):
	users[0] = u

def get_user():
	return users[0]

def set_control(c):
	controls[0] = c

def get_control():
	return controls[0]

def old_android():
	if flavor == 'web':
		return False
	platform = JS("""$wnd.window.device.platform""")
	version = JS("""$wnd.window.device.version""")
	return platform == "Android" and int(version.split(".")[0]) < 4

def ios():
	if flavor == 'web':
		return False
	platform = JS("""$wnd.window.device.platform""")
	return platform == "iOS"