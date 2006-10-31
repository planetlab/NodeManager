import xmlrpclib
import hmac, sha

class PLCAPI:
    """
    Wrapper around xmlrpclib.ServerProxy to automagically add an Auth
    struct as the first argument to every XML-RPC call. Initialize
    auth with either:

    (node_id, key) => BootAuth
    or
    session => SessionAuth

    To authenticate using the Boot Manager authentication method, or
    the new session-based method.
    """

    def __init__(self, uri, auth, **kwds):
        if isinstance(auth, (tuple, list)):
            (self.node_id, self.key) = auth
            self.session = None
        else:
            self.node_id = self.key = None
            self.session = auth

        self.server = xmlrpclib.ServerProxy(uri, allow_none = 1, **kwds)

    def add_auth(self, function):
        """
        Returns a wrapper which adds an Auth struct as the first
        argument when the function is called.
        """

        def canonicalize(args):
            """
            BootAuth canonicalization method. Parameter values are
            collected, sorted, converted to strings, then hashed with
            the node key.
            """

            values = []

            for arg in args:
                if isinstance(arg, list) or isinstance(arg, tuple):
                    # The old implementation did not recursively handle
                    # lists of lists. But neither did the old API itself.
                    values += self.canonicalize(arg)
                elif isinstance(arg, dict):
                    # Yes, the comments in the old implementation are
                    # misleading. Keys of dicts are not included in the
                    # hash.
                    values += self.canonicalize(arg.values())
                else:
                    # We use unicode() instead of str().
                    values.append(unicode(arg))

            return values

        def wrapper(*params):
            """
            Adds an Auth struct as the first argument when the
            function is called.
            """

            if self.session is not None:
                # Use session authentication
                auth = {'session': self.session}
            else:
                # Yes, this is the "canonicalization" method used.
                args = canonicalize(params)
                args.sort()
                msg = "[" + "".join(args) + "]"

                # We encode in UTF-8 before calculating the HMAC, which is
                # an 8-bit algorithm.
                digest = hmac.new(self.key, msg.encode('utf-8'), sha).hexdigest()

                auth = {'AuthMethod': "hmac",
                        'node_id': self.node_id,
                        'value': digest}

            # Automagically add auth struct to every call
            params = (auth,) + params

            return function(*params)

        return wrapper

    def __getattr__(self, methodname):
        function = getattr(self.server, methodname)
        return self.add_auth(function)
