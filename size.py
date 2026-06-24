#!/usr/bin/env python2
# -*- coding: utf-8 -*-

import BaseHTTPServer
import json
import urllib2
import urllib
import urlparse
import base64
import os
import re
import ssl
import codecs
import threading
import time
import shutil

# --- CONFIGURATION ---
PORT_NUMBER = 8080
MAP_FILE = "components_map.txt"
CACHE_FILE = "dashboard_cache.json"

# Artifactory
ARTIFACTORY_BASE = "https://cisas.eu.airbus.corp:8643/artifactory"
ARTIFACTORY_AUTH = ("asilbwxv", "cmVmdGtuOjAxOjE3OTA4OTc0ODE6ZE1jNWx2aWhnSGNjT0hnUFhmTjJNSjBzR1lN")

# GitHub Enterprise
GITHUB_API_URL = "https://gheprivate.intra.corp/api/v3" 
GITHUB_TOKEN = "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"
GITHUB_ORG = "software-avionics"

# Jira
JIRA_BASE_URL = "https://cisas.eu.airbus.corp:8343/1V32-jira"
JIRA_TOKEN = "MTc5NDU1MzU0NTE0OnrZeM3tRaBlXJPW5RaP1njINC5d"

# API Politeness
REQUEST_DELAY = 0.1

# Bypass SSL verification
try:
    CTX = ssl._create_unverified_context()
except AttributeError:
    CTX = None

# --- CACHE SYSTEM ---
if os.path.exists(CACHE_FILE):

    try:
        with open(CACHE_FILE, 'r') as f:
            API_CACHE = json.load(f)
    except Exception:
        API_CACHE = {"versions": {}, "github_files": {}}
else:
    API_CACHE = {"versions": {}, "github_files": {}}

def save_cache():
    with open(CACHE_FILE, 'w') as f:
        json.dump(API_CACHE, f)

# --- HELPER FUNCTIONS ---
def safe_unicode(value):
    if value is None: return u"N/A"
    if isinstance(value, unicode): return value
    if isinstance(value, dict) or isinstance(value, list): return unicode(json.dumps(value, indent=2))
    return unicode(str(value), 'utf-8', errors='replace')

