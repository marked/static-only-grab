# encoding=utf8
import datetime
from distutils.version import StrictVersion
import hashlib
import os.path
import random
from seesaw.config import realize, NumberConfigValue
from seesaw.externalprocess import ExternalProcess
from seesaw.item import ItemInterpolation, ItemValue
from seesaw.task import SimpleTask, LimitConcurrent
from seesaw.tracker import GetItemFromTracker, PrepareStatsForTracker, \
                           UploadWithTracker, SendDoneToTracker
import shutil
import socket
import subprocess
import sys
import time
import string

from tornado import httpclient

import seesaw
from seesaw.externalprocess import WgetDownload
from seesaw.pipeline import Pipeline
from seesaw.project import Project
from seesaw.util import find_executable

import json

# check the seesaw version
if StrictVersion(seesaw.__version__) < StrictVersion('0.10.3'):
    raise Exception('This pipeline needs seesaw version 0.10.3 or higher.')


###########################################################################
# Find a useful Wget+Lua executable.
#
# WGET_LUA will be set to the first path that
# 1. does not crash with --version, and
# 2. prints the required version string
WGET_LUA = find_executable(
    'Wget+Lua',
    ['GNU Wget 1.20.3-at-lua'],
    [
        './wget-lua',
        './wget-lua-warrior',
        './wget-lua-local',
        '../wget-lua',
        '../../wget-lua',
        '/home/warrior/wget-lua',
        '/usr/bin/wget-lua'
    ]
)

if not WGET_LUA:
    raise Exception('No usable Wget+Lua found.')


###########################################################################
# The version number of this pipeline definition.
#
# Update this each time you make a non-cosmetic change.
# It will be added to the WARC files and reported to the tracker.
VERSION = '20191026.01'
USER_AGENT = 'ArchiveTeam'
TRACKER_ID = 'static-only'
# TRACKER_HOST = 'tracker.archiveteam.org'  #prod-env
TRACKER_HOST = 'tracker-test.ddns.net'  #dev-env


###########################################################################
# This section defines project-specific tasks.
#
# Simple tasks (tasks that do not need any concurrency) are based on the
# SimpleTask class and have a process(item) method that is called for
# each item.
class CheckIP(SimpleTask):
    def __init__(self):
        SimpleTask.__init__(self, 'CheckIP')
        self._counter = 0

    def process(self, item):
        # NEW for 2014! Check if we are behind firewall/proxy

        if self._counter <= 0:
            item.log_output('Checking IP address.')
            ip_set = set()

            ip_set.add(socket.gethostbyname('twitter.com'))
            ip_set.add(socket.gethostbyname('facebook.com'))
            ip_set.add(socket.gethostbyname('youtube.com'))
            ip_set.add(socket.gethostbyname('microsoft.com'))
            ip_set.add(socket.gethostbyname('icanhas.cheezburger.com'))
            ip_set.add(socket.gethostbyname('archiveteam.org'))

            if len(ip_set) != 6:
                item.log_output('Got IP addresses: {0}'.format(ip_set))
                item.log_output(
                    'Are you behind a firewall/proxy? That is a big no-no!')
                raise Exception(
                    'Are you behind a firewall/proxy? That is a big no-no!')

        # Check only occasionally
        if self._counter <= 0:
            self._counter = 10
        else:
            self._counter -= 1


class CheckBan(SimpleTask):
    def __init__(self):
        SimpleTask.__init__(self, 'CheckBan')

    def process(self, item):
        msg = None
        httpclient.AsyncHTTPClient.configure(None, defaults=dict(user_agent=USER_AGENT))
        http_client = httpclient.HTTPClient()
        try:
            # response = http_client.fetch("https://yourshot.nationalgeographic.com/static/img/navbar/yourshot-logo.svg") # static asset
            response = http_client.fetch("https://yourshot.nationalgeographic.com/api/v3/photos/search/")  # dynamic
        except httpclient.HTTPError as e:
            msg = "Failed to get CheckBan URL: " + str(e)
            item.log_output(msg)
            item.log_output("Sleeping 60...")
            time.sleep(60)
        http_client.close()
        if msg != None:
            raise Exception(msg)


class PrepareDirectories(SimpleTask):
    def __init__(self, warc_prefix):
        SimpleTask.__init__(self, 'PrepareDirectories')
        self.warc_prefix = warc_prefix

    def process(self, item):
        start_time = time.strftime('%Y%m%d-%H%M%S')

        item_name = item['item_name']
        assert ':' in item_name
        item_type, item_fn, item_value = item_name.split(':', 2)
        item['item_type'] = item_type
        item['item_value'] = item_value
        item['item_fn'] = item_fn

        escaped_item_name = item_fn.replace(':', '_').replace('/', '_').replace('~', '_')
        dirname = '/'.join((item['data_dir'], escaped_item_name))

        if os.path.isdir(dirname):
            shutil.rmtree(dirname)

        os.makedirs(dirname)

        item['item_dir'] = dirname
        item['start_time'] = start_time
        item['warc_file_base'] = '%s-%s-%s'    % (self.warc_prefix, escaped_item_name[:50],      start_time)

        open('%(item_dir)s/%(warc_file_base)s.warc.gz' % item, 'w').close()


