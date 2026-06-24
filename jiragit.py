import urllib
import urllib2
import json
import codecs
import argparse
import sys
import os
import time

# --- CONFIGURATION ---

# 1. Jira Configuration
JIRA_BASE_URL = "https://cisas.eu.airbus.corp:8343/1V32-jira"
JIRA_TOKEN = "MTc5NDU1MzU0NTE0OnrZeM3tRaBlXJPW5RaP1njINC5d"

# 2. GitHub Enterprise Configuration
# Replace with your actual GitHub Enterprise API URL (usually ends in /api/v3)
GITHUB_API_URL = "https://gheprivate.intra.corp/api/v3" 
GITHUB_TOKEN = "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"
GITHUB_ORG = "software-avionics"

# API Politeness Settings
REQUEST_DELAY = 0.1  # Half a second delay between requests

# --- HELPER FUNCTIONS ---

def safe_unicode(value):
    """Safely converts any data type to Unicode to prevent Python 2 crashes."""
    if value is None:
        return u"N/A"
    if isinstance(value, unicode):
        return value
    if isinstance(value, dict) or isinstance(value, list):
        return unicode(json.dumps(value, indent=2))
    return unicode(str(value), 'utf-8', errors='replace')

def make_api_request(url, token, accept_header="application/json"):
    """Generic helper to make authenticated API requests with rate limit handling."""
    req = urllib2.Request(url)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", accept_header)
    
    # Polite delay to prevent hammering the server
    time.sleep(REQUEST_DELAY)
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = urllib2.urlopen(req)
            return response.read()
            
        except urllib2.HTTPError as e:
            if e.code == 422:
                return None
            elif e.code in (403, 429):
                retry_after = e.headers.get('Retry-After')
                if retry_after:
                    sleep_time = int(retry_after) + 1
                    print "  [!] Rate limited. Sleeping for {0} seconds...".format(sleep_time)
                else:
                    sleep_time = 10 * (attempt + 1) 
                    print "  [!] Secondary rate limit hit. Backing off for {0} seconds...".format(sleep_time)
                
                time.sleep(sleep_time)
                continue
            else:
                print "HTTP Error {0} for URL: {1}".format(e.code, url)
                return None
                
        except urllib2.URLError as e:
            print "URL Error: {0} for URL: {1}".format(e.reason, url)
            return None
            
    print "  [!] Max retries reached for URL: {0}".format(url)
    return None

# --- CORE LOGIC ---

def get_jira_issues(jql):
    """Fetches Jira issues based on a raw JQL query."""
    print "  -> Fetching Jira tickets..."
    
    url = JIRA_BASE_URL + "/rest/api/2/search"
    params = {
        'jql': jql,
        'maxResults': 100, 
        'expand': 'names'
    }
    
    full_url = url + "?" + urllib.urlencode(params)
    data = make_api_request(full_url, JIRA_TOKEN)
    
    if data:
        return json.loads(data).get('issues', [])
    return []

def get_github_diffs_for_ticket(ticket_key, component):
    """Searches GitHub for commits mentioning the ticket, and fetches their diffs."""
    search_query = "{0} repo:{1}/{2}".format(ticket_key, GITHUB_ORG, component)
    
    search_params = {
        'q': search_query,
        'sort': 'author-date',
        'order': 'asc' 
    }
    search_url = GITHUB_API_URL + "/search/commits?" + urllib.urlencode(search_params)
    
    search_data = make_api_request(search_url, GITHUB_TOKEN, accept_header="application/vnd.github.v3+json")
    
    if not search_data:
        return []
        
    search_results = json.loads(search_data)
    commits = search_results.get('items', [])
    
    diffs = []
    for commit in commits:
        sha = commit.get('sha')
        message = commit.get('commit', {}).get('message', '').split('\n')[0] 
        
        print "    -> Found commit {0} for {1}".format(sha[:7], ticket_key)
        
        diff_url = "{0}/repos/{1}/{2}/commits/{3}".format(GITHUB_API_URL, GITHUB_ORG, component, sha)
        raw_diff = make_api_request(diff_url, GITHUB_TOKEN, accept_header="application/vnd.github.v3.diff")
        
        if raw_diff:
            diffs.append({
                'sha': sha,
                'message': message,
                'diff': safe_unicode(raw_diff)
            })
            
    return diffs

# --- FILE WRITERS ---

def write_jira_file(issues, filename, jql):
    with codecs.open(filename, 'w', 'utf-8') as f:
        f.write(u"JIRA RELEASE NOTES FOR: {0}\n".format(jql))
        f.write(u"=" * 80 + u"\n\n")
        
        for issue in issues:
            key = issue.get('key', 'UNKNOWN')
            fields = issue.get('fields', {})
            
            target_fields = [
                ('Issue Type', fields.get('issuetype', {}).get('name', 'N/A')),
                ('Summary', fields.get('summary', 'N/A')),
                ('Description', fields.get('description')),
                ('Solution Description', fields.get('customfield_11107')),
                ('Impacted Elements', fields.get('customfield_12502')),
                ('Change Impact', fields.get('customfield_11109')),
                ('Applicability/Impact Details', fields.get('customfield_11108')),
                ('Change Impact on Users', fields.get('customfield_12103', {}).get('value') if isinstance(fields.get('customfield_12103'), dict) else fields.get('customfield_12103')),
                ('Root Cause/Summary', fields.get('customfield_12100'))
            ]
            
            f.write(u"TICKET: {0}\n".format(key))
            f.write(u"-" * 80 + u"\n")
            
            for label, value in target_fields:
                if value is not None and value != "" and value != [] and value != {}:
                    f.write(u"{0}:\n{1}\n\n".format(label, safe_unicode(value)))
                    
            f.write(u"=" * 80 + u"\n\n")

