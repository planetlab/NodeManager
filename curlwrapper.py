from subprocess import PIPE, Popen


class CurlException(Exception): pass

def retrieve(url, cacert=None, postdata=None, timeout=300):
    options = ('/usr/bin/curl', '--fail', '--silent')
    if cacert: options += ('--cacert', cacert)
    if postdata: options += ('--data', '@-')
    if timeout: options += ('--max-time', str(timeout))
    p = Popen(options + (url,), stdin=PIPE, stdout=PIPE, stderr=PIPE, close_fds=True)
    if postdata: p.stdin.write(postdata)
    p.stdin.close()
    data = p.stdout.read()
    err = p.stderr.read()
    rc = p.wait()
    if rc != 0: raise CurlException(err)
    else: return data
