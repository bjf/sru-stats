import os
from launchpadlib.launchpad             import Launchpad as _Launchpad


class Launchpad():
    """
    Manages connection to Launchpad services.
    """
    def __init__(s, client_name):
        """
        """
        s.__service_root = 'production'
        launchpad_cachedir = os.path.join(os.path.expanduser('~'), '.cache', client_name)
        launchpad_creddir  = os.path.join(os.path.expanduser('~'), '.config', client_name)
        filename_parts = ['credentials', 'production']

        launchpad_credentials_file = os.path.join(launchpad_creddir, '-'.join(filename_parts))

        if not os.path.exists(launchpad_creddir):
            os.makedirs(launchpad_creddir, 0o700)

        s.service = _Launchpad.login_with(client_name,
                                          service_root=s.__service_root,
                                          launchpadlib_dir=launchpad_cachedir,
                                          credentials_file=launchpad_credentials_file,
                                          version='devel')
        return

    # bug_url
    #
    def bug_url(s, bug_id):
        '''
        Helper routine to return the correct URL for the specified bug. Takes use
        of the qastaging service into account.
        '''
        if s.__service_root == 'staging':
            lpserver = 'bugs.qastaging.launchpad.net'
        else:
            lpserver = 'bugs.launchpad.net'
        retval = 'https://%s/bugs/%s' % (lpserver, bug_id)
        return retval
