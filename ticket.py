"""An extremely simple interface to the signing/verifying capabilities
of gnupg.

You must already have the key in the keyring.
"""

from subprocess import PIPE, Popen
from xmlrpclib import dumps, loads

GPG = '/usr/bin/gpg'


def sign(data):
    """Return <data> signed with the default GPG key."""
    msg = dumps((data,))
    p = _popen_gpg('--armor', '--sign', '--keyring', '/etc/planetlab/secring.gpg', '--no-default-keyring')
    p.stdin.write(msg)
    p.stdin.close()
    signed_msg = p.stdout.read()
    p.stdout.close()
    p.stderr.close()
    p.wait()
    return signed_msg

def verify(signed_msg):
    """If <signed_msg> is a valid signed document, return its contents.  Otherwise, return None."""
    p = _popen_gpg('--decrypt', '--keyring', '/usr/boot/pubring.gpg', '--no-default-keyring')
    p.stdin.write(signed_msg)
    p.stdin.close()
    msg = p.stdout.read()
    p.stdout.close()
    p.stderr.close()
    if p.wait(): return None  # verification failed
    else:
        data, = loads(msg)[0]
        return data

def _popen_gpg(*args):
    """Return a Popen object to GPG."""
    return Popen((GPG, '--batch', '--no-tty') + args, stdin=PIPE, stdout=PIPE, stderr=PIPE)