def read_components_map():
    mapping = []
    if not os.path.isfile(MAP_FILE): return mapping
    with codecs.open(MAP_FILE, "r", "utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line: continue
            m = re.match(r"^(C\d{5})\s+(.+)$", line, flags=re.IGNORECASE)
            if m: mapping.append({"code": m.group(1).upper(), "name": m.group(2).strip()})
    return mapping

def make_api_request(url, token, auth_type="Bearer", accept_header="application/json"):
    req = urllib2.Request(url)
    req.add_header("Authorization", auth_type + " " + token)
    req.add_header("Accept", accept_header)
    time.sleep(REQUEST_DELAY)
    
    for attempt in range(3):
        try:
            return urllib2.urlopen(req, context=CTX).read() if CTX else urllib2.urlopen(req).read()
        except urllib2.HTTPError as e:
            if e.code in (422, 404): return None
            elif e.code in (403, 429):
                retry_after = e.headers.get('Retry-After')
                sleep_time = int(retry_after) + 1 if retry_after else 5 * (attempt + 1)
                print "  [!] Rate limited. Sleeping for {0}s...".format(sleep_time)
                time.sleep(sleep_time)
                continue
            else:
                return None
        except Exception:
            return None
    return None

# --- CORE API LOGIC ---
def fetch_artifactory_versions(component_code):
    if component_code in API_CACHE["versions"]:
        return API_CACHE["versions"][component_code]

    package_path = "com/airbus/avsw/{0}/{0}".format(component_code)
    all_versions = []
    auth_string = base64.b64encode("{0}:{1}".format(ARTIFACTORY_AUTH[0], ARTIFACTORY_AUTH[1]))

    for repo in ["avionics-software-release", "avionics-software-snapshot"]:
        api_url = "{0}/api/storage/{1}/{2}".format(ARTIFACTORY_BASE, repo, package_path)
        data_raw = make_api_request(api_url, auth_string, auth_type="Basic")
        if data_raw:
            data = json.loads(data_raw)
            if 'children' in data:
                for child in data['children']:
                    if child.get('folder') is True:
                        all_versions.append({"version": child['uri'].lstrip('/'), "repo": repo})
            
    releases = [v for v in all_versions if 'snapshot' not in v['repo']]
    snapshots = [v for v in all_versions if 'snapshot' in v['repo']]
    releases.sort(key=lambda x: x['version'], reverse=True)
    snapshots.sort(key=lambda x: x['version'], reverse=True)
    
    final_versions = releases + snapshots
    API_CACHE["versions"][component_code] = final_versions
    save_cache()
    return final_versions

def fetch_github_files(code):
    if code in API_CACHE["github_files"]:
        return API_CACHE["github_files"][code]

    branch = "master"
    url = "{0}/repos/{1}/{2}/git/trees/{3}?recursive=1".format(GITHUB_API_URL, GITHUB_ORG, code, branch)
    data_raw = make_api_request(url, GITHUB_TOKEN, accept_header="application/vnd.github.v3+json")
    
    if not data_raw:
        branch = "main"
        url = "{0}/repos/{1}/{2}/git/trees/{3}?recursive=1".format(GITHUB_API_URL, GITHUB_ORG, code, branch)
        data_raw = make_api_request(url, GITHUB_TOKEN, accept_header="application/vnd.github.v3+json")

    if not data_raw:
        result = {"error": "Repository or default branch not found."}
        API_CACHE["github_files"][code] = result
        save_cache()
        return result

    tree = json.loads(data_raw).get("tree", [])
    result = {"branch": branch, "docs": {"AD": None, "SD": None, "SID": None, "UG": None}, "cram": []}
    up_code = code.upper()

    for item in tree:
        if item.get("type") != "blob": continue
        path = item.get("path", "")
        lp, basename = path.lower(), path.split("/")[-1]
        up_base = basename.upper()

        if up_code in up_base:
            if lp.endswith(".html"):
                for t in ["AD", "SD", "SID", "UG"]:
                    if t in up_base and (not result["docs"][t] or path.count("/") < result["docs"][t].count("/")):
                        result["docs"][t] = path
            if lp.endswith(".xlsm"):
                if "CRAM_UG" in up_base:
                    result["cram"].append({"path": path, "label": "CRAM_UG"})
                elif "RAM-HLR" in up_base:
                    result["cram"].append({"path": path, "label": "RAM-HLR"})

    API_CACHE["github_files"][code] = result
    save_cache()
    return result

# --- BACKGROUND WORKERS ---
def generate_diffs_worker(component, version):
    print "\n[BACKGROUND] Starting Diff generation for {0} v{1}".format(component, version)
    output_dir = "Release_Data_{0}_{1}".format(component, version)
    if os.path.exists(output_dir): shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    jql = 'project = {0} AND fixVersion = "{1}"'.format(component, version)
    params = {'jql': jql, 'maxResults': 100, 'expand': 'names'}
    jira_url = JIRA_BASE_URL + "/rest/api/2/search?" + urllib.urlencode(params)
    
    jira_data = make_api_request(jira_url, JIRA_TOKEN)
    issues = json.loads(jira_data).get('issues', []) if jira_data else []
    
    if not issues:
        print "  -> No Jira issues found for {0} v{1}.".format(component, version)
        return

    jira_filename = os.path.join(output_dir, "00_RD_{0}_{1}.txt".format(component, version))
    with codecs.open(jira_filename, 'w', 'utf-8') as f:
        f.write(u"JIRA RELEASE NOTES FOR: {0}\n".format(jql))
        f.write(u"=" * 80 + u"\n\n")
        for issue in issues:
            key, fields = issue.get('key', 'UNKNOWN'), issue.get('fields', {})
            f.write(u"TICKET: {0}\n".format(key))
            f.write(u"-" * 80 + u"\n")
            for label, val in [('Summary', fields.get('summary')), ('Description', fields.get('description')), ('Solution Description', fields.get('customfield_11107'))]:
                if val: f.write(u"{0}:\n{1}\n\n".format(label, safe_unicode(val)))
            f.write(u"=" * 80 + u"\n\n")

    for issue in issues:
        ticket_key = issue.get('key')
        search_query = "{0} repo:{1}/{2}".format(ticket_key, GITHUB_ORG, component)
        search_url = GITHUB_API_URL + "/search/commits?" + urllib.urlencode({'q': search_query, 'sort': 'author-date', 'order': 'asc'})
        
        search_data = make_api_request(search_url, GITHUB_TOKEN, accept_header="application/vnd.github.v3+json")
        commits = json.loads(search_data).get('items', []) if search_data else []
        if not commits: continue
        
        agg_filepath = os.path.join(output_dir, "{0}_All_Diffs.txt".format(ticket_key))
        with codecs.open(agg_filepath, 'w', 'utf-8') as agg_file:
            agg_file.write(u"AGGREGATED DIFFS FOR TICKET: {0}\n".format(ticket_key))
            agg_file.write(u"=" * 80 + u"\n\n")
            for commit in commits:
                sha, msg = commit.get('sha'), commit.get('commit', {}).get('message', '').split('\n')[0]
                diff_url = "{0}/repos/{1}/{2}/commits/{3}".format(GITHUB_API_URL, GITHUB_ORG, component, sha)
                raw_diff = make_api_request(diff_url, GITHUB_TOKEN, accept_header="application/vnd.github.v3.diff")
                if raw_diff:
                    agg_file.write(u"COMMIT: {0}\nMESSAGE: {1}\nDIFF:\n{2}\n{3}\n\n".format(sha, safe_unicode(msg), safe_unicode(raw_diff), u"~" * 80))

    print "[BACKGROUND] Completed Diff generation for {0} v{1} -> {2}/".format(component, version, output_dir)

def categorize_file(rel_path):
    n = rel_path.replace('\\', '/').lower()
    base = n.split('/')[-1]
    if n.startswith('src/plan/'): return '0_PLAN'
    if n.startswith('src/spec/'): return '1_SPEC_ARCHI'
    if n.startswith('src/design/') or base in ('.dcsl_derog', '.codda_derog'): return '2_DESIGN'
    if n.startswith('src/main/c/') or n.startswith('src/main/header/') or n.startswith('src/main/asm/') or base in ('.checkc_derog', '.fanc_derog'): return '3_CODE'
    if n.startswith('src/verif/unit-test/'): return '4_UNIT_VERIF'
    if n.startswith('src/verif/integration/') or n.startswith('src/toolchain/toolchain-titv/') or n.startswith('src/toolchain/toolchain-tienvbuild/'): return '5_INTEG_VERIF'
    if n.startswith('src/delivery-doc/'): return '7_USER_GUIDE'
    if base in ('data.gradle', 'jenkinsfile'): return '6_ENVIRONMENT'
    return None

def generate_phases_worker(component, version):
    print "\n[BACKGROUND] Starting Phases Extraction for {0} v{1}".format(component, version)
    output_dir = "Phases_{0}_{1}".format(component, version)
    if os.path.exists(output_dir): shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    possible_refs = [version, "v" + version, "{0}-{1}".format(component, version), "master", "main"]
    tree_data = None
    target_ref = version

    for ref in possible_refs:
        tree_url = "{0}/repos/{1}/{2}/git/trees/{3}?recursive=1".format(GITHUB_API_URL, GITHUB_ORG, component, urllib.quote(ref.encode('utf-8')))
        tree_data = make_api_request(tree_url, GITHUB_TOKEN, accept_header="application/vnd.github.v3+json")
        if tree_data:
            target_ref = ref
            print "  -> Found Git Tree using reference: {0}".format(ref)
            break
            
    if not tree_data:
        print "  [!] Could not find Git Tree for version tag '{0}'. Check if tag exists on GitHub.".format(version)
        return

    items = json.loads(tree_data).get("tree", [])
    phases_map = {
        '0_PLAN': [], '1_SPEC_ARCHI': [], '2_DESIGN': [], '3_CODE': [],
        '4_UNIT_VERIF': [], '5_INTEG_VERIF': [], '6_ENVIRONMENT': [], '7_USER_GUIDE': []
    }

    excluded_exts = ('.xlsx', '.xlsm', '.jar', '.html', '.pdf', '.rqtfimage')
    excluded_dirs = ['external', 'build', 'tmp']

    for item in items:
        if item.get("type") != "blob": continue
        path = item.get("path", "")
        if path.lower().endswith(excluded_exts) or path.split('/')[-1].lower() == 'rqtfimage': continue
        if any(ex in path.lower().split('/') for ex in excluded_dirs): continue
        cat = categorize_file(path)
        if cat in phases_map:
            phases_map[cat].append(path)

    files_processed = 0
    for cat, paths in phases_map.items():
        if not paths: continue
        paths.sort(key=lambda x: (x.split('/')[-1].lower(), x.lower()))
        out_name = os.path.join(output_dir, "{0}_{1}.txt".format(component, cat))
        
        with codecs.open(out_name, 'w', 'utf-8') as out:
            for p in paths:
                safe_path = urllib.quote(p.encode('utf-8'), safe='/')
                safe_ref = urllib.quote(target_ref.encode('utf-8'))
                raw_url = "{0}/repos/{1}/{2}/contents/{3}?ref={4}".format(GITHUB_API_URL, GITHUB_ORG, component, safe_path, safe_ref)
                content = make_api_request(raw_url, GITHUB_TOKEN, accept_header="application/vnd.github.v3.raw")
                if content is not None:
                    out.write(u"{0}:\n\n".format(p.split('/')[-1]))
                    out.write(safe_unicode(content))
                    out.write(u"\n\n")
                    files_processed += 1

    print "[BACKGROUND] Completed Phases. Downloaded {0} files for {1} v{2} -> {3}/".format(files_processed, component, version, output_dir)


# --- WEB SERVER HANDLER ---
class DashboardHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    
    def log_message(self, format, *args):
        """Silences standard HTTP GET logging to prevent terminal spam."""
        if "GET /api/" in args[0] or "GET / HTTP" in args[0]:
            return
        BaseHTTPServer.BaseHTTPRequestHandler.log_message(self, format, *args)

    def do_GET(self):
        if self.path == "/": self.serve_html()
        elif self.path == "/api/init_data":
            # Pass components and the entire cache in a single request to eliminate front-end spam
            self.serve_json({
                "components": read_components_map(),
                "cache": API_CACHE
            })
        elif self.path.startswith("/api/versions?comp="):
            parsed = urlparse.urlparse(self.path)
            self.serve_json(fetch_artifactory_versions(dict(urlparse.parse_qsl(parsed.query)).get('comp')))
        elif self.path.startswith("/api/github_files?comp="):
            parsed = urlparse.urlparse(self.path)
            self.serve_json(fetch_github_files(dict(urlparse.parse_qsl(parsed.query)).get('comp')))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/clear_cache":
            global API_CACHE
            API_CACHE = {"versions": {}, "github_files": {}}
            if os.path.exists(CACHE_FILE): os.remove(CACHE_FILE)
            self.serve_json({"status": "Cache cleared"})
            print "\n[*] Cache manually cleared by user."
        
        elif self.path.startswith("/api/generate_diffs"):
            parsed = urlparse.urlparse(self.path)
            params = dict(urlparse.parse_qsl(parsed.query))
            comp, ver = params.get('comp'), params.get('version')
            
            t = threading.Thread(target=generate_diffs_worker, args=(comp, ver))
            t.daemon = True
            t.start()
            self.serve_json({"message": "Diffs for {0} v{1} are generating in the background.".format(comp, ver)})
            
        elif self.path.startswith("/api/generate_phases"):
            parsed = urlparse.urlparse(self.path)
            params = dict(urlparse.parse_qsl(parsed.query))
            comp, ver = params.get('comp'), params.get('version')
            
            t = threading.Thread(target=generate_phases_worker, args=(comp, ver))
            t.daemon = True
            t.start()
            self.serve_json({"message": "Phases for {0} v{1} are extracting in the background.".format(comp, ver)})
            
        else:
            self.send_response(404)
            self.end_headers()

    def serve_json(self, data):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data))

    def serve_html(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        
        html = """<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Avionics Component Dashboard</title>
    <style>
        body { font-family: system-ui, sans-serif; background: #f4f5f7; margin: 0; padding: 20px; color: #333; }
        .wrap { max-width: 1400px; margin: 0 auto; background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; vertical-align: middle; }
        th { background: #f8f9fa; font-weight: 600; }
        select { padding: 6px 12px; border-radius: 4px; border: 1px solid #ccc; font-size: 13px; }
        
        button { 
            padding: 6px 12px; 
            border-radius: 4px; 
            border: 1px solid #ccc; 
            font-size: 11px; 
            font-weight: bold;
            text-transform: uppercase;
            background: #0052cc; 
            color: white; 
            cursor: pointer; 
            margin-right: 8px; 
            transition: opacity 0.2s;
        }
        button:hover:not(:disabled) { background: #0043a6; }
        button:disabled { background: #cccccc; color: #666; cursor: not-allowed; opacity: 0.7;}
        
        .status { font-size: 12px; color: #666; font-style: italic; }
        a.repo-link { color: #0052cc; text-decoration: none; }
        a.repo-link:hover { text-decoration: underline; }
        .chip-container { display: flex; flex-wrap: wrap; gap: 6px; }
        .chip { padding: 3px 8px; border-radius: 999px; text-decoration: none; background: #e3fcef; color: #006644; border: 1px solid #00a671; font-size: 11px; font-weight: bold; }
        .chip:hover { background: #b3f5d1; }
        .chip-cram { background: #deebff; color: #0747a6; border: 1px solid #4c9aff; }
        .chip-cram:hover { background: #b3d4ff; }
        .footer-tools { margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; text-align: right; }
        .footer-tools button { background: #ff5630; }
        .footer-tools button:hover { background: #de350b; }
        .snap-warn { font-size: 11px; color: #ff5630; display: block; margin-top: 4px; }
    </style>
</head>
<body>
<div class="wrap">
    <h1>Component Dashboard</h1>
    <p>Loading components and cache data...</p>
    
    <table>
        <thead>
            <tr>
                <th>Component</th>
                <th>Name</th>
                <th>GitHub Docs & Files</th>
                <th>Target Version</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody id="table-body"></tbody>
    </table>

    <div class="footer-tools">
        <button onclick="clearCache()">RESCAN & CLEAR CACHE</button>
    </div>
</div>

<script>
    const GHE_BASE_URL = "https://gheprivate.intra.corp/software-avionics";

    // Request the components and entire existing cache in one single call
    fetch('/api/init_data')
        .then(response => response.json())
        .then(data => {
            const tbody = document.getElementById('table-body');
            const components = data.components;
            const cache = data.cache;

            components.forEach(comp => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong><a class="repo-link" href="${GHE_BASE_URL}/${comp.code}" target="_blank">${comp.code}</a></strong></td>
                    <td>${comp.name}</td>
                    <td id="files-${comp.code}"><span class="status">Loading...</span></td>
                    <td id="version-col-${comp.code}"><span class="status">Loading...</span></td>
                    <td id="actions-${comp.code}">
                        <button disabled>RELEASE NOTES</button>
                        <button disabled>JIRA</button>
                        <button disabled>GEN DIFFS</button>
                        <button disabled>GEN PHASES</button>
                    </td>
                `;
                tbody.appendChild(tr);
                
                // Use Cache instantly if it exists, otherwise queue the network request
                if (cache.versions && cache.versions[comp.code]) {
                    renderVersions(comp.code, cache.versions[comp.code]);
                } else {
                    fetchVersions(comp.code);
                }

                if (cache.github_files && cache.github_files[comp.code]) {
                    renderGitHubFiles(comp.code, cache.github_files[comp.code]);
                } else {
                    fetchGitHubFiles(comp.code);
                }
            });
        });

    function fetchVersions(code) {
        fetch('/api/versions?comp=' + code)
            .then(response => response.json())
            .then(versions => renderVersions(code, versions));
    }

    function renderVersions(code, versions) {
        const td = document.getElementById('version-col-' + code);
        const actionsTd = document.getElementById('actions-' + code);
        
        if (!versions || versions.length === 0) {
            td.innerHTML = '<span class="status">No versions found</span>';
            return;
        }

        const rels = versions.filter(v => !v.repo.includes('snapshot'));
        const snaps = versions.filter(v => v.repo.includes('snapshot'));

        let selectHtml = `<select id="sel-${code}" onchange="updateButtonState('${code}')">`;
        
        if (rels.length > 0) {
            selectHtml += `<optgroup label="Releases">`;
            rels.forEach(v => { selectHtml += `<option value="${v.version}" data-repo="${v.repo}">${v.version}</option>`; });
            selectHtml += `</optgroup>`;
        }
        if (snaps.length > 0) {
            selectHtml += `<optgroup label="Snapshots">`;
            snaps.forEach(v => { selectHtml += `<option value="${v.version}" data-repo="${v.repo}">${v.version}</option>`; });
            selectHtml += `</optgroup>`;
        }

        selectHtml += `</select><span id="warn-${code}" class="snap-warn" style="display:none;">View-only mode (Snapshot)</span>`;
        td.innerHTML = selectHtml;

        actionsTd.innerHTML = `
            <button id="rn-${code}" onclick="openReleaseNotes('${code}')">RELEASE NOTES</button>
            <button id="jira-${code}" onclick="openJira('${code}')">JIRA</button>
            <button id="diffs-${code}" onclick="generateDiffs('${code}')">GEN DIFFS</button>
            <button id="phases-${code}" onclick="generatePhases('${code}')">GEN PHASES</button>
        `;
        
        updateButtonState(code);
    }
    
    function updateButtonState(code) {
        const sel = document.getElementById('sel-' + code);
        const repo = sel.options[sel.selectedIndex].getAttribute('data-repo');
        const isSnap = repo.includes('snapshot');
        
        document.getElementById('rn-' + code).disabled = isSnap;
        document.getElementById('jira-' + code).disabled = isSnap;
        document.getElementById('diffs-' + code).disabled = isSnap;
        document.getElementById('phases-' + code).disabled = isSnap;
        document.getElementById('warn-' + code).style.display = isSnap ? 'block' : 'none';
    }

    function fetchGitHubFiles(code) {
        fetch('/api/github_files?comp=' + code)
            .then(response => response.json())
            .then(data => renderGitHubFiles(code, data));
    }

    function renderGitHubFiles(code, data) {
        const td = document.getElementById('files-' + code);
        if (data.error) {
            td.innerHTML = `<span class="status" style="color:red;">Error: ${data.error}</span>`;
            return;
        }

        let html = '<div class="chip-container">';
        let foundAny = false;

        ["AD", "SD", "SID", "UG"].forEach(t => {
            if (data.docs[t]) {
                html += `<a class="chip" href="${GHE_BASE_URL}/${code}/blob/${data.branch}/${data.docs[t]}" target="_blank">${t}</a>`;
                foundAny = true;
            }
        });

        if (data.cram && data.cram.length > 0) {
            data.cram.forEach(c => {
                html += `<a class="chip chip-cram" href="${GHE_BASE_URL}/${code}/raw/${data.branch}/${c.path}" title="${c.path}">${c.label}</a>`;
                foundAny = true;
            });
        }

        td.innerHTML = foundAny ? html + '</div>' : '<span class="status">No tracked docs found</span>';
    }

    function openReleaseNotes(code) {
        const sel = document.getElementById('sel-' + code);
        const version = sel.value;
        const repo = sel.options[sel.selectedIndex].getAttribute('data-repo');
        window.open(`https://cisas.eu.airbus.corp:8643/ui/api/v1/download/contentBrowsing/${repo}/com/airbus/avsw/${code}/${code}/${version}/${code}-${version}.tar.gz!/${code}/build/delivery-doc/RN/html/${code}_RN_${version}.html?isNativeBrowsing=true`, '_blank');
    }

    function openJira(code) {
        const version = document.getElementById('sel-' + code).value;
        window.open(`https://cisas.eu.airbus.corp:8343/1V32-jira/issues/?jql=` + encodeURIComponent(`project = ${code} AND fixVersion = ${version}`), '_blank');
    }

    function generateDiffs(code) {
        const version = document.getElementById('sel-' + code).value;
        fetch(`/api/generate_diffs?comp=${code}&version=${version}`, { method: 'POST' })
            .then(res => res.json())
            .then(data => alert(data.message));
    }

    function generatePhases(code) {
        const version = document.getElementById('sel-' + code).value;
        fetch(`/api/generate_phases?comp=${code}&version=${version}`, { method: 'POST' })
            .then(res => res.json())
            .then(data => alert(data.message));
    }

    function clearCache() {
        if(confirm("This will erase all cached data and query the servers again. Proceed?")) {
            fetch('/api/clear_cache', { method: 'POST' })
                .then(() => location.reload());
        }
    }
</script>
</body>
</html>
        """
        self.wfile.write(html)

if __name__ == '__main__':
    try:
        server = BaseHTTPServer.HTTPServer(('', PORT_NUMBER), DashboardHandler)
        print "Started Dashboard Web Server on port", PORT_NUMBER
        print "Open http://localhost:8080 in your browser."
        server.serve_forever()
    except KeyboardInterrupt:
        print "\nShutting down server."
        server.socket.close()