class MoveFiles(SimpleTask):
    def __init__(self):
        SimpleTask.__init__(self, 'MoveFiles')

    def process(self, item):
        # NEW for 2014! Check if wget was compiled with zlib support
        if os.path.exists('%(item_dir)s/%(warc_file_base)s.warc' % item):
            raise Exception('Please compile wget with zlib support!')

        os.rename('%(item_dir)s/%(warc_file_base)s.warc.gz' % item,
                  '%(data_dir)s/%(warc_file_base)s.warc.gz' % item)

        shutil.rmtree('%(item_dir)s' % item)
        item['files'] = [ ItemInterpolation('%(data_dir)s/%(warc_file_base)s.warc.gz') ]

def get_hash(filename):
    with open(filename, 'rb') as in_file:
        return hashlib.sha1(in_file.read()).hexdigest()


CWD = os.getcwd()
PIPELINE_SHA1 = get_hash(os.path.join(CWD, 'pipeline.py'))
LUA_SHA1 = get_hash(os.path.join(CWD, 'static-only.lua'))


def stats_id_function(item):
    # NEW for 2014! Some accountability hashes and stats.
    d = {
        'pipeline_hash': PIPELINE_SHA1,
        'lua_hash': LUA_SHA1,
        'python_version': sys.version,
    }

    return d


class WgetArgs(object):
    def realize(self, item):
        wget_args = [
            WGET_LUA,
            '-U', USER_AGENT,
            #'-nv',
            '--no-cookies',
            '--lua-script', 'static-only.lua',
            '-o', ItemInterpolation('%(item_dir)s/wget.log'),
            '--no-check-certificate',
            '--output-document', ItemInterpolation('%(item_dir)s/wget.tmp'),
            '--truncate-output',
            '-e', 'robots=off',
            '--rotate-dns',
            # '--recursive', '--level=inf',
            # '--no-parent',
            # '--page-requisites',
            '--timeout', '30',
            # '--tries', 'inf',
            # '--domains', '.com',
            # '--span-hosts',
            '--waitretry', '30',
            '--warc-file', ItemInterpolation('%(item_dir)s/%(warc_file_base)s'),
            '--warc-header', 'operator: Archive Team',
            '--warc-header', 'static-only-dld-script-version: ' + VERSION,
            '--warc-header', ItemInterpolation('static-only-item: %(item_name)s'),
            # --warc-header static-url-id: ... filled in below
            # '--header', 'Accept-Encoding: gzip',
            # '--compression', 'gzip'
            # changed flags #
        ]

        item_type = item["item_type"]
        item_value = item["item_value"]

        wget_urls = []

        task_line = item_value

        #if len(task_line) == 0:
        #    continue
        # elif item_type == 'static_job_json': #  TODO
        # elif item_type == 'static_job_urls': #  TODO

        if item_type == 'static_url':
            print("T>  " + task_line)  #debug
            wget_urls.append(task_line)
        else:
            raise Exception('Unknown item')

        item["todo_url_count"] = str(len(wget_urls))

        print("URIs ToDo: {}".format(len(wget_urls)))
        if len(wget_urls) == 0:
            wget_args.append("-V")
        else:
            wget_args.extend(wget_urls)

        # print("\nD^      ".join(defer_assets))  #debug
        # print("\nD^      ", end="")  #debug

        if 'bind_address' in globals():
            wget_args.extend(['--bind-address', globals()['bind_address']])
            print('')
            print('*** Wget will bind address at {0} ***'.format(
                globals()['bind_address']))
            print('')

        return realize(wget_args, item)


###########################################################################
# Initialize the project.
#
# This will be shown in the warrior management panel. The logo should not
# be too big. The deadline is optional.
project = Project(
    title='static-only',
    project_html='''
    '''
)

pipeline = Pipeline(
    CheckIP(),
    # CheckBan(),
    GetItemFromTracker('http://%s/%s' % (TRACKER_HOST, TRACKER_ID), downloader, VERSION),
    PrepareDirectories(warc_prefix='static-only'),
    WgetDownload(
        WgetArgs(),
        max_tries=1,              # 2,          #changed
        accept_on_exit_code=[0],  # [0, 4, 8],  #changed
        env={
            'item_dir': ItemValue('item_dir'),
            'item_value': ItemValue('item_value'),
            'item_type': ItemValue('item_type'),
            'warc_file_base': ItemValue('warc_file_base'),
            'todo_url_count': ItemValue('todo_url_count'),
        }
    ),
    PrepareStatsForTracker(
        defaults={'downloader': downloader, 'version': VERSION},
        file_groups={
            'data': [
                ItemInterpolation('%(item_dir)s/%(warc_file_base)s.warc.gz')  #TODO ?
            ]
        },
        id_function=stats_id_function,
    ),
    MoveFiles(),
    LimitConcurrent(NumberConfigValue(min=1, max=20, default='20',
    name='shared:rsync_threads', title='Rsync threads',
    description='The maximum number of concurrent uploads.'),
        UploadWithTracker(
            'http://%s/%s' % (TRACKER_HOST, TRACKER_ID),
            downloader=downloader,
            version=VERSION,
            files=[
                ItemInterpolation('%(data_dir)s/%(warc_file_base)s.warc.gz'),
            ],
            rsync_target_source_path=ItemInterpolation('%(data_dir)s/'),
            rsync_extra_args=[
                '--recursive',
                '--partial',
                '--partial-dir', '.rsync-tmp',
                '--min-size', '1',
                '--no-compress',
                '--compress-level', '0'
            ]
        ),
    ),
    SendDoneToTracker(
        tracker_url='http://%s/%s' % (TRACKER_HOST, TRACKER_ID),
        stats=ItemValue('stats')
    )
)
