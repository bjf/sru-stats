from launchpadlib.launchpad             import Launchpad
from ktl.kernel_series                  import KernelSeries
import yaml
import os

class LP():
    def __init__(self):
        client_name = 'NVIDIA tools'
        launchpad_cachedir = os.path.join(os.path.expanduser('~'), '.cache', client_name)
        launchpad_creddir  = os.path.join(os.path.expanduser('~'), '.config', client_name)
        filename_parts = ['credentials', 'production']

        launchpad_credentials_file = os.path.join(launchpad_creddir, '-'.join(filename_parts))

        if not os.path.exists(launchpad_creddir):
            os.makedirs(launchpad_creddir, 0o700)

        self.launchpad = Launchpad.login_with(client_name,
                                              service_root='production',
                                              launchpadlib_dir=launchpad_cachedir,
                                              credentials_file=launchpad_credentials_file,
                                              version='devel')

class LPBug(): # Launchpad Bug
    def __init__(self, bid=None):
        self.launchpad = LP().launchpad
        if bid is not None:
            self.lpbug = self.launchpad.bugs[bid]
        self._description = None

    @property
    def description(self):
        if self._description is None:
            self._description = self.lpbug.description
        return self._description

class KTB(LPBug): # Kernel Tracking Bug
    def __init__(self, bid):
        super().__init__(bid)
        self._swm_properties = None
        self._series = None
        self._package = None
        self._title = None
        self._build_ppas = None
        self._tags = None
        self._sru_cycle = None

    @property
    def id(self):
        return self.lpbug.id

    @property
    def title(self):
        self._title = self.lpbug.title if self._title is None else self._title
        return self._title

    @property
    def series(self):
        if self._series is None:
            series__and_package = self.title.split(':', 1)[0] if ':' in self.title else None
            self._series, self._package = series__and_package.split('/', 1) if '/' in series__and_package else None
        return self._series

    @property
    def package(self):
        if self._package is None:
            series__and_package = self.title.split(':', 1)[0] if ':' in self.title else None
            self._series, self._package = series__and_package.split('/', 1) if '/' in series__and_package else None
        return self._package

    @property
    def owner(self):
        return "None" if self.lpbug.owner is None else self.lpbug.owner.display_name

    @property
    def date_created(self):
        return self.lpbug.date_created

    @property
    def date_last_message(self):
        return self.lpbug.date_last_message

    @property
    def date_last_updated(self):
        return self.lpbug.date_last_updated

    @property
    def duplicate_of(self):
        return self.lpbug.duplicate_of

    @property
    def activity(self):
        return self.lpbug.activity

    @property
    def swm_properties(self):
        if self._swm_properties is None:
            try:
                _, props = self.description.split('-- swm properties --', 1)
                self._swm_properties = yaml.safe_load(props)
            except ValueError:
                pass
        return self._swm_properties

    @property
    def packages_and_versions(self):
        pv = {}
        if False:
            for pkg in self.swm_properties['packages']:
                try:
                    pv[self.swm_properties['packages'][pkg]] = self.swm_properties['versions'][pkg]
                except KeyError:
                    pass
        for pkg in self.swm_properties['packages']:
            pv[self.swm_properties['packages'][pkg]] = '0.0'
        return pv

    @property
    def build_ppas(self):
        if self._build_ppas is None:
            ks = KernelSeries().lookup_series(codename=self.series)
            src = ks.lookup_source(self.package)
            route = src.routing.lookup_route('build').routing.name
            route_table = ks.routing_table[route]['build']

            self._build_ppas = []
            for x in route_table:
                team, _, ppa = x[0].replace('ppa:', '').split('/')
                self._build_ppas.append([team, ppa])
        return self._build_ppas

    @property
    def tags(self):
        if self._tags is None:
            self._tags = self.lpbug.tags
        return self._tags

    @property
    def sru_cycle(self):
        if self._sru_cycle is None:
            for tag in self.tags:
                if tag.startswith('kernel-sru-cycle-'):
                    (self._sru_cycle, self._sru_cycle_spin) = tag.replace('kernel-sru-cycle-', '').split('-', 1)
                    break
        return self._sru_cycle

# vi:set ts=4 sw=4 expandtab:
