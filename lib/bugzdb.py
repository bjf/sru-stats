#!/usr/bin/env python3

import os
import sqlite3

class SQLBase():

    # __init__
    #
    def __init__(self, db):
        try:
            self.sql = sqlite3.connect(db)
            self.sql.row_factory = sqlite3.Row
        except Exception as e:
            self.sql.rollback()
            self.sql.close()
            raise e

    def commit(self, query):
        try:
            cursor = self.sql.cursor()
            cursor.execute(query)
            self.sql.commit()
        except Exception as e:
            self.sql.rollback()
            self.sql.close()
            raise e

    def query(self, query):
        cursor = self.sql.cursor()
        cursor.execute(query)
        return cursor

    def fetch_all(self, query):
        results = self.query(query).fetchall()
        return results

    def fetch_one(self, query):
        results = self.query(query).fetchone()
        return results

class BugzDB(SQLBase):

    def __init__(self):
        self.db_path = '/'.join([os.path.expanduser('~'), '.cache', 'bugz', 'bugz.db'])
        SQLBase.__init__(self, self.db_path)
        self.sql = sqlite3.connect(self.db_path)
        self.sql.row_factory = sqlite3.Row

    def init_schema_sru_cycle_stats_table(self):
        try:
            cursor = self.sql.cursor()

            q  = 'create table if not exists '
            q += 'sru_cycle_stats ( '
            q += '    id                    text primary key,'   # lpbug.id
            q += '    series                text,'               # Series
            q += '    package               text,'               # package
            q += '    cycle                 text,'               # The SRU cycle id (without the spin #)
            q += '    variant               text,'               # deb or snap
            q += '    total                 integer,'            # Time from when a bug is marked in-progress until it is fix-released
            q += '    ready                 integer,'            # prepare-package(confirmed)          - prepare-package(created)
            q += '    waiting               integer,'            # prepare-package(in progress)        - prepare-package(confirmed)
            q += '    crank                 integer,'            # prepare-package(fix committed)      - prepare-package(in progress)
            q += '    build                 integer,'            # promote-to-proposed(confirmed)      - prepare-package(fix released)
            q += '    review_start          integer,'            # promote-to-proposed(in progress)    - promote-to-proposed(confirmed)
            q += '    review                integer,'            # promote-to-proposed(fix committed)  - promote-to-proposed(in progress)
            q += '    regression_testing    integer,'            # regression-testing(fix released)    - regression-testing(confirmed)
            q += '    verification_testing  integer,'            # verification-testing(fix released)  - verification-testing(confirmed)
            q += '    certification_testing integer'             # certification-testing(fix released) - certification-testing(confirmed)
            q += ');'

            cursor.execute(q)
            self.sql.commit()
        except Exception as e:
            self.sql.rollback()
            self.sql.close()
            raise e

    def update_sru_cycle_stats_table(self, cycle):
        cursor = self.sql.cursor()

        q  = 'insert or replace into sru_cycle_stats (id, series, package, cycle, variant, total, ready, waiting, crank, build, review_start, review, regression_testing, verification_testing, certification_testing) values '
        q += '('
        q += '"{}",'.format(cycle.id)
        q += '"{}",'.format(cycle.series)
        q += '"{}",'.format(cycle.package)
        q += '"{}",'.format(cycle.cycle)
        q += '"{}",'.format(cycle.variant)
        q += '"{}",'.format(cycle.total)
        q += '"{}",'.format(cycle.ready)
        q += '"{}",'.format(cycle.waiting)
        q += '"{}",'.format(cycle.crank)
        q += '"{}",'.format(cycle.build)
        q += '"{}",'.format(cycle.review_start)
        q += '"{}",'.format(cycle.review)
        q += '"{}",'.format(cycle.regression_testing)
        q += '"{}",'.format(cycle.verification_testing)
        q += '"{}"'.format(cycle.certification_testing)
        q += ');'
        try:
            cursor.execute(q)
            self.sql.commit()
        except sqlite3.OperationalError:
            print('Exception thrown executing:\n    %s\n' % q)
            raise

    def init_schema_bug_table(self):
        try:
            cursor = self.sql.cursor()

            q  = 'create table if not exists '
            q += 'bugs ( '
            q += '    id                    text primary key,'   # lpbug.id
            q += '    title                 text,'               # lpbug.title,
            q += '    owner                 text,'               # lpbug.owner
            q += '    owner_display_name    text,'               # lpbug.owner.display_name
            q += '    created               integer,'            # lpbug.date_created
            q += '    last_message          integer,'            # lpbug.date_last_message
            q += '    last_updated          integer,'            # lpbug.date_last_updated
            q += '    private               text,'               # lpbug.private,
            q += '    security              text,'               # lpbug.security_related,
            q += '    duplicate             text,'               # lpbug.duplicate_of
            q += '    heat                  integer,'            # lpbug.heat
            q += '    is_expirable          text,'               # lpbug.isExpirable()
            q += '    problem_type          text,'               # The description can contain a "problem_type"
            q += '    description           text,'               # lpbug.description
            q += '    master_bug_id         text,'               # The bug number of the master bug if there is one
            q += '    cycle                 text,'               # The SRU cycle id (without the spin #)
            q += '    spin                  text,'               # The SRU cycle spin number (just the spin number)
            q += '    series                text,'               # Series
            q += '    package               text,'               # package
            q += '    version               text,'               # version
            q += '    variant               text'                # variant
            q += ');'
            cursor.execute(q)
            self.sql.commit()
        except Exception as e:
            self.sql.rollback()
            self.sql.close()
            raise e

    def init_schema_tasks_table(self):
        try:
            # This table is for mapping from bugs to tables that are specific
            # to an individual task
            #
            cursor = self.sql.cursor()

            q  = 'create table if not exists '
            q += 'tasks ( '
            q += '    id                    text key,'           # lpbug.id
            q += '    tbl                   text'                # table name
            q += ');'
            cursor.execute(q)
            self.sql.commit()
        except Exception as e:
            self.sql.rollback()
            self.sql.close()
            raise e

        try:
            # This table maps from a LP task name to the corresponding table
            # for that task.
            #
            cursor = self.sql.cursor()

            q  = 'create table if not exists '
            q += 'task_names ( '
            # q += '    id                    text key,'           # lpbug.id
            q += '    tbl                   text,'               # table name
            q += '    name                  text'                # task name
            q += ');'
            cursor.execute(q)
            self.sql.commit()
        except Exception as e:
            self.sql.rollback()
            self.sql.close()
            raise e

    def init_schema_task_table(self, table):
        try:
            cursor = self.sql.cursor()

            q  = 'create table if not exists '
            q += '%s ( ' % table
            q += '    rid                   integer primary key autoincrement,'
            q += '    id                    text key,'           # lpbug.id

            q += '    assignee              text,'               # assignee.display_name
            q += '    status                text,'               # task.status
            q += '    importance            text,'               # task.importance
            q += '    date_created          integer,'            # task.date_created
            q += '    date_confirmed        integer,'            # task.date_confirmed
            q += '    date_assigned         integer,'            # task.date_assigned
            q += '    date_closed           integer,'            # task.date_closed
            q += '    date_fix_committed    integer,'            # task.date_fix_committed
            q += '    date_fix_released     integer,'            # task.date_fix_released
            q += '    date_in_progress      integer,'            # task.date_in_progress
            q += '    date_incomplete       integer,'            # task.date_incomplete
            q += '    date_left_closed      integer,'            # task.date_left_closed
            q += '    date_left_new         integer,'            # task.date_left_new
            q += '    date_triaged          integer,'            # task.date_triaged
            q += '    is_complete           text,'               # task.is_complete
            q += '    owner                 text,'               # task.owner.display_name
            q += '    title                 text,'               # task.title
            q += '    milestone             text,'               # task.milestone
            q += '    name                  text'                # task.bug_target_display_name

            q += ');'
            cursor.execute(q)
            self.sql.commit()
        except Exception as e:
            print(q)
            self.sql.rollback()
            self.sql.close()
            raise e

    def init_schema_comments_table(self):
        try:
            cursor = self.sql.cursor()

            q  = 'create table if not exists '
            q += 'comments ( '
            q += '    rid                   integer primary key autoincrement,'
            q += '    id                    text key,'           # lpbug.id

            q += '    content               text,'               # message.content,
            q += '    created               integer,'            # message.date_created,
            q += '    owner                 text,'               # message.owner.display_name,
            q += '    subject               text'                # message.subject,

            q += ');'
            cursor.execute(q)
            self.sql.commit()
        except Exception as e:
            self.sql.rollback()
            self.sql.close()
            raise e

    def init_schema_nominations_table(self):
        try:
            cursor = self.sql.cursor()

            q  = 'create table if not exists '
            q += 'nominations ( '
            q += '    rid                   integer primary key autoincrement,'
            q += '    id                    text key,'           # lpbug.id

            q += '    status                text,'               # nomination.status
            q += '    distro_series         text,'               # ds.name
            q += '    active                text,'               # ds.active
            q += '    supported             text,'               # ds.supported
            q += '    product_series        text,'               # nomination.product_series.name
            q += '    created               integer,'            # date_to_string(nomination.date_created
            q += '    decided               integer'             # date_to_string(nomination.date_decided

            q += ');'
            cursor.execute(q)
            self.sql.commit()
        except Exception as e:
            self.sql.rollback()
            self.sql.close()
            raise e

    def init_schema_tags_table(self):
        try:
            cursor = self.sql.cursor()

            q  = 'create table if not exists '
            q += 'tags ( '
            q += '    id                    text key,'           # lpbug.id
            q += '    tag                   text'                # a single tag associated with the bug
            q += ');'
            cursor.execute(q)
            self.sql.commit()
        except Exception as e:
            self.sql.rollback()
            self.sql.close()
            raise e

    def init_schema(self):
        self.init_schema_bug_table()
        self.init_schema_tasks_table()
        self.init_schema_comments_table()
        self.init_schema_nominations_table()
        self.init_schema_tags_table()
        self.init_schema_sru_cycle_stats_table()

    def text_clean(self, text):
        return text.replace('"', '""')

    def update_bugs_table(self, bug):
        cursor = self.sql.cursor()
        q  = 'insert or replace into bugs (id, title, owner, owner_display_name, created, last_message, last_updated, private, security, duplicate, heat, is_expirable, problem_type, description, master_bug_id, cycle, spin, series, package, version, variant) values '
        q += '('
        q += '"{}",'.format(bug.id)
        q += '"{}",'.format(bug.title)
        q += '"{}",'.format(bug.owner)
        q += '"{}",'.format(bug.owner_display_name)
        q += '"{}",'.format(bug.created)
        q += '"{}",'.format(bug.last_message)
        q += '"{}",'.format(bug.last_updated)
        q += '"{}",'.format(bug.private)
        q += '"{}",'.format(bug.security)
        q += '"{}",'.format(bug.duplicate)
        q += '"{}",'.format(bug.heat)
        q += '"{}",'.format(bug.is_expirable)
        q += '"{}",'.format(bug.problem_type)
        q += '"{}",'.format(self.text_clean(bug.description))
        q += '"{}",'.format(bug.master_bug_id)
        q += '"{}",'.format(bug.cycle)
        q += '"{}",'.format(bug.spin)
        q += '"{}",'.format(bug.series)
        q += '"{}",'.format(bug.package)
        q += '"{}",'.format(bug.version)
        q += '"{}"'.format(bug.variant)
        q += ');'
        try:
            cursor.execute(q)
        except sqlite3.OperationalError:
            print('Exception thrown executing:\n    %s\n' % q)
            raise

        self.sql.commit()

        q = 'delete from tags where id = %s;' % bug.id
        cursor.execute(q)

        for tag in bug.tags:
            q  = 'insert into tags ('
            q += 'id, '
            q += 'tag '
            q += ') values ('
            q += '"{}", '.format(bug.id)
            q += '"%s"' % tag
            q += ');'
            try:
                cursor.execute(q)
            except sqlite3.OperationalError:
                print('Exception thrown executing:\n    %s\n' % q)
                raise

        self.sql.commit()

    def update_tasks_tables(self, bug):
        cursor = self.sql.cursor()

        # We need to first remove any existing mappings from the bug id to
        # tasks associated to that bug.
        #
        q = 'delete from tasks where id = %s;' % bug.id
        cursor.execute(q)

        for taskname in bug.tasks:
            task = bug.tasks[taskname]
            # print(json.dumps(task, sort_keys=True, indent=4))
            table = taskname.replace('-', '_').replace(' ', '_').replace('(', '').replace(')', '').replace('/', '___').replace('.', '_')

            # By always creating the table if it doesn't exist when we add new tasks to the bugs we don't
            # have to come in here and add additional code to create the schema.
            #
            self.init_schema_task_table(table)

            q = 'delete from %s where id = %s;' % (table, bug.id)
            cursor.execute(q)

            q  = 'insert or replace into %s (' % table
            q += 'id, '
            q += 'assignee,'
            q += 'status,'
            q += 'importance,'
            q += 'date_created,'
            q += 'date_confirmed,'
            q += 'date_assigned,'
            q += 'date_closed,'
            q += 'date_fix_committed,'
            q += 'date_fix_released,'
            q += 'date_in_progress,'
            q += 'date_incomplete,'
            q += 'date_left_closed,'
            q += 'date_left_new,'
            q += 'date_triaged,'
            q += 'is_complete,'
            q += 'owner,'
            q += 'title,'
            q += 'milestone,'
            q += 'name'
            q += ') values (' # % table
            q += '"{}", '.format(bug.id)
            q += '"{}", '.format(task.assignee)
            q += '"{}", '.format(task.status)
            q += '"{}", '.format(task.importance)
            q += '"{}", '.format(task.date_created)
            q += '"{}", '.format(task.date_confirmed)
            q += '"{}", '.format(task.date_assigned)
            q += '"{}", '.format(task.date_closed)
            q += '"{}", '.format(task.date_fix_committed)
            q += '"{}", '.format(task.date_fix_released)
            q += '"{}", '.format(task.date_in_progress)
            q += '"{}", '.format(task.date_incomplete)
            q += '"{}", '.format(task.date_left_closed)
            q += '"{}", '.format(task.date_left_new)
            q += '"{}", '.format(task.date_triaged)
            q += '"{}", '.format(task.is_complete)
            q += '"{}", '.format(task.owner)
            q += '"{}", '.format(self.text_clean(task.title))
            q += '"{}", '.format(task.milestone)
            q += '"{}"'.format(taskname)
            q += ');'

            cursor.execute(q)

            # This maps a single bug to all of the task tables that it has information in.
            #
            q  = 'insert into tasks(id, tbl) values'
            q += '('
            q += '"{}", '.format(bug.id)
            q += '"{}"  '.format(table)
            q += ');'
            cursor.execute(q)

            # This maps all of the tasks names to their table.
            #
            # q  = 'insert or ignore into task_names(id, tbl, name) values '
            q  = 'insert or ignore into task_names(tbl, name) values '
            q += '('
            # q += '(select id from task_names where tbl = "%s" and name = "%s"), ' % (table, taskname)
            q += '"{}", '.format(table)
            q += '"{}"  '.format(taskname)
            q += ');'
            cursor.execute(q)

            self.sql.commit()

            # if table not in self.sql_tables:
            #     self.sql_tables.append(table)

    def load_new_bug(self, msg):
        msg['title'] = msg['title'].replace('"', '""')
        self.update_bugs_table(msg)
        self.update_tasks_tables(msg)
