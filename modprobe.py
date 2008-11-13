#
# $Id$
#

"""Modprobe is a utility to read/modify/write /etc/modprobe.conf"""

import os

class Modprobe():
    def __init__(self,filename="/etc/modprobe.conf"):
        self.conffile = {}
        self.origconffile = {}
        for keyword in ("alias","options","install","remove","blacklist","MODULES"):
            self.conffile[keyword]={}
        self.filename = filename

    def input(self,filename=None):
        if filename==None: filename=self.filename
        fb = file(filename,"r")
        for line in fb.readlines():
            parts = line.split()
            command = parts[0].lower()

            table = self.conffile.get(command,None)
            if table == None:
                print "WARNING: command %s not recognize. Ignoring!" % command
                continue

            if command == "alias":
                wildcard=parts[1]
                modulename=parts[2]
                self.aliasset(wildcard,modulename)
                options=''
                if len(parts)>3:
                    options=" ".join(parts[3:])
                    self.optionsset(modulename,options)
                    self.conffile['MODULES']={}
                self.conffile['MODULES'][modulename]=options
            else:
                modulename=parts[1]
                rest=" ".join(parts[2:])
                self._set(command,modulename,rest)
                if command == "options":
                    self.conffile['MODULES'][modulename]=rest

        self.origconffile = self.conffile.copy()
                
    def _get(self,command,key):
        return self.conffile[command].get(key,None)

    def _set(self,command,key,value):
        self.conffile[command][key]=value

    def aliasget(self,key):
        return self._get('alias',key)

    def optionsget(self,key):
        return self._get('options',key)

    def aliasset(self,key,value):
        self._set("alias",key,value)

    def optionsset(self,key,value):
        self._set("options",key,value)
        
    def _comparefiles(self,a,b):
        try:
            if not os.path.exists(a): return False
            fb = open(a)
            buf_a = fb.read()
            fb.close()

            if not os.path.exists(b): return False
            fb = open(b)
            buf_b = fb.read()
            fb.close()

            return buf_a == buf_b
        except IOError, e:
            return False

    def output(self,filename="/etc/modprobe.conf",program="NodeManager"):
        tmpnam = os.tmpnam()
        fb = file(tmpnam,"w")
        fb.write("# Written out by %s\n" % program)

        for command in ("alias","options","install","remove","blacklist"):
            table = self.conffile[command]
            keys = table.keys()
            keys.sort()
            for k in keys:
                v = table[k]
                fb.write("%s %s %s\n" % (command,k,v))

        fb.close()
        if not self._comparefiles(tmpnam,filename):
            os.rename(tmpnam,filename)
            os.chmod(filename,0644)
            return True
        else:
            return False

    def probe(self,name):
        o = os.popen("/sbin/modprobe %s" % name)
        o.close()

    def checkmodules(self):
        syspath="/sys/module"
        modules = os.listdir(syspath)
        for module in modules:
            path="%/%s/parameters"%(syspath,module)
            if os.path.exists(path):
                ps=os.listdir(path)
                parameters={}
                for p in ps:
                    fb = file("%s/%s"%(path,p),"r")
                    parameters[p]=fb.readline()
                    fb.close()
         
if __name__ == '__main__':
    import sys
    if len(sys.argv)>1:
        m = Modprobe(sys.argv[1])
    else:
        m = Modprobe()

    m.input()
    m.aliasset("bond0","bonding")
    m.optionsset("bond0","miimon=100")
    m.output("/tmp/x")
