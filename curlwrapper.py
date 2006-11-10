from subprocess import PIPE, Popen


class CurlException(Exception): pass

def retrieve(url, postdata=None):
    options = ('/usr/bin/curl', '--cacert', '/usr/boot/cacert.pem')
    if postdata: options += ('--data', '@-')
    p = Popen(options + (url,), stdin=PIPE, stdout=PIPE, stderr=PIPE)
    if postdata: p.stdin.write(postdata)
    p.stdin.close()
    data = p.stdout.read()
    err = p.stderr.read()
    rc = p.wait()
    if rc != 0: raise CurlException(err)
    else: return data
