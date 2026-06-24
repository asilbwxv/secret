# -*- coding: utf-8 -*-
# jira_client.py
import requests
import urllib3
import time
import sys
import os
import argparse
import codecs
from config import JIRA_BASE_URL, JIRA_TOKEN, REQUEST_DELAY

# Import the diff generator directly from our GitHub client
from github import write_github_diffs

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def safe_str(value):
    """Safely converts any data type to string to prevent crashes."""
    if value is None:
        return "N/A"
    if isinstance(value, dict) or isinstance(value, list):
        import json
        return json.dumps(value, indent=2)
    return str(value)

def get_jira_issues(jql_query):
    """Fetches Jira issues based on a JQL query."""
    print("[*] Fetching Jira tickets for JQL: {}".format(jql_query))
    url = "{}/rest/api/2/search".format(JIRA_BASE_URL)
    headers = {"Authorization": "Bearer {}".format(JIRA_TOKEN), "Accept": "application/json"}
    params = {'jql': jql_query, 'maxResults': 100, 'expand': 'names'}

    time.sleep(REQUEST_DELAY)
    try:
        response = requests.get(url, headers=headers, params=params, verify=False)
        response.raise_for_status()
        return response.json().get('issues', [])
    except requests.exceptions.RequestException as e:
        print("[!] Jira API Error: {}".format(e))
        return []

def write_jira_file(issues, filename, jql):
    """Parses Jira issues and writes them to a formatted text document."""
    with codecs.open(filename, 'w', 'utf-8') as f:
        f.write("JIRA RELEASE NOTES FOR: {}\n".format(jql))
        f.write("=" * 80 + "\n\n")
        
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
            
            f.write("TICKET: {}\n".format(key))
            f.write("-" * 80 + "\n")
            
            for label, value in target_fields:
                if value is not None and value != "" and value != [] and value != {}:
                    f.write("{}:\n{}\n\n".format(label, safe_str(value)))
                    
            f.write("=" * 80 + "\n\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Airbus Jira to AI Context Extractor\n\nFetches Jira tickets and orchestrates GitHub to pull corresponding branch diffs.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    # Mutually exclusive group so you can't use -t and -r at the same time
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-t", "--tickets", nargs="+", help="TICKET MODE: Fetch specific tickets (e.g., -t C00216-151 C00216-200)")
    group.add_argument("-r", "--release", nargs=2, metavar=('COMPONENT', 'VERSION'), help="RELEASE MODE: Fetch all tickets for a release (e.g., -r C00216 1.5.0)")
    
    parser.add_argument("-b", "--branch", default="develop", help="Base branch to compare diffs against (Defaults to 'develop')")

    # Spawn help menu if no arguments are passed
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    # ==========================================
    # MODE 1: SELECTED TICKETS (-t)
    # ==========================================
    if args.tickets:
        # Auto-extract component name from the first ticket (e.g., "C00216-151" -> "C00216")
        component = args.tickets[0].split('-')[0].upper()
        
        print("=" * 80)
        print("SELECTED TICKETS MODE FOR {}".format(component))
        print("=" * 80)
        
        ticket_list_str = ", ".join(['"{}"'.format(t) for t in args.tickets])
        jql_query = 'key in ({})'.format(ticket_list_str)
        
        issues = get_jira_issues(jql_query)
        if not issues:
            print("  -> No issues found or failed to connect.")
            sys.exit(1)
            
        print("  -> Successfully fetched {} tickets from Jira.".format(len(issues)))
        
        # We reuse the workspace logic from github_client
        safe_branch = args.branch.replace('/', '_')
        output_dir = "{}_{}".format(component, safe_branch)
        if not os.path.exists(output_dir): os.makedirs(output_dir)
            
        jira_filename = os.path.join(output_dir, "{}_Selected_Tickets.txt".format(component))
        write_jira_file(issues, jira_filename, jql_query)
        
        print("\n[*] Fetching GitHub Diffs for Selected Tickets...")
        ticket_keys = [i['key'] for i in issues]
        write_github_diffs(ticket_keys, component, args.branch)
        
        print("\n[+] Process complete! Jira notes and diffs saved to {}/".format(output_dir))

    # ==========================================
    # MODE 2: RELEASE BATCH (-r)
    # ==========================================
    elif args.release:
        component = args.release[0].upper()
        version = args.release[1]
        
        print("=" * 80)
        print("RELEASE MODE FOR {} - VERSION {}".format(component, version))
        print("=" * 80)
        
        jql_query = 'project = "{}" AND fixVersion = "{}"'.format(component, version)
        
        issues = get_jira_issues(jql_query)
        if not issues:
            print("  -> No issues found for that release.")
            sys.exit(1)
            
        print("  -> Successfully fetched {} tickets from Jira.".format(len(issues)))
        
        safe_branch = args.branch.replace('/', '_')
        output_dir = "{}_{}".format(component, safe_branch)
        if not os.path.exists(output_dir): os.makedirs(output_dir)
            
        jira_filename = os.path.join(output_dir, "{}_Release_{}.txt".format(component, version.replace('.', '_')))
        write_jira_file(issues, jira_filename, jql_query)
        
        print("\n[*] Fetching GitHub Diffs for Release {}...".format(version))
        ticket_keys = [i['key'] for i in issues]
        write_github_diffs(ticket_keys, component, args.branch)
        
        print("\n[+] Release process complete! Jira notes and diffs saved to {}/".format(output_dir))
