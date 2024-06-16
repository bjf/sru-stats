#!/usr/bin/env python3

from .launchpad                         import Launchpad
from datetime                           import datetime, timedelta

class LaunchpadBugz(Launchpad):
    def __init__(s, clientname='bugz'):
        super().__init__(clientname)
        s.launchpad = s.service

    def tag_bug(s, bugid, tag):
        '''
        Apply the specified tag to the specified Launchpad bug.
        '''
        lp = Launchpad('bugz')
        lpbug = lp.service.bugs[bugid]
        tags = lpbug.tags
        if tag not in tags:
            tags.append(tag)
            lpbug.tags = tags
            lpbug.lp_save()

    def fetch(s, bugid, callback):
        lpbug = s.launchpad.bugs[bugid]
        callback(lpbug, s)

    def tag_search(s, tag, callback, since=None, delta_seconds=None):
        '''
        Return a list of all of the launchpad bugs of the Ubuntu distribution that have a given tag.
        '''
        search_tags = [tag]
        search_tags_combinator = "All"

        # A list of the bug statuses that we care about
        #
        search_status = [
            "New",
            "Incomplete (with response)",
            "Incomplete (without response)",
            "Confirmed",
            "Triaged",
            "In Progress",
            "Fix Committed",
            "Invalid",
            "Fix Released",
        ] # A list of the bug statuses that we care about

        # The tracking bugs that we are interested in should have been created recently (days).
        #
        retval = datetime.utcnow()
        if since is not None:
            timestamp = since
        else:
            timestamp = datetime.utcnow()

        if delta_seconds is not None:
            search_since = timestamp - timedelta(seconds=delta_seconds)
        else:
            search_since = None

        ubuntu = s.launchpad.distributions['ubuntu']
        tasks = ubuntu.searchTasks(status=search_status, tags=search_tags, tags_combinator=search_tags_combinator, modified_since=search_since)
        for task in tasks:
            callback(task)
            break # just one for debugging purposes

        return retval

    def initial_message(s, lptask):
        '''
        Build a message with all the bug information we are interested in the first time we start
        tracking a bug.
        '''
        pass

    def update_message(s, lptask):
        '''
        Build a message with all the bug information we are interested in when a bug we are tracking
        gets updated.
        '''
        pass
