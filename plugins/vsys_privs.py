"""
vsys sub-configurator.  Maintains configuration parameters associated with vsys scripts.
All slice attributes with the prefix vsys_ are written into configuration files on the
node for the reference of vsys scripts.
"""

import logger
import os
from sets import Set

VSYS_PRIV_DIR = "/etc/planetlab/vsys-attributes"

def start(options, conf):
    logger.log("vsys_privs plugin v0.1")
    if (not os.path.exists(VSYS_PRIV_DIR)):
        os.makedirs(VSYS_PRIV_DIR)
        logger.log("Created vsys attributes dir")

def GetSlivers(data, config=None, plc=None):
    privs = {}

    # Parse attributes and update dict of scripts
    for sliver in data['slivers']:
        slice = sliver['name']
        for attribute in sliver['attributes']:
            tag = attribute['tagname']
            value = attribute['value']
            if tag.startswith('vsys_'):
                if (privs.has_key(slice)):
                    slice_priv = privs[slice]
                    if (slice_priv.has_key(tag)):
                        slice_priv[tag].append(value)
                    else:
                        slice_priv[tag]=[value]

                    privs[slice] = slice_priv
                else:
                    privs[slice] = {tag:[value]}

    cur_privs = read_privs()
    write_privs(cur_privs, privs)

def read_privs():
    cur_privs={}
    priv_finder = os.walk(VSYS_PRIV_DIR)
    priv_find = [i for i in priv_finder]
    (rootdir,slices,foo) = priv_find[0]

    for slice in slices:
        cur_privs[slice]={}

    if (len(priv_find)>1):
        for (slicedir,bar,tagnames) in priv_find[1:]:
            if (bar != []):
                # The depth of the vsys-privileges directory = 1
                pass

            for tagname in tagnames:
                tagfile = os.path.join(slicedir,tagname)
                values_n = file(tagfile).readlines()
                values = map(lambda s:s.rstrip(),values_n)
                slice = os.path.basename(slicedir)
                cur_privs[slice][tagname]=values

    return cur_privs

def write_privs(cur_privs,privs):
    for slice in privs.keys():
        variables = privs[slice]
        slice_dir = os.path.join(VSYS_PRIV_DIR,slice)
        if (not os.path.exists(slice_dir)):
            os.mkdir(slice_dir)

        # Add values that do not exist
        for k in variables.keys():
            v = variables[k]
            if (cur_privs.has_key(slice) 
                    and cur_privs[slice].has_key(k)
                    and cur_privs[slice][k] == v):
                # The binding has not changed
                pass
            else:
                v_file = os.path.join(slice_dir, k)
                f = open(v_file,'w')
                data = '\n'.join(v)
                f.write(data)
                f.close()
                logger.log("Added vsys attribute %s for %s"%(k,slice))

    # Remove files and directories 
    # that are invalid
    for slice in cur_privs.keys():
        variables = cur_privs[slice]
        slice_dir = os.path.join(VSYS_PRIV_DIR,slice)

        # Add values that do not exist
        for k in variables.keys():
            if (privs.has_key(slice) 
                    and cur_privs[slice].has_key(k)):
                # ok, spare this tag
                print "Sparing  %s, %s "%(slice,k) 
            else:
                v_file = os.path.join(slice_dir, k)
                os.remove(v_file)    

        if (not privs.has_key(slice)):
            os.rmdir(slice_dir)


if __name__ == "__main__":           
    test_slivers = {'slivers':[
        {'name':'foo','attributes':[
            {'tagname':'vsys_m','value':'2'},
            {'tagname':'vsys_m','value':'3'},
            {'tagname':'vsys_m','value':'4'}
            ]},
        {'name':'bar','attributes':[
            #{'tagname':'vsys_x','value':'z'}
            ]}
        ]}
    start(None,None)
    GetSlivers(test_slivers)
