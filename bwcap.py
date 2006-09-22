import bwlimit

import logger
import tools


_old_rec = {}

def update(rec):
    global _old_rec
    if rec != _old_rec:
        if rec['cap'] != _old_rec.get('cap'):
            logger.log('setting node bw cap to %d' % rec['cap'])
#             bwlimit.init('eth0', rec['cap'])
        if rec['exempt_ips'] != _old_rec.get('exempt_ips'):
            logger.log('initializing exempt ips to %s' % rec['exempt_ips'])
#             bwlimit.exempt_init('Internet2', rec['exempt_ips'])
        _old_rec = tools.deepcopy(rec)
