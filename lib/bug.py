#!/usr/bin/env python3
#

from lib.launchpad                      import Launchpad
from lib.bugzdb                         import BugzDB
from datetime                           import datetime, timezone, timedelta
import re
import yaml

SeriesOrder = [
    'noble',
    'jammy',
    'focal',
    'eoan',
    'disco',
    'bionic',
    'xenial',
    'trusty',
    'precise'
]

epoch = datetime(2009, 3, 2, 0, 0, tzinfo=timezone.utc)
def timestamp(mark):
    try:
        delta = int((mark - epoch).total_seconds())
    except TypeError:
        delta = 0
    return delta

def date_of_timestamp(ts):
    date = epoch + timedelta(seconds=ts)
    return date

def problem_type(lpbug):
    """
    Look in the bug description to see if we can determine the type of problem
    that the bug is about. We are looking for a "ProblemType:" line in the
    description to help.
    """
    retval = 'unknown'
    for line in lpbug.description.split('\n'):
        m = re.search(r'ProblemType:\s*(.*)', line)
        if m is not None:
            retval = m.group(1)
    return retval

def comments(lpbug):
    retval = []

    messages = lpbug.messages_collection
    for message in messages:
        msg = {
            'content'            : message.content,
            'created'            : timestamp(message.date_created),
            'owner'              : message.owner.name,
            'owner_display_name' : message.owner.display_name,
            'subject'            : message.subject,
            'id'                 : lpbug.id,
        }

        retval.append(msg)

    return retval

def title_v1_decode(title):
    #                              .- package name (group(1))
    #                             /           .- kernel version (group(2))
    #                            /           /          .- version/abi separator (group(3))
    #                           /           /          /
    ver_rc     = re.compile(r"(\S+): (\d+\.\d+\.\d+)([-\.])(\d+)\.(\d+)([~a-z\d.]*)")
    #                                                       /      /       /
    #                                                      /      /       .- backport extra (m.group(6))
    #                                                     /      .- upload number (m.group(5))
    #                                                    .- abi (group(4))
    if 'version to be filled' not in title:
        m = ver_rc.search(title)
        if m is not None:
            package = m.group(1)
            version = '%s%s%s.%s%s' % (m.group(2), m.group(3), m.group(4), m.group(5), m.group(6))
            return None, package, version

def title_v2_decode(title):
    # Title: [<series>/]<package>: <version> <junk>
    #
    # If the series is absent it will report None, if the version is
    # unspecified it will report as None.
    #
    #                                 .- optional series (group(1))
    #                                 |       .- package (group(2))
    #                                 |       |             .- version (group(3))
    #                                 |       |             |
    title2spv_rc = re.compile(r'^(?:(\S+)/)?(\S+): (?:(\d+\.\d+\.\S+)|<version to be filled>)')

    match = title2spv_rc.search(title)
    if not match:
        print('title invalid: <{}>'.format(title))
        return None, None, None

    (series, package, version) = match.groups()
    return series, package, version

def obtain_series_package_version(bug):
    series_codenames = [
        'precise',
        'trusty',
        'xenial',
        'yakkety',
        'zesty',
        'artful',
        'bionic',
        'cosmic',
        'disco',
        'eoan',
        'focal',
        'jammy',
        'noble',
    ]

    series, package, version = title_v2_decode(bug.title)
    if not series:
        for tag in bug.tags:
            if tag in series_codenames:
                series = tag
                break

    return series, package, version

class SRUCycleStats():
    def __init__(self):
        self.id                    = ''
        self.cycle                 = ''
        self.series                = ''
        self.package               = ''
        self.variant               = ''
        self.total                 = 0
        self.ready                 = 0
        self.waiting               = 0
        self.crank                 = 0
        self.build                 = 0
        self.review_start          = 0
        self.review                = 0
        self.regression_testing    = 0
        self.verification_testing  = 0
        self.certification_testing = 0

    def load(self, id):
        q = 'select * from sru_cycle_stats where id = "%s"' % (id)
        db = BugzDB()
        rec = db.fetch_one(q)

        self.id                    = rec['id']
        self.cycle                 = rec['cycle']
        self.series                = rec['series']
        self.package               = rec['package']
        self.variant               = rec['variant']
        self.total                 = rec['total']
        self.ready                 = rec['ready']
        self.waiting               = rec['waiting']
        self.crank                 = rec['crank']
        self.build                 = rec['build']
        self.review_start          = rec['review_start']
        self.review                = rec['review']
        self.regression_testing    = rec['regression_testing']
        self.verification_testing  = rec['verification_testing']
        self.certification_testing = rec['certification_testing']
        return self

    def store(self):
        db = BugzDB()
        db.update_sru_cycle_stats_table(self)

