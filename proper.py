"""Generate Proper configuration file"""

import os
import logger

def GetSlivers(data):
    # anyone can execute the get_file_flags operation (since it is applied
    # within the caller's vserver and the command lsattr gives the same
    # info anyway) or get the version string.  wait is harmless too since
    # the caller needs to know the child ID.  and we let any slice unmount
    # directories in its own filesystem, mostly as a workaround for some
    # Stork problems.
    buf = """
*: get_file_flags
*: version
*: wait
+: unmount
""".lstrip()

    for sliver in data['slivers']:
        for attribute in sliver['attributes']:
            if attribute['name'] == 'proper_op':
                buf += "%s: %s\n" % (sliver['name'], attribute['value'])

    try: os.makedirs("/etc/proper")
    except OSError: pass
    propd_conf = open("/etc/proper/propd.conf", "r+")

    if propd_conf.read() != buf:
        logger.log('proper: updating /etc/propd.conf')
        propd_conf.seek(0)
        propd_conf.write(buf)
        propd_conf.truncate()
        logger.log('proper: restarting proper')
        os.system('/etc/init.d/proper restart')

    propd_conf.close()

def start(options, config):
    pass
