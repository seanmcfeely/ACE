# vim: sw=4:ts=4:et

import logging
import re
import os
import saq

from saq.analysis import Analysis, Observable
from saq.constants import *
from saq.modules import AnalysisModule, SplunkAnalysisModule, splunktime_to_saqtime

from cbapi import auth, connection
from cbapi.response import *
from cbapi.errors import ApiError, ObjectNotFoundError
from cbinterface import events_to_json, walk_process_tree

KEY_ASSET_COUNT = 'asset_count'
KEY_PROCESS_LOGS = 'process_logs'

#
# Module:   DLP Process Analysis by Hash
# Question: How many assets have executed this program?
#

class DLPProcessHashAnalysis_v1(Analysis):
    """How many assets and users have executed a program with this hash value in the past N hours?"""

    def initialize_details(self):
        self.details = {
            KEY_ASSET_COUNT: None,
            KEY_PROCESS_LOGS: None }

    @property
    def asset_count(self):
        """Returns the number of distinct assets that have executed this program in the past 24 hours."""
        return self.details[KEY_ASSET_COUNT]

    @asset_count.setter
    def asset_count(self, value):
        if isinstance(value, str):
            value = int(value)

        self.details[KEY_ASSET_COUNT] = value

    @property
    def process_logs(self):
        """Returns all the process execution logs from DLP for the given hash in the past 24 hours."""
        return self.details[KEY_PROCESS_LOGS]
        
    @process_logs.setter
    def process_logs(self, value):
        self.details[KEY_PROCESS_LOGS] = value

    @property
    def jinja_template_path(self):
        return "analysis/process_analysis_v1.html"

    def generate_summary(self):
        return "DLP Process Analysis ({0} hosts)".format(self.asset_count)

class DLPProcessHashAnalyzer_v1(SplunkAnalysisModule):
    def verify_environment(self):
        self.verify_config_exists('max_asset_count')

    @property
    def max_asset_count(self):
        return self.config.getint('max_asset_count')

    @property
    def generated_analysis_type(self):
        return DLPProcessHashAnalysis_v1

    @property
    def valid_observable_types(self):
        return F_MD5

    def __init__(self, *args, **kwargs):
        super(DLPProcessHashAnalyzer_v1, self).__init__(*args, **kwargs)
        
    def execute_analysis(self, observable):

        if not observable in self.root.observables and not observable.is_suspect:
            return False

        logging.debug("performing DLP process analysis on {0}".format(observable.value))

        # first we look at our Windows DNS systems
        query_broad_filter = observable.value
        query_fine_filter = 'MD5_Checksum = {0}'.format(observable.value)

        # who made these requests?
        self.relative_duration_before = self.config['relative_duration_before']
        self.relative_duration_after = self.config['relative_duration_after']

        self.splunk_query("""index=dlp_logs sourcetype=digitalguardian:process {0} | search {1} | stats dc(Computer_Name) as asset_count""".format(
            query_broad_filter, query_fine_filter),
            self.root.event_time_datetime if observable.time_datetime is None else observable.time_datetime)
        
        asset_count_results = self.json()

        if asset_count_results is None or len(asset_count_results) == 0:
            logging.error("got 0 results from a stats command (should not happen)")
            return False

        analysis = self.create_analysis(observable)
        analysis.asset_count = asset_count_results[0]['asset_count']

        # now perform a detailed query for the individual dns requests
        self.splunk_query("""index=dlp_logs sourcetype=digitalguardian:process {0} | search {1} | fields *""".format(
            query_broad_filter, query_fine_filter),
            self.root.event_time_datetime if observable.time_datetime is None else observable.time_datetime)

        if self.search_results is None:
            logging.debug("missing search results after splunk query")
            return False

        analysis.process_logs = self.json()

        if analysis.asset_count > self.max_asset_count:
            return True

        computer_names = set()
        user_names = set()

        for event in analysis.process_logs:
            if event['Computer_Name'] and '/' in event['Computer_Name']:
                domain, hostname = event['Computer_Name'].split('/')
            else:
                hostname = event['Computer_Name']

            computer_names.add(hostname)

            if event['User_Name'] and '/' in event['User_Name']:
                domain, username = event['User_Name'].split('/')
            else:
                username = event['User_Name']

            user_names.add(hostname)

        for hostname in computer_names:
            analysis.add_observable(F_HOSTNAME, hostname)

        for user in user_names:
            analysis.add_observable(F_USER, user)

        return True
#
# Module:   Bit9 Process Analysis by Hash
# Question: How many assets have seen this file?
#

class Bit9FileHashAnalysis_v1(Analysis):
    """How many assets have we seen this file hash on?"""

    def initialize_details(self):
        self.details = {
            # how many distinct SRC_IP in the X minutes surrounding the alert
            KEY_ASSET_COUNT: None,
            KEY_PROCESS_LOGS: None }

    @property
    def asset_count(self):
        """Returns the number of distinct assets that have seen this file in the past 24 hours."""
        return self.details[KEY_ASSET_COUNT]

    @asset_count.setter
    def asset_count(self, value):
        if isinstance(value, str):
            value = int(value)

        self.details[KEY_ASSET_COUNT] = value

    @property
    def process_logs(self):
        """Returns all the bit9 logs for the given hash in the past 24 hours."""
        return self.details[KEY_PROCESS_LOGS]
        
    @process_logs.setter
    def process_logs(self, value):
        self.details[KEY_PROCESS_LOGS] = value

    @property
    def jinja_template_path(self):
        return "analysis/process_analysis_v1.html"

    def generate_summary(self):
        return "Bit9 File Analysis ({0} hosts)".format(self.asset_count)