class BugTask():
    def __init__(self):
        self.id                    = ''
        self.assignee              = ''
        self.status                = ''
        self.importance            = ''
        self.date_created          = ''
        self.date_fix_committed    = ''
        self.date_confirmed        = ''
        self.date_assigned         = ''
        self.date_closed           = ''
        self.date_fix_released     = ''
        self.date_in_progress      = ''
        self.date_incomplete       = ''
        self.date_left_closed      = ''
        self.date_left_new         = ''
        self.date_triaged          = ''
        self.is_complete           = ''
        self.owner                 = ''
        self.title                 = ''
        self.milestone             = ''
        self.name                  = ''
        pass

class BugTaskDB(BugTask):
    def __init__(self, record):
        super(BugTask, self).__init__()
        self.id                    = record['id']
        self.assignee              = record['assignee']
        self.status                = record['status']
        self.importance            = record['importance']
        self.date_created          = record['date_created']
        self.date_confirmed        = record['date_confirmed']
        self.date_assigned         = record['date_assigned']
        self.date_closed           = record['date_closed']
        self.date_fix_committed    = record['date_fix_committed']
        self.date_fix_released     = record['date_fix_released']
        self.date_in_progress      = record['date_in_progress']
        self.date_incomplete       = record['date_incomplete']
        self.date_left_closed      = record['date_left_closed']
        self.date_left_new         = record['date_left_new']
        self.date_triaged          = record['date_triaged']
        self.is_complete           = record['is_complete']
        self.owner                 = record['owner']
        self.title                 = record['title']
        self.milestone             = record['milestone']
        self.name                  = record['name']

class BugTaskLP(BugTask):
    def __init__(self, lptask):
        super(BugTask, self).__init__()
        self.id                    = lptask.bug.id
        self.assignee              = lptask.assignee.name if lptask.assignee else ''
        self.status                = lptask.status
        self.importance            = lptask.importance
        self.date_created          = timestamp(lptask.date_created)
        self.date_confirmed        = timestamp(lptask.date_confirmed)
        self.date_assigned         = timestamp(lptask.date_assigned)
        self.date_triaged          = timestamp(lptask.date_triaged)
        self.date_in_progress      = timestamp(lptask.date_in_progress)
        self.date_closed           = timestamp(lptask.date_closed)
        self.date_fix_committed    = timestamp(lptask.date_fix_committed)
        self.date_fix_released     = timestamp(lptask.date_fix_released)
        self.date_incomplete       = timestamp(lptask.date_incomplete)
        self.date_left_closed      = timestamp(lptask.date_left_closed)
        self.date_left_new         = timestamp(lptask.date_left_new)
        self.is_complete           = lptask.is_complete
        self.owner                 = lptask.owner.name
        self.owner_display_name    = lptask.owner.display_name
        self.title                 = lptask.title
        self.milestone             = lptask.milestone if lptask.milestone else ''
        self.name                  = lptask.bug_target_name

