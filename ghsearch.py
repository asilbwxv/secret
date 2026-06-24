import urllib
import urllib2
import json
import codecs
import argparse
import sys
import os
import time

# --- CONFIGURATION ---
GITHUB_API_URL = "https://gheprivate.intra.corp/api/v3" 
GITHUB_TOKEN = "YOUR_WORKING_GITHUB_TOKEN_HERE"
GITHUB_ORG = "software-avionics"

REQUEST_DELAY = 0.5  # Polite delay

# --- HELPER FUNCTIONS ---

def safe_unicode(value):
    if value is None: return u"N/A"
    if isinstance(value, unicode): return value
    if isinstance(value, dict) or isinstance(value, list): return unicode(json.dumps(value))
    return unicode(str(value), 'utf-8', errors='replace')

def make_gh_request(url, accept_header="application/vnd.github.v3+json"):
    req = urllib2.Request(url)
    req.add_header("Authorization", "Bearer " + GITHUB_TOKEN)
    req.add_header("Accept", accept_header)
    time.sleep(REQUEST_DELAY)
    
    for attempt in range(3):
        try:
            resp = urllib2.urlopen(req)
            return json.loads(resp.read())
        except urllib2.HTTPError as e:
            if e.code == 422: return None # Validation failed / No results
            elif e.code in (403, 429):
                retry = e.headers.get('Retry-After')
                time.sleep((int(retry) + 1) if retry else 5 * (attempt + 1))
                continue
            return None
        except Exception:
            return None
    return None

# --- SEARCH ENGINES ---

def search_code(query):
    print " -> Searching Code..."
    # Code searches MUST scope to an org, user, or repo
    q = "{0} org:{1}".format(query, GITHUB_ORG)
    url = "{0}/search/code?q={1}&per_page=50".format(GITHUB_API_URL, urllib.quote_plus(q))
    data = make_gh_request(url)
    
    results = []
    if data and 'items' in data:
        for item in data['items']:
            results.append({
                'name': item.get('name'),
                'path': item.get('path'),
                'repo': item.get('repository', {}).get('name'),
                'url': item.get('html_url'),
                'sha': item.get('sha')
            })
    return results

def search_commits(query):
    print " -> Searching Commits..."
    q = "{0} org:{1}".format(query, GITHUB_ORG)
    url = "{0}/search/commits?q={1}&per_page=50".format(GITHUB_API_URL, urllib.quote_plus(q))
    # Commits search requires a specific preview header
    data = make_gh_request(url, accept_header="application/vnd.github.cloak-preview+json")
    
    results = []
    if data and 'items' in data:
        for item in data['items']:
            results.append({
                'message': item.get('commit', {}).get('message', '').split('\n')[0],
                'author': item.get('commit', {}).get('author', {}).get('name'),
                'repo': item.get('repository', {}).get('name'),
                'url': item.get('html_url'),
                'sha': item.get('sha')
            })
    return results

def search_issues(query):
    print " -> Searching Issues & Pull Requests..."
    q = "{0} org:{1}".format(query, GITHUB_ORG)
    url = "{0}/search/issues?q={1}&per_page=50".format(GITHUB_API_URL, urllib.quote_plus(q))
    data = make_gh_request(url)
    
    results = []
    if data and 'items' in data:
        for item in data['items']:
            results.append({
                'title': item.get('title'),
                'state': item.get('state'),
                'type': 'PR' if 'pull_request' in item else 'Issue',
                'url': item.get('html_url'),
                'number': item.get('number')
            })
    return results

# --- REPORT GENERATORS ---

def write_txt_reports(code_res, commit_res, issue_res, out_dir):
    print " -> Generating .txt reports..."
    
    # 1. Code Report
    with codecs.open(os.path.join(out_dir, "01_Code_Results.txt"), 'w', 'utf-8') as f:
        f.write(u"=== CODE SEARCH RESULTS ===\n\n")
        for r in code_res:
            f.write(u"REPO: {0}\nFILE: {1}\nSHA:  {2}\nURL:  {3}\n\n".format(
                safe_unicode(r['repo']), safe_unicode(r['path']), safe_unicode(r['sha']), safe_unicode(r['url'])
            ))

    # 2. Commit Report
    with codecs.open(os.path.join(out_dir, "02_Commit_Results.txt"), 'w', 'utf-8') as f:
        f.write(u"=== COMMIT SEARCH RESULTS ===\n\n")
        for r in commit_res:
            f.write(u"REPO:   {0}\nAUTHOR: {1}\nMSG:    {2}\nSHA:    {3}\nURL:    {4}\n\n".format(
                safe_unicode(r['repo']), safe_unicode(r['author']), safe_unicode(r['message']), safe_unicode(r['sha']), safe_unicode(r['url'])
            ))

    # 3. Issue Report
    with codecs.open(os.path.join(out_dir, "03_Issue_Results.txt"), 'w', 'utf-8') as f:
        f.write(u"=== ISSUE & PR SEARCH RESULTS ===\n\n")
        for r in issue_res:
            f.write(u"TYPE:  {0} #{1}\nSTATE: {2}\nTITLE: {3}\nURL:   {4}\n\n".format(
                safe_unicode(r['type']), safe_unicode(r['number']), safe_unicode(r['state']), safe_unicode(r['title']), safe_unicode(r['url'])
            ))