def write_github_files_per_commit(issues, component, output_dir):
    for issue in issues:
        ticket_key = issue.get('key')
        diffs = get_github_diffs_for_ticket(ticket_key, component)
        
        if not diffs:
            print "  [!] No GitHub commits found for {0}. (Skipping diff generation)".format(ticket_key)
            continue
            
        agg_filename = "{0}_All_Diffs.txt".format(ticket_key)
        agg_filepath = os.path.join(output_dir, agg_filename)
        
        with codecs.open(agg_filepath, 'w', 'utf-8') as agg_file:
            agg_file.write(u"AGGREGATED DIFFS FOR TICKET: {0}\n".format(ticket_key))
            agg_file.write(u"=" * 80 + u"\n\n")
        
            for d in diffs:
                short_hash = d['sha'][:7]
                indiv_filename = "{0}_{1}.diff".format(ticket_key, short_hash)
                indiv_filepath = os.path.join(output_dir, indiv_filename)
                
                with codecs.open(indiv_filepath, 'w', 'utf-8') as ind_file:
                    ind_file.write(u"TICKET: {0}\n".format(ticket_key))
                    ind_file.write(u"COMMIT: {0}\n".format(d['sha']))
                    ind_file.write(u"MESSAGE: {0}\n".format(safe_unicode(d['message'])))
                    ind_file.write(u"=" * 80 + u"\n\n")
                    ind_file.write(d['diff'])
                
                agg_file.write(u"COMMIT: {0}\n".format(d['sha']))
                agg_file.write(u"MESSAGE: {0}\n".format(safe_unicode(d['message'])))
                agg_file.write(u"DIFF:\n")
                agg_file.write(d['diff'] + u"\n")
                agg_file.write(u"~" * 80 + u"\n\n")

# --- MAIN EXECUTION ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compile Jira notes and Git diff files for versions or selected tickets.")
    parser.add_argument("component", help="The component name (e.g., C00157)")
    
    # Versions remain default behavior, but optional if -t is used
    parser.add_argument("versions", nargs='*', help="List of fixVersions in order. Leave blank if using -t.")
    
    # Update to accept multiple tickets
    parser.add_argument("-t", "--tickets", nargs='+', help="List of specific Jira tickets to download (e.g., -t C00153-204 C00153-202)")
    
    args = parser.parse_args()
    
    # ==========================================
    # MODE 1: SELECTED TICKETS
    # ==========================================
    if args.tickets:
        print "=" * 80
        print "SELECTED TICKETS MODE FOR {0}".format(args.component)
        print "=" * 80
        
        # Build the JQL query: key in ("C00095-580", "C00095-578", ...)
        ticket_list_str = ", ".join(['"{0}"'.format(t) for t in args.tickets])
        jql_query = 'key in ({0})'.format(ticket_list_str)
        
        issues = get_jira_issues(jql_query)
        
        if not issues:
            print "  -> No issues found for the provided tickets or failed to connect."
            sys.exit(1)
            
        print "  -> Successfully fetched {0} tickets from Jira.".format(len(issues))
            
        # Create dedicated folder
        output_dir = "Selected_Tickets_{0}".format(args.component)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        jira_filename = "00_RD_{0}_Selected_Tickets.txt".format(args.component)
        
        write_jira_file(issues, jira_filename, jql_query)
        
        print "\n--- Processing GitHub diffs for selected tickets ---"
        write_github_files_per_commit(issues, args.component, output_dir)
        
        print "\nCompleted selected tickets download!"
        print " -> Master Jira notes saved as: {0}".format(jira_filename)
        print " -> Diffs saved to folder: {0}/".format(os.path.abspath(output_dir))
        
        sys.exit(0)

    # ==========================================
    # MODE 2: BATCH VERSIONS
    # ==========================================
    if not args.versions:
        print "Error: You must provide either a list of versions (e.g., 2.1.0) or use the -t flag."
        sys.exit(1)

    total_versions = len(args.versions)
    versions_data = []

    print "=" * 80
    print "PHASE 1: FETCHING JIRA TICKETS"
    print "=" * 80
    
    for i, version in enumerate(args.versions, start=1):
        print "\n[Version {0}/{1}] - {2}".format(i, total_versions, version)
        
        jira_filename = "{0:02d}_RD_{1}_{2}.txt".format(i, args.component, version)
        jql_query = 'project = {0} AND fixVersion = "{1}"'.format(args.component, version)
        
        issues = get_jira_issues(jql_query)
        
        if not issues:
            print "  -> No issues found. Skipping."
            continue
            
        print "  -> Found {0} tickets. Saving to {1}...".format(len(issues), jira_filename)
        write_jira_file(issues, jira_filename, jql_query)
        
        versions_data.append({
            'version': version,
            'issues': issues
        })

    print "\n" + "=" * 80
    print "PHASE 2: FETCHING GITHUB DIFFS (Rate-limited, may take a while)"
    print "=" * 80
    
    for data in versions_data:
        version = data['version']
        issues = data['issues']
        
        output_dir = "Release_Data_{0}_{1}".format(args.component, version)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        print "\n--- Processing GitHub diffs for {0} ---".format(version)
        write_github_files_per_commit(issues, args.component, output_dir)
        print "  -> Done! Diffs saved to folder: {0}/".format(os.path.abspath(output_dir))
        
    print "\nBatch process completely finished!"