class Bug():
    def __init__(self):
        self.bdb = BugzDB()

        self.id                 = ''
        self.title              = ''
        self.owner              = ''
        self.created            = ''
        self.last_message       = ''
        self.last_updated       = ''
        self.private            = ''
        self.security           = ''
        self.duplicate          = ''
        self.heat               = ''
        self.is_expirable       = ''
        self.problem_type       = ''
        self.owner_display_name = ''
        self.description        = ''
        self.master_bug_id      = ''
        self.cycle              = ''
        self.spin               = ''
        self.series             = ''
        self.package            = ''
        self.version            = ''
        self.variant            = ''
        self.tasks              = {}
        self.tags               = []

    def load(self, bid):
        '''
        Instantiate a Bug object from data in the bugz database.
        '''
        q = 'select * from bugs where id = %s' % bid
        rec = self.bdb.fetch_one(q)
        self.id                 = rec['id']
        self.title              = rec['title']
        self.owner              = rec['owner']
        self.created            = rec['created']
        self.date_created       = str(date_of_timestamp(rec['created']))
        self.last_message       = rec['last_message']
        self.date_last_message  = str(date_of_timestamp(rec['last_message']))
        self.last_updated       = rec['last_updated']
        self.date_last_updated  = str(date_of_timestamp(rec['last_updated']))
        self.private            = rec['private']
        self.security           = rec['security']
        self.duplicate          = rec['duplicate']
        self.heat               = rec['heat']
        self.is_expirable       = rec['is_expirable']
        self.problem_type       = rec['problem_type']
        self.owner_display_name = rec['owner_display_name']
        self.description        = rec['description']
        self.master_bug_id      = rec['master_bug_id']
        self.cycle              = rec['cycle']
        self.spin               = rec['spin']
        self.series             = rec['series']
        self.package            = rec['package']
        self.version            = rec['version']
        self.variant            = rec['variant']

        q = 'select * from tags where id = %s' % bid
        recs = self.bdb.fetch_all(q)
        for rec in recs:
            self.tags.append(rec['tag'])

        self.tasks = {}
        q = 'select * from tasks where id=%s' % self.id
        tasks = self.bdb.fetch_all(q)
        for rec in tasks:
            q = 'select * from %s where id=%s' % (rec['tbl'], self.id)
            tasks = self.bdb.fetch_all(q)
            for task in tasks:
                self.tasks[task['name'].replace('kernel-sru-workflow/', '')] = BugTaskDB(task)

        return self

    def load_from_lp(self, bugid, lp=None):
        if lp is None:
            lp = Launchpad('bugz')
        lpbug = lp.service.bugs[bugid]
        self.id                 = lpbug.id
        self.title              = lpbug.title
        self.owner              = lpbug.owner.name
        self.owner_display_name = lpbug.owner.display_name
        self.created            = timestamp(lpbug.date_created)
        self.last_message       = timestamp(lpbug.date_last_message)
        self.last_updated       = timestamp(lpbug.date_last_updated)
        self.private            = lpbug.private
        self.security           = lpbug.security_related
        self.duplicate          = lpbug.duplicate_of
        self.heat               = lpbug.heat
        self.is_expirable       = lpbug.isExpirable()
        self.problem_type       = problem_type(lpbug)
        self.description        = lpbug.description
        self.tags               = lpbug.tags

        # ____________________________________________________________________________
        #
        # Determine the cycle and the spin #
        #
        for tag in self.tags:
            if tag.startswith('kernel-sru-cycle-'):
                tag = tag.replace('kernel-sru-cycle-devel-', '').replace('kernel-sru-cycle-', '')
                try:
                    (self.cycle, self.spin) = tag.split('-')
                except ValueError:
                    self.cycle = tag
                    self.spin = '0'
                break

        # ____________________________________________________________________________
        #
        # Determine the master bug #
        #
        desc = self.description
        ys   = desc.partition('\n-- swm properties --\n')[2]
        if ys != '':
            # Everything beyond "-- swm properties --" is supposed to be yaml
            # format. However Launchpad will convert leading spaces after manual
            # updates into non-breaking spaces (0xa0) which breaks yaml parsing.
            #
            ys = ys.replace('\xa0', ' ')
            wf_properties = yaml.safe_load(ys)
            try:
                self.master_bug_id = wf_properties['kernel-stable-master-bug']
            except:
                pass

            try:
                self.variant = wf_properties['variant']
            except:
                self.variant = 'debs'

        # ____________________________________________________________________________
        #
        # Determine the series, package and kernel version
        #
        self.series, self.package, self.version = obtain_series_package_version(self)

        for lptask in lpbug.bug_tasks:
            bt = BugTaskLP(lptask)
            # self.tasks[bt.name] = bt
            self.tasks[bt.name.replace('kernel-sru-workflow/', '')] = bt

        history_tasks = self.__extract_task_status_dates(lpbug)
        for task in history_tasks:
            for status in history_tasks[task]:
                match status:
                    case 'New'          :
                        try:
                            self.tasks[task].date_new           = history_tasks[task][status]
                        except KeyError: pass
                    case 'Confirmed'    :
                        try:
                            self.tasks[task].date_confirmed     = history_tasks[task][status]
                        except KeyError: pass
                    case 'Opinion'      : pass
                    case 'Triaged'      :
                        try:
                            self.tasks[task].date_triaged       = history_tasks[task][status]
                        except KeyError:
                            pass
                    case 'In Progress'  :
                        try:
                            self.tasks[task].date_triaged       = history_tasks[task][status]
                        except KeyError: pass
                    case 'Fix Committed':
                        try:
                            self.tasks[task].date_fix_committed = history_tasks[task][status]
                        except KeyError: pass
                    case 'Fix Released' :
                        try:
                            self.tasks[task].date_fix_released  = history_tasks[task][status]
                        except KeyError: pass

        return self

    def __extract_task_status_dates(self, bug):
        tasks = {}

        history = bug.activity
        for activity in history:
            if activity.whatchanged.endswith('status'):
                task = activity.whatchanged.split(':', 1)[0]
                if task.startswith('kernel-sru-workflow') and '/' in task:
                    task = task.split('/')[1]
                tasks.setdefault(task, {})
                # tasks[task][activity.newvalue] = str(activity.datechanged).split('.', 1)[0]
                tasks[task][activity.newvalue] = timestamp(activity.datechanged)
        return tasks

    def store(self):
        db = BugzDB()
        db.update_bugs_table(self)
        db.update_tasks_tables(self)

