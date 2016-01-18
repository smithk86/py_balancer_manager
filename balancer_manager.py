import re
import requests
import argparse
import logging
from bs4 import BeautifulSoup


""" balancer_manager.py: Library for programatically interacting with Apache's mod_proxy_balancer management interface """

__author__ = "Kyle Smith"
__email__ = "smithk86@gmail.com"
__license__ = "GPL"
__version__ = "1.0.1"

# redirect urllib3 warning to logging module
logging.captureWarnings(True)


def _get_print_value(val):
    if val is None:
        return ''
    elif type(val) is bool:
        if val:
            return 'on'
        else:
            return 'off'
    else:
        return val


class ApacheBalancerManager:

    def __init__(self, url, verify_ssl_cert=True, username=None, password=None):
        self.url = url
        self.verify_ssl_cert = verify_ssl_cert
        self.auth_username = username
        self.auth_password = password
        self.apache_version = None

        self.session = requests.Session()
        self.session.headers.update({'User-agent': 'balancer_manager.py/{version}'.format(version=__version__)})
        if self.auth_username and self.auth_password:
            self.session.auth = (self.auth_username, self.auth_password)

        page = self._get_soup_html()
        full_version_string = page.find('dt').string
        match = re.match(r'^Server\ Version:\ Apache/([\.0-9]*)', full_version_string)
        if match:
            self.apache_version = match.group(1)

        if self.apache_version is None:
            raise TypeError('apache version parse failed')

    def _get_soup_html(self):
        req = self.session.get(self.url, verify=self.verify_ssl_cert)
        return BeautifulSoup(req.text, 'html.parser')

    def get_routes(self):
        page = self._get_soup_html()
        session_nonce_uuid_pattern = re.compile(r'.*&nonce=([-a-f0-9]{36}).*')
        cluster_name_pattern = re.compile(r'.*\?b=(.*?)&.*')

        routes = []
        tables = page.find_all('table')

        # only iterate through even tables
        # odd tables contain data about the cluster itself
        for table in tables[1::2]:
            for row in table.find_all('tr'):
                route = row.find_all('td')
                if len(route) > 0:
                    cells = row.find_all('td')
                    worker_url = cells[0].find('a')['href']
                    session_nonce_uuid = None
                    cluster_name = None

                    if worker_url:

                        session_nonce_uuid_match = session_nonce_uuid_pattern.search(worker_url)
                        if session_nonce_uuid_match:
                            session_nonce_uuid = session_nonce_uuid_match.group(1)

                        cluster_name_match = cluster_name_pattern.search(worker_url)
                        if cluster_name_match:
                            cluster_name = cluster_name_match.group(1)

                    routes.append({
                        'url': cells[0].find('a').string,
                        'route': cells[1].string,
                        'route_redir': cells[2].string,
                        'factor': cells[3].string,
                        'set': cells[4].string,
                        'status_init': 'Init' in cells[5].string,
                        'status_ignore_errors': 'Ign' in cells[5].string,
                        'status_draining_mode': 'Drn' in cells[5].string,
                        'status_disabled': 'Dis' in cells[5].string,
                        'status_hot_standby': 'Stby' in cells[5].string,
                        'elected': cells[6].string,
                        'busy': cells[7].string,
                        'load': cells[8].string,
                        'to': cells[9].string,
                        'from': cells[10].string,
                        'session_nonce_uuid': session_nonce_uuid,
                        'cluster': cluster_name
                    })

        return routes

    def change_route_status(self, route, status_ignore_errors=None, status_draining_mode=None, status_disabled=None, status_hot_standby=None):

        if type(status_ignore_errors) is bool:
            route['status_ignore_errors'] = status_ignore_errors
        if type(status_draining_mode) is bool:
            route['status_draining_mode'] = status_draining_mode
        if type(status_disabled) is bool:
            route['status_disabled'] = status_disabled
        if type(status_hot_standby) is bool:
            route['status_hot_standby'] = status_hot_standby

        post_data = {
            'w_lf': '1',
            'w_ls': '0',
            'w_wr': route['route'],
            'w_rr': '',
            'w_status_I': int(route['status_ignore_errors']),
            'w_status_N': int(route['status_draining_mode']),
            'w_status_D': int(route['status_disabled']),
            'w_status_H': int(route['status_hot_standby']),
            'w': route['url'],
            'b': route['cluster'],
            'nonce': route['session_nonce_uuid']
        }

        self.session.post(self.url, data=post_data, verify=self.verify_ssl_cert)

    def print_routes(self):

        rows = [[
            'Cluster',
            'Worker URL',
            'Route',
            'Route Redir',
            'Factor',
            'Set',
            'Status: Init',
            'Status: Ign',
            'Status: Drn',
            'Status: Dis',
            'Status: Stby',
            'Elected',
            'Busy',
            'Load',
            'To',
            'From',
            'Session Nonce UUID'
        ]]

        for route in self.get_routes():
            rows.append([
                _get_print_value(route['cluster']),
                _get_print_value(route['url']),
                _get_print_value(route['route']),
                _get_print_value(route['route_redir']),
                _get_print_value(route['factor']),
                _get_print_value(route['set']),
                _get_print_value(route['status_init']),
                _get_print_value(route['status_ignore_errors']),
                _get_print_value(route['status_draining_mode']),
                _get_print_value(route['status_disabled']),
                _get_print_value(route['status_hot_standby']),
                _get_print_value(route['elected']),
                _get_print_value(route['busy']),
                _get_print_value(route['load']),
                _get_print_value(route['to']),
                _get_print_value(route['from']),
                _get_print_value(route['session_nonce_uuid'])
            ])

        widths = [max(map(len, col)) for col in zip(*rows)]
        for row in rows:
            print(' | '.join((val.ljust(width) for val, width in zip(row, widths))))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('balance-manager-url')
    parser.add_argument('-l', '--list', dest='list_routes', action='store_true', default=False)
    parser.add_argument('-c', '--cluster')
    parser.add_argument('-r', '--route')
    parser.add_argument('--enable', action='store_true', default=False)
    parser.add_argument('--disable', action='store_true', default=False)
    parser.add_argument('-u', '--username', default=None)
    parser.add_argument('-p', '--password', default=None)
    parser.add_argument('--no-check-certificate', dest='no_check_certificate', action='store_true', default=False)
    args = parser.parse_args()

    abm = ApacheBalancerManager(getattr(args, 'balance-manager-url'), verify_ssl_cert=not args.no_check_certificate, username=args.username, password=args.password)
    routes = abm.get_routes()

    if args.enable and args.disable:
        raise ValueError('--enable and --disable are incompatible')

    if args.list_routes:
        abm.print_routes()

    elif args.enable or args.disable:

        if args.cluster is None or args.route is None:
            raise ValueError('--cluster and --route are required')

        for route in routes:
            if route['cluster'] == args.cluster and route['route'] == args.route:
                status_disabled = True if args.disable else False
                abm.change_route_status(route, status_disabled=status_disabled)


if __name__ == '__main__':
    main()
