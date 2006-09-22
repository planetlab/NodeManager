"""Global parameters and configuration."""

try:
    from bwlimit import bwmin, bwmax

    DEFAULT_RSPEC = {'nm_cpu_share': 32, 'nm_cpu_guaranteed_share': 0,
                     'nm_disk_quota': 5000000,
                     'nm_enabled': 1,
                     'nm_net_min_rate': bwmin, 'nm_net_max_rate': bwmax,
                     'nm_net_exempt_min_rate': bwmin,
                     'nm_net_exempt_max_rate': bwmax,
                     'nm_net_share': 1}
except ImportError: pass

API_SERVER_PORT = 812

DB_FILE = '/root/pl_node_mgr_db.pickle'

KEY_FILE = '/home/deisenst/nm/key.pem'

LOANABLE_RESOURCES = set(['nm_cpu_share', 'nm_cpu_guaranteed_share',
                          'nm_net_max_rate', 'nm_net_exempt_max_rate',
                          'nm_net_share'])

LOG_FILE = '/var/log/pl_node_mgr.log'

PID_FILE = '/var/run/pl_node_mgr.pid'

SA_HOSTNAME = 'plc-a.demo.vmware'

START_DELAY_SECS = 10

TICKET_SERVER_PORT = 1813
