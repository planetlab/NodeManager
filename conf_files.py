"""configuration files"""

import grp
import os
import pwd
import sha
import string
import threading

import curlwrapper
import logger
import tools


class conf_files:
    def __init__(self, config, noscripts=False):
        self.config = config
        self.noscripts = noscripts
        self.cond = threading.Condition()
        self.data = None

    def checksum(self, path):
        try:
            f = open(path)
            try: return sha.new(f.read()).digest()
            finally: f.close()
        except IOError: return None

    def system(self, cmd):
        if not self.noscripts and cmd:
            logger.log('conf_files: running command %s' % cmd)
            return os.system(cmd)
        else: return 0

    def update_conf_file(self, cf_rec):
        if not cf_rec['enabled']: return
        dest = cf_rec['dest']
        # XXX Remove once old Node Manager is out of service
        if dest == '/etc/proper/propd.conf': return
        err_cmd = cf_rec['error_cmd']
        mode = string.atoi(cf_rec['file_permissions'], base=8)
        uid = pwd.getpwnam(cf_rec['file_owner'])[2]
        gid = grp.getgrnam(cf_rec['file_group'])[2]
        url = 'https://%s/%s' % (self.config.PLC_BOOT_HOST, cf_rec['source'])
        contents = curlwrapper.retrieve(url, self.config.cacert)
        if not cf_rec['always_update'] and sha.new(contents).digest() == self.checksum(dest):
            return
        if self.system(cf_rec['preinstall_cmd']):
            self.system(err_cmd)
            if not cf_rec['ignore_cmd_errors']: return
        logger.log('conf_files: installing file %s from %s' % (dest, url))
        try: os.makedirs(os.path.dirname(dest))
        except OSError: pass
        tools.write_file(dest, lambda f: f.write(contents), mode=mode, uidgid=(uid,gid))
        if self.system(cf_rec['postinstall_cmd']): self.system(err_cmd)

    def run_once(self, data):
        for f in data['conf_files']:
            try: self.update_conf_file(f)
            except: logger.log_exc()

    def run(self):
        while True:
            self.cond.acquire()
            while self.data == None: self.cond.wait()
            data = self.data
            self.data = None
            self.cond.release()
            self.run_once(data)

    def callback(self, data):
        if data != None:
            self.cond.acquire()
            self.data = data
            self.cond.notify()
            self.cond.release()

main = None

def start(options, config):
    global main
    main = conf_files(config)
    tools.as_daemon_thread(main.run)

def GetSlivers(data):
    global main
    assert main is not None
    return main.callback(data)

if __name__ == '__main__':
    import optparse
    parser = optparse.OptionParser()
    parser.add_option('-f', '--config', action='store', dest='config', default='/etc/planetlab/plc_config', help='PLC configuration file')
    parser.add_option('-k', '--session', action='store', dest='session', default='/etc/planetlab/session', help='API session key (or file)')
    parser.add_option('--noscripts', action='store', dest='noscripts', default=False, help='Do not run pre- or post-install scripts')
    (options, args) = parser.parse_args()

    # Load /etc/planetlab/plc_config
    from config import Config
    config = Config(options.config)

    # Load /etc/planetlab/session
    if os.path.exists(options.session):
        session = file(options.session).read().strip()
    else:
        session = options.session

    # Initialize XML-RPC client
    from plcapi import PLCAPI
    plc = PLCAPI(config.plc_api_uri, config.cacert, auth = session)

    main = conf_files(config, options.noscripts)
    data = plc.GetSlivers()
    main.run_once(data)