class BugHelper():
    def __init__(self):
        self.bdb = BugzDB()

    def query(self, q):
        recs = self.bdb.fetch_all(q)
        for rec in recs:
            yield rec

    def stable_cycles(self):
        q = 'select distinct cycle from bugs order by cycle;'
        recs = self.bdb.fetch_all(q)
        for rec in recs:
            if not rec['cycle'] or rec['cycle'].startswith('d') or rec['cycle'] == 'None':
                continue
            yield rec['cycle']

    def cycle_bugs(self, cycle):
        q = 'select id from bugs where cycle = "%s" order by id;' % cycle
        recs = self.bdb.fetch_all(q)
        for rec in recs:
            yield rec['id']

    def bugs_in_cycle(self, cycle):
        q = 'select id from bugs where cycle = "%s" order by series;' % cycle
        recs = self.bdb.fetch_all(q)
        for rec in recs:
            yield Bug().load(rec['id'])

    def series_in_cycle(self, cycle):
        q = 'select distinct series from bugs where cycle = "%s" order by series;' % cycle
        recs = self.bdb.fetch_all(q)
        for rec in recs:
            yield rec['series']

    def bugs_in_cycle_and_series(self, cycle, series):
        q = 'select id from bugs where cycle = "%s" and series = "%s" and variant = "debs" order by package;' % (cycle, series)
        recs = self.bdb.fetch_all(q)
        for rec in recs:
            yield Bug().load(rec['id'])

    def series_in_cycle_ex(self, cycle):
        cycle_series = []
        q = 'select distinct series from sru_cycle_stats where cycle = "%s" order by series;' % cycle
        recs = self.bdb.fetch_all(q)
        for rec in recs:
            cycle_series.append(rec['series'])

        for series in SeriesOrder:
            if series in cycle_series:
                yield series

    def stats_in_cycle_and_series(self, cycle, series):
        q = 'select * from sru_cycle_stats where cycle = "%s" and series = "%s" and variant = "debs" order by package;' % (cycle, series)
        recs = self.bdb.fetch_all(q)
        for rec in recs:
            # yield SRUCycleStats().load(cycle, series, rec['package'])
            yield SRUCycleStats().load(rec['id'])