class Bit9FileHashAnalyzer_v1(SplunkAnalysisModule):
    def verify_environment(self):
        self.verify_config_exists('max_asset_count')

    @property
    def max_asset_count(self):
        return self.config.getint('max_asset_count')

    @property
    def generated_analysis_type(self):
        return Bit9FileHashAnalysis_v1

    @property
    def valid_observable_types(self):
        return F_MD5, F_SHA1, F_SHA256
        
    def execute_analysis(self, observable):

        if not observable in self.root.observables and not observable.is_suspect:
            return False

        logging.debug("performing bit9 file hash analysis on {0}".format(observable.value))

        query_broad_filter = observable.value
        if observable.type == F_MD5:
            query_fine_filter = 'Md5 = {0}'.format(observable.value)
        elif observable.type == F_SHA1:
            query_fine_filter = 'Sha1 = {0}'.format(observable.value)
        if observable.type == F_SHA256:
            query_fine_filter = 'FileHash = {0}'.format(observable.value)

        self.relative_duration_before = self.config['relative_duration_before']
        self.relative_duration_after = self.config['relative_duration_after']

        self.splunk_query("""index=bit9 {0} | search {1} | stats dc(HostName) as asset_count""".format(
            query_broad_filter, query_fine_filter),
            self.root.event_time_datetime if observable.time_datetime is None else observable.time_datetime)
        
        asset_count_results = self.json()

        if asset_count_results is None or len(asset_count_results) == 0:
            logging.error("got 0 results from a stats command (should not happen)")
            return False

        analysis = self.create_analysis(observable)
        analysis.asset_count = asset_count_results[0]['asset_count']

        self.splunk_query("""index=bit9 {0} | search {1} | fields *""".format(
            query_broad_filter, query_fine_filter),
            self.root.event_time_datetime if observable.time_datetime is None else observable.time_datetime)

        if self.search_results is None:
            logging.debug("missing search results after splunk query")
            return False

        analysis.process_logs = self.json()

        if analysis.asset_count > self.max_asset_count:
            return True

        computer_names = set()

        for event in analysis.process_logs:
            if '\\' in event['HostName']:
                domain, hostname = event['HostName'].split('\\')
            else:
                hostname = event['HostName']

            computer_names.add(hostname)

        for hostname in computer_names:
            analysis.add_observable(F_HOSTNAME, hostname)

        return True

#
# Module:   CarbonBlack Process GUID Analysis
# Questions: What did this process do? (Activity/event summary)
#            What does the process tree look like?
#

              
class ProcessGUIDAnalysis(Analysis):
    """What activity did this process perform?"""

    def initialize_details(self):
        self.details = {}

    @property
    def jinja_template_path(self):
        return "analysis/process_guid.html"

    def generate_summary(self):
        process_name = self.details['process_name']
        hostname = self.details['hostname']
        username = self.details['username']
        return "CarbonBlack Process Analysis: {0} executed on {1} by {2}".format(process_name,
                                                                                  hostname,
                                                                                  username) 

class ProcessGUIDAnalyzer(AnalysisModule):
    def verify_environment(self):

        if not 'carbon_black' in saq.CONFIG:
            raise ValueError("missing config section carbon_black")

        key = 'credential_file'
        if not key in saq.CONFIG['carbon_black']:
                raise ValueError("missing config item {} in section carbon_black".format(key))

    @property
    def generated_analysis_type(self):
        return ProcessGUIDAnalysis

    @property
    def valid_observable_types(self):
        return F_PROCESS_GUID

    def execute_analysis(self, observable):

        if not observable in self.root.observables and not observable.is_suspect:
            return False

        #cbapi does not check for guids and doesn't error correctly
        regex = re.compile('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I)
        if regex.match(observable.value) == None:
            logging.error("{} is not in the format of a process guid".format(observable.value))
            return False

        cb = CbResponseAPI(credential_file=saq.CONFIG['carbon_black']['credential_file'])

        try:
            proc = cb.select(Process, observable.value, force_init=True)
        except ObjectNotFoundError as e:
            logging.error("Could not find process {0:s}".format(observable.value))
            return False
        except ApiError as e:
            logging.error("Encountered error retrieving process: {0:s}".format(str(e)))
            return False
        except Exception as e:
            logging.error("Encountered unknown error retrieving process: {0:s}".format(str(e)))
            return False

        analysis = self.create_analysis(observable)

        process_tree = walk_process_tree(proc)
        process_event_details = events_to_json(proc)
        process_event_details['process_tree'] =  process_tree.tuple_list()
  
        binfo = proc.binary.version_info
        process_event_details['binary_file_desc'] = binfo.file_desc   
        process_event_details['binary_product_name'] = binfo.product_name
        process_event_details['binary_legal_copyright'] = binfo.legal_copyright
        process_event_details['binary_original_filename'] = binfo.original_filename


        process_event_details['binary_sig_status'] = proc.binary.signing_data.result
        process_event_details['binary_sig_publisher'] = proc.binary.signing_data.publisher
        process_event_details['binary_sig_issuer'] = proc.binary.signing_data.issuer
        process_event_details['binary_sig_subject'] = proc.binary.signing_data.subject
        process_event_details['binary_vt_score'] = proc.binary.virustotal.score
        process_event_details['binary_vt_link'] = proc.binary.virustotal.link

        analysis.details = process_event_details
        return True