def write_html_dashboard(query_label, code_res, commit_res, issue_res, out_dir):
    print " -> Generating HTML Dashboard..."
    html_path = os.path.join(out_dir, "Search_Dashboard.html")
    
    # CSS & HTML Template
    html = u"""<!DOCTYPE html>
<html>
<head>
    <title>Universal Search: {query}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; background-color: #f6f8fa; color: #24292e; margin: 0; padding: 20px; }}
        h1 {{ border-bottom: 1px solid #eaecef; padding-bottom: 10px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .card {{ background: #fff; border: 1px solid #e1e4e8; border-radius: 6px; margin-bottom: 20px; padding: 15px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
        .card-header {{ font-size: 1.2em; font-weight: 600; margin-bottom: 10px; color: #0366d6; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #e1e4e8; font-size: 14px; }}
        th {{ background-color: #f6f8fa; }}
        a {{ color: #0366d6; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .sha {{ font-family: monospace; background: #f0f3f6; padding: 2px 6px; border-radius: 3px; font-size: 12px; }}
        .badge {{ padding: 3px 8px; border-radius: 2em; font-size: 12px; font-weight: 600; color: #fff; }}
        .badge.open {{ background-color: #28a745; }}
        .badge.closed {{ background-color: #cb2431; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Universal Search Results: <i>{query}</i></h1>
""".format(query=safe_unicode(query_label))

    # --- CODE SECTION ---
    html += u"""<div class="card"><div class="card-header">Code Results ({0})</div><table>
        <tr><th>Repository</th><th>File Path</th><th>SHA</th><th>Link</th></tr>""".format(len(code_res))
    for r in code_res:
        html += u"<tr><td>{0}</td><td>{1}</td><td><span class='sha'>{2}</span></td><td><a href='{3}' target='_blank'>View File</a></td></tr>".format(
            safe_unicode(r['repo']), safe_unicode(r['path']), safe_unicode(r['sha'][:7]), safe_unicode(r['url'])
        )
    html += u"</table></div>"

    # --- COMMIT SECTION ---
    html += u"""<div class="card"><div class="card-header">Commit Results ({0})</div><table>
        <tr><th>Repository</th><th>Message</th><th>Author</th><th>SHA</th><th>Link</th></tr>""".format(len(commit_res))
    for r in commit_res:
        html += u"<tr><td>{0}</td><td>{1}</td><td>{2}</td><td><span class='sha'>{3}</span></td><td><a href='{4}' target='_blank'>View Commit</a></td></tr>".format(
            safe_unicode(r['repo']), safe_unicode(r['message']), safe_unicode(r['author']), safe_unicode(r['sha'][:7]), safe_unicode(r['url'])
        )
    html += u"</table></div>"

    # --- ISSUE SECTION ---
    html += u"""<div class="card"><div class="card-header">Issues & Pull Requests ({0})</div><table>
        <tr><th>Type</th><th>State</th><th>Title</th><th>Link</th></tr>""".format(len(issue_res))
    for r in issue_res:
        state_class = "open" if r['state'] == "open" else "closed"
        html += u"<tr><td>{0} #{1}</td><td><span class='badge {2}'>{3}</span></td><td>{4}</td><td><a href='{5}' target='_blank'>View Ticket</a></td></tr>".format(
            safe_unicode(r['type']), safe_unicode(r['number']), state_class, safe_unicode(r['state'].upper()), safe_unicode(r['title']), safe_unicode(r['url'])
        )
    html += u"</table></div>"

    html += u"</div></body></html>"
    
    with codecs.open(html_path, 'w', 'utf-8') as f:
        f.write(html)

# --- MAIN EXECUTION ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Universal Searcher: Scrape GitHub for code, commits, and issues.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--word", nargs="+", help="Search for specific keywords (e.g., --word blinking synchro)")
    group.add_argument("--dir", help="Search for a specific directory path (e.g., --dir src/verif/integration)")
    group.add_argument("--file", help="Search for a specific filename (e.g., --file main.c)")
    group.add_argument("--ticket", help="Search for a specific Jira ticket across GitHub (e.g., --ticket C00153-281)")
    
    args = parser.parse_args()
    
    # 1. Format the query based on the mode
    if args.word:
        raw_query = " ".join(args.word)
        github_query = raw_query
        folder_name = "Search_Word_{0}".format(raw_query.replace(" ", "_"))
    elif args.dir:
        raw_query = args.dir
        github_query = "path:{0}".format(args.dir)
        folder_name = "Search_Dir_{0}".format(args.dir.replace("/", "_"))
    elif args.file:
        raw_query = args.file
        github_query = "filename:{0}".format(args.file)
        folder_name = "Search_File_{0}".format(args.file.replace(".", "_"))
    elif args.ticket:
        raw_query = args.ticket
        github_query = args.ticket
        folder_name = "Search_Ticket_{0}".format(args.ticket)

    print "=" * 60
    print " UNIVERSAL SEARCH INITIATED: {0}".format(raw_query)
    print "=" * 60

    # 2. Execute parallel searches
    code_results = search_code(github_query)
    commit_results = search_commits(github_query)
    issue_results = search_issues(github_query)
    
    # 3. Create Output Directory
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)
        
    # 4. Generate Reports
    write_txt_reports(code_results, commit_results, issue_results, folder_name)
    write_html_dashboard(raw_query, code_results, commit_results, issue_results, folder_name)
    
    print "\nProcess Complete! All data saved to: {0}/".format(os.path.abspath(folder_name))
    print " -> Open 'Search_Dashboard.html' in your web browser to view the unified interface."
