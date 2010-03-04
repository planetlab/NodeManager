#!/usr/bin/python

""" DRL configurator.  """

import os
import shutil

import logger
import tools


drl = """<?xml version="1.0" encoding="UTF-8"?>
<!-- %s -->
<drl>
    <machine id="%d" limit="%d" commfabric="MESH" accounting="STANDARD" ewma="0.1" htb_node="100" htb_parent="10">

%s
    </machine>
</drl>"""

def start(options, conf):
	logger.log('drl plugin starting up...')


def DRLSetup(site_name, slice_name, site_id, bw_limit, peer):
	DRL_file = '/vservers/%s/etc/drl.xml' % slice_name
	DRL_config = drl % (site_name, site_id, bw_limit, peer)
	
	# Check config changes
	if os.path.exists(DRL_file):
		import md5
		new_digest = md5.new(DRL_config).digest()
		old_digest = md5.new(open(DRL_file).read()).digest()
		if old_digest == new_digest:	
			logger.log('drl: %s already exists...' % DRL_file)
			DRLInstall(slice_name)
			return
	DRLConfig(DRL_file, DRL_config)
	DRLInstall(slice_name)


def DRLConfig(DRL_file, DRL_config):
	logger.log('drl: %s is out-dated...' % DRL_file)
	logger.log('drl: generating %s' % DRL_file)
	f = open( DRL_file, 'w')	
	f.write(DRL_config)
	f.close()


def DRLInstall(slice_name):
	if not os.path.exists('/vservers/%s/etc/yum.repos.d/myplc.repo' % slice_name):
		shutil.copyfile('/etc/yum.myplc.d/myplc.repo', '/vservers/%s/etc/yum.repos.d/myplc.repo' % slice_name)
		logger.log('drl: installing DistributedRateLimiting into %s slice' % slice_name)
		logger.log_call('vserver', '%s' % slice_name, 'suexec', '0', 'yum', 'install', '-y', '-q', 'DistributedRateLimiting')
		logger.log_call('vserver', '%s' % slice_name, 'suexec', '0', 'chkconfig', '--add', 'ulogd')
	else:	
		logger.log('drl: installing DistributedRateLimiting into %s slice' % slice_name)
		logger.log_call('vserver', '%s' % slice_name, 'suexec', '0', 'yum', 'update', '-y', '-q', 'DistributedRateLimiting')
		
	logger.log('drl: (re)starting DistributedRateLimiting service')
	logger.log_call('vserver', '%s' % slice_name, 'suexec', '0', 'service', 'ulogd', 'restart')


def GetSlivers(data, conf = None, plc = None):
	DRL_SLICE_NAME = ''
	HAVE_DRL = 0
	node_id = tools.node_id()

	for sliver in data['slivers']:
		for attribute in sliver['attributes']:
            		tag = attribute['tagname']
            		value = attribute['value']
			if tag == 'drl' and value == '1':
				HAVE_DRL = 1
				DRL_SLICE_NAME = sliver['name']

	if HAVE_DRL:
		site_id = plc.GetNodes({'node_id': int(node_id) }, ['site_id'])
		site_id = site_id[0]['site_id']

		q = plc.GetSites({'site_id': site_id, 'enabled': True, 'peer_site_id': None}, ['name', 'node_ids'])
		for i in q:
        		if i['node_ids'] != [] and len(i['node_ids']) > 1:
                		z = plc.GetNodeNetworks({'node_id': i['node_ids'], 'is_primary': True, '~bwlimit': None}, ['node_id', 'ip', 'bwlimit'])
				total_bwlimit = 0
                		peer = ''
				node_has_bwlimit = 0
                		for j in range(len(z)):
                                	total_bwlimit +=  z[j]['bwlimit']
					if z[j]['node_id'] != int(node_id):
                                		peer += '\t<peer>%s</peer>\n' % z[j]['ip']
					else:
						node_has_bwlimit = 1
				if node_has_bwlimit:
					DRLSetup(i['name'], DRL_SLICE_NAME, site_id, total_bwlimit/1000, peer)
				else:
					logger.log('drl: This node has no bwlimit')

			else:
				logger.log('drl: This site has only %s node' % len(i['node_ids']))
	else:
		logger.log('drl: This node has no drl slice!...')
