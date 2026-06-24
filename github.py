# github_client.py
from __future__ import print_function
import os
import json
import argparse
import codecs
import time
import ssl
import re
import sys
import base64
from config import GITHUB_API_URL, GITHUB_TOKEN, GITHUB_ORG, REQUEST_DELAY
from tools import convert_xlsm_to_jsonl  # <-- IMPORT YOUR NEW TOOL
import sys

# --- THE PYTHON 2 NUCLEAR OPTION ---
if sys.version_info[0] < 3:
    reload(sys)
    sys.setdefaultencoding('utf-8')

# --- PYTHON 2 / 3 COMPATIBILITY LAYER ---
try:
    import urllib.request as urllib_request
    import urllib.error as urllib_error
    from urllib.parse import urlencode, quote as urlquote
except ImportError:
    import urllib2 as urllib_request
    import urllib2 as urllib_error
    from urllib import urlencode, quote as urlquote

try:
    CTX = ssl._create_unverified_context()
except AttributeError:
    CTX = None

# --- CONFIGURATION ---
HARD_EXCLUDED_EXTS = (
    '.xlsx', '.xlsm', '.jar', '.pdf', '.rqtfimage', 
    '.png', '.jpg', '.jpeg', '.bin', '.lup', '.luh', '.pptx', '.svg', '.csv', 
    #'.i', '.pre.c', '.genload_log', '.log',
    '.o', '.a', '.html', '.result', 
    '.ram', '.rom', '.lvbitx', '.tmp', '.pdb', '.ilk', '.obj',
    '.tar', '.tar.gz', '.tgz', '.tar.xz', '.tar.bz2', '.zip', '.pack', '.idx',
    '.bmp', '.mkv', '.wav', '.mp3', '.pcap', '.pcapng', '.exe', '.elf', '.so', '.dbg',
    '.doc', '.docx', '.docm', '.xls', '.vsd', '.vsdx',
    '.ttl', '.lst', '.luao', '.css', '.map', '.min.js',
    '.saofd', '.mi', '.cmm', '.kal', '.mdf', '.mdv', '.s3', '.ldz', '.sql', '.out',
    '.drawio', '.drawio.xml', '.matrix.json', '.cpntdata.json', '.userdata.json', 
    '.cache', '.t32', '.ann', '.bib', 
    # NEW: Bytecode, temp files, and icons
    '.pyc', '.pyo', '.bak', '.swp', '.swn', '.ico'
)

HARD_EXCLUDED_DIRS = [
    'tmp', 'build', 'external', 'sqar', 
    'asic_reg', 'gac', 'gac_2', 'gac_splitcheckc', 
    'testapp', 'genaudiodb', 'audiodb',
    'testappli', 'results', 'result', 'inputs', 
    'simugene_snapshots', 'linux_rmax', 'opera_scenario', 
    'yellow_pages', 'server_stub', 'network_tools',
    'testappliconf', 'libbenchicd', 'benchconfig', 'rte', 
    't32_plugin_main', 'dev-tools', 'acg_output', 
    'ims_cioc_test_package', 'database', 'romgen', 
    'sib_sdac1_conf', 'flics', 'cots', 'git2', 
    'unit-proof', 'rsrc', 'java', 'toolchain-titv', 'lct',
    'doxygen' # We keep gradle and build-conf, but Doxygen is safe to drop
]
# --- HELPER FUNCTIONS ---
def safe_decode(content):
    if content is None:
        return u""
    try:
        return content.decode('utf-8', errors='replace')
    except AttributeError:
        return content

def make_gh_request(url, params=None, is_diff=False, is_raw=False):
    if params:
        url = url + "?" + urlencode(params)
        
    req = urllib_request.Request(url)
    req.add_header("Authorization", "Bearer " + GITHUB_TOKEN)
    
    if is_diff:
        req.add_header("Accept", "application/vnd.github.v3.diff")
    elif is_raw:
        req.add_header("Accept", "application/vnd.github.v3.raw")
    else:
        req.add_header("Accept", "application/vnd.github.v3+json")

    time.sleep(REQUEST_DELAY)
    
    for attempt in range(3):
        try:
            response = urllib_request.urlopen(req, context=CTX) if CTX else urllib_request.urlopen(req)
            raw_data = response.read()
            
            if is_diff or is_raw:
                return raw_data
            else:
                decoded_str = raw_data if isinstance(raw_data, str) else raw_data.decode('utf-8', errors='replace')
                return json.loads(decoded_str)
                
        except urllib_error.HTTPError as e:
            if e.code in (422, 404): return None
            elif e.code in (403, 429):
                retry_after = e.headers.get('Retry-After')
                time.sleep((int(retry_after) + 1) if retry_after else 5 * (attempt + 1))
                continue
            else: return None
        except Exception: return None
    return None

def get_all_components():
    """Queries the GitHub API to find all repositories matching CXXXXX."""
    components = []
    page = 1
    while True:
        url = "{}/orgs/{}/repos?per_page=100&page={}".format(GITHUB_API_URL, GITHUB_ORG, page)
        repos = make_gh_request(url)
        
        if not repos or not isinstance(repos, list): 
            break
            
        for repo in repos:
            name = repo.get("name", "")
            # Matches C followed by exactly 5 digits
            if re.match(r"^C\d{5}$", name, re.IGNORECASE):
                components.append(name.upper())
                
        if len(repos) < 100:
            break # Reached the last page
        page += 1
        
    return sorted(list(set(components)))

def get_file_tree(component, ref="master"):
    url = "{}/repos/{}/{}/git/trees/{}?recursive=1".format(GITHUB_API_URL, GITHUB_ORG, component, urlquote(ref))
    return make_gh_request(url)

def categorize_file(rel_path):
    n = rel_path.replace('\\', '/').lower()
    base = n.split('/')[-1]
    
    if n.endswith(('.adoc', '.xlsm', '.xlsx')): return None
    if n.startswith('src/plan/'): return '0_PLAN'
    if n.startswith('src/spec/'): return '1_SPEC_ARCHI'
    if n.startswith('src/design/') or base in ('.dcsl_derog', '.codda_derog'): return '2_DESIGN'
    if n.startswith('src/main/c/') or n.startswith('src/main/header/') or n.startswith('src/main/asm/') or base in ('.checkc_derog', '.fanc_derog'): return '3_CODE'
    if n.startswith('src/verif/unit-test/'): return '4_UNIT_VERIF'
    if n.startswith('src/verif/integration/tests/environment/'): return '5_INTEG_VERIF_TEST_ENV'
    if n.startswith('src/verif/integration/') or n.startswith('src/toolchain/toolchain-titv/') or n.startswith('src/toolchain/toolchain-tienvbuild/'): return '5_INTEG_VERIF'
    if n.startswith('src/delivery-doc/'): return '7_USER_GUIDE'
    if base in ('data.gradle', 'jenkinsfile'): return '6_ENVIRONMENT'
    return None

        
def map_all_components():
    """Iterates through all components to build a global size ranking and detailed file map."""
    components = get_all_components()
    if not components: 
        print("[!] No components found in the organization.")
        return
    
    print("\n[*] Found {} components. Globally mapping...".format(len(components)))
    all_stats = []
    
    for comp in components:
        print("  -> Scanning {}".format(comp))
        tree = get_filtered_tree_map(comp, "master")
        if not tree: continue
        
        total_size = sum(item.get("size", 0) for item in tree)
        cat_sizes = {}
        files_list = []
        
        for item in tree:
            path = item.get("path", "")
            cat = categorize_file(path)
            if not cat: cat = "SPECIFIC_DOCS" if path.endswith(('.adoc', '.xlsm', '.xlsx')) else "UNCATEGORIZED"
            
            size = item.get("size", 0)
            cat_sizes[cat] = cat_sizes.get(cat, 0) + size
            files_list.append({"path": path, "size": size, "cat": cat})
            
        all_stats.append({
            "component": comp,
            "total_size": total_size,
            "cat_sizes": cat_sizes,
            "files": sorted(files_list, key=lambda x: x['size'], reverse=True)
        })
        
    # Sort components from heaviest to lightest
    all_stats.sort(key=lambda x: x["total_size"], reverse=True)
    
    out_path = "Global_Components_Stats.txt"
    with codecs.open(out_path, "w", "utf-8") as f:
        f.write(u"=== GLOBAL COMPONENT SIZE RANKINGS & HEAVY FILES ===\n\n")
        
        for stat in all_stats:
            f.write(u"[{}] Total Weight: {:.2f} MB\n".format(stat["component"], stat["total_size"] / (1024.0 * 1024.0)))
            
            f.write(u"  --- Category Breakdown ---\n")
            for cat, size in sorted(stat["cat_sizes"].items(), key=lambda x: x[1], reverse=True):
                f.write(u"    {}: {:.2f} KB\n".format(cat, size / 1024.0))
                
            f.write(u"\n  --- Top 50 Largest Files in Repo ---\n")
            for f_info in stat["files"][:20]:
                f.write(u"    [{}] {} ({:.2f} KB)\n".format(f_info['cat'], f_info['path'], f_info['size'] / 1024.0))
                
            f.write(u"\n" + u"="*80 + u"\n\n")
            
    print("\n[+] Global map completed and saved to {}".format(out_path))

# --- CORE TRIAGE & DOWNLOAD LOGIC ---

def get_filtered_tree_map(component, ref="master", target_dirs=None, include_overrides=None):
    """Maps the GitHub tree and carefully tags files or folders for isolated extraction."""
    if target_dirs is None: target_dirs = []
    if include_overrides is None: include_overrides = []
    
    include_overrides = [x.strip().lower() for x in include_overrides]
    
    tree_data = get_file_tree(component, ref)
    if not tree_data or "tree" not in tree_data: return None

    filtered_tree = []
    up_code = component.upper()
    matched_path_count = 0

    for item in tree_data["tree"]:
        if item.get("type") != "blob": continue
        path = item.get("path", "")
        lp = path.lower()
        up_base = path.split("/")[-1].upper()

        # 1. VIP PASS: Does it match a --dir target (Folder or Specific File)?
        dir_matches = []
        is_xlsm_tool_match = False
        
        for t_dir in target_dirs:
            norm_path = t_dir.strip().lower().replace('\\', '/').rstrip('/')
            # Check if it's a file inside a targeted folder OR the exact specific file targeted
            if lp.startswith(norm_path + '/') or lp == norm_path:
                # If the targeted path is exactly this file AND it's an XLSM, use the tool
                if lp == norm_path and lp.endswith(('.xlsm', '.xlsx')):
                    is_xlsm_tool_match = True
                
                # Naming: Use the last part of the target path for the bucket name
                bucket_label = norm_path.split('/')[-1].replace('.', '_').upper()
                dir_matches.append(bucket_label)
                matched_path_count += 1

        # 2. Check Directory Bans
        is_dir_banned = False
        for ex in HARD_EXCLUDED_DIRS:
            if ex in lp.split('/'):
                if ex.lower() not in include_overrides:
                    is_dir_banned = True
                    break

        if is_dir_banned and not dir_matches:
            continue

        # 3. Check Specific Document matches (Immunity Shield for XLSM/ADOC)
        is_specific_doc = False
        if up_code in up_base:
            if lp.endswith(".adoc") and any(t in up_base for t in ["AD", "SD", "SID", "UG"]):
                is_specific_doc = True
            elif lp.endswith((".xlsm", ".xlsx")) and ("CRAM_UG" in up_base or "RAM-HLR" in up_base):
                is_specific_doc = True
        
        if is_xlsm_tool_match:
            is_specific_doc = True

        # 4. Check Extension Bans (Bypassed by specific docs/xlsms)
        is_ext_banned = False
        for ext in HARD_EXCLUDED_EXTS:
            if lp.endswith(ext):
                if ext.lower() not in include_overrides:
                    is_ext_banned = True
                    break

        if is_ext_banned and not is_specific_doc:
            continue

        # 5. Specific File Bans
        if not is_specific_doc:
            banned_bases = ['OUTPUT.XML', 'JQUERY.JS', 'POETRY.LOCK', 'MKKFS_REDHAT', 'ELF2R5APP', 'FSWATCH', 'IP', 'DOXYFILE.TEMPLATE', 'THUMBS.DB']
            if up_base in banned_bases and up_base.lower() not in include_overrides: continue
            if up_base == 'RQTFIMAGE' and 'rqtfimage' not in include_overrides: continue
            if up_base.startswith('REPORT') and up_base.endswith('.XML') and '.xml' not in include_overrides: continue
            if (up_base.startswith('DUMPWIRESHARK') or up_base.startswith('BUFFER_REF_') or up_base.startswith('ADC_')) and up_base.lower() not in include_overrides: continue
            if (up_base.endswith('RAM-HLR.JSON') or up_base.endswith('CRAM_UG.JSON')) and 'SRC/SPEC/' in lp.upper(): continue
            if '.ZIP.' in up_base and '.zip' not in include_overrides: continue

        item['dir_matches'] = dir_matches
        item['is_xlsm_tool_match'] = is_xlsm_tool_match
        filtered_tree.append(item)
        
    if target_dirs:
        print("  -> [DEBUG] Found {} files matching targeted paths.".format(matched_path_count))
        
    return filtered_tree

def generate_file_statistics_text(filtered_tree):
    files = []
    dir_sizes = {}
    
    for item in filtered_tree:
        path = item.get("path", "")
        size = item.get("size", 0)
        cat = categorize_file(path)
        if not cat: cat = "SPECIFIC_DOCS" if path.endswith(('.adoc', '.xlsm')) else "UNCATEGORIZED"
        files.append({"path": path, "size": size, "cat": cat})
        
        # Directory Aggregation
        dirname = "/".join(path.split('/')[:-1]) if "/" in path else "[Root]"
        dir_sizes[dirname] = dir_sizes.get(dirname, 0) + size

    files_sorted = sorted(files, key=lambda x: x['size'], reverse=True)
    dirs_sorted = sorted(dir_sizes.items(), key=lambda x: x[1], reverse=True)
    
    lines = [u"=== AI CONTEXT TRIAGE MAP ===", u""]
    lines.append(u"[SYSTEM-LEVEL HARD EXCLUSIONS APPLIED]")
    lines.append(u"Excluded Extensions: " + u", ".join(HARD_EXCLUDED_EXTS))
    lines.append(u"Excluded Directories: " + u", ".join(HARD_EXCLUDED_DIRS))
    
    lines.append(u"\n--- TOP 20 HEAVIEST DIRECTORIES ---")
    for d, s in dirs_sorted[:20]:
        lines.append(u"  {} ({:.2f} KB)".format(d, s / 1024.0))
        
    lines.append(u"\n--- TOP 20 LARGEST FILES ---")
    for f in files_sorted[:20]:
        lines.append(u"[{}] {} ({:.2f} KB)".format(f['cat'], f['path'], f['size'] / 1024.0))

    lines.append(u"\n--- ALL FILES BY CATEGORY ---")
    grouped = {}
    for f in files_sorted: grouped.setdefault(f['cat'], []).append(f)
    for cat in sorted(grouped.keys()):
        lines.append(u"\n[{}]".format(cat))
        for f in grouped[cat]: lines.append(u"  {} ({:.2f} KB)".format(f['path'], f['size'] / 1024.0))
    
    return u"\n".join(lines)

def download_repository_content(component, ref, filtered_tree, dynamic_exclusions=None, triage_docs_only=False, target_dirs=None):
    if dynamic_exclusions is None: dynamic_exclusions = []
    if target_dirs is None: target_dirs = []
        
    phases_lists = {
        '0_PLAN': [], '1_SPEC_ARCHI': [], '2_DESIGN': [], '3_CODE': [],
        '4_UNIT_VERIF': [], '5_INTEG_VERIF': [], '5_INTEG_VERIF_TEST_ENV': [], 
        '6_ENVIRONMENT': [], '7_USER_GUIDE': [],
        'TRIAGE_DOCS': []
    }

    docs = {"AD": [], "SD": [], "SID": [], "UG": []}
    cram_files = []
    standard_files = {k: [] for k in phases_lists.keys() if k != 'TRIAGE_DOCS'}
    
    up_code = component.upper()

    for item in filtered_tree:
        path = item.get("path", "")
        lp = path.lower()
        up_base = path.split("/")[-1].upper()

        if any(dyn_ex.lower() in lp for dyn_ex in dynamic_exclusions): continue
        
        dir_matches = item.get('dir_matches', [])
        is_xlsm_tool = item.get('is_xlsm_tool_match', False)

        # 1. Route Targeted Paths (Isolated Buckets)
        if dir_matches and not triage_docs_only:
            # If it's a specific XLSM file targeted, send to XLSM pipeline
            if is_xlsm_tool:
                for label in dir_matches:
                    cram_files.append({"path": path, "label": "XLSM_" + label, "sha": item.get("sha", "")})
            else:
                # Standard file or folder contents go to standard text buckets
                for bucket_label in dir_matches:
                    bucket = "DIR_" + bucket_label
                    if bucket not in phases_lists: phases_lists[bucket] = []
                    if bucket not in standard_files: standard_files[bucket] = []
                    standard_files[bucket].append({"path": path, "sha": item.get("sha", "")})
            continue # Skip standard phases

        # 2. STRICT MODE: If targets provided, ignore everything else
        if target_dirs:
            continue

        # 3. Standard Processing...
        if lp.endswith(".adoc"):
            if "src/spec/ad" in lp: docs["AD"].append(path)
            elif "src/spec/sd" in lp: docs["SD"].append(path)
            elif "src/spec/sid" in lp: docs["SID"].append(path)
            elif "src/delivery-doc" in lp: docs["UG"].append(path)
            elif up_code in up_base:
                for t in ["AD", "SD", "SID", "UG"]:
                    if t in up_base: docs[t].append(path)
            continue

        if up_code in up_base and lp.endswith((".xlsm", ".xlsx")) and not triage_docs_only:
            if "CRAM_UG" in up_base: cram_files.append({"path": path, "label": "CRAM_UG", "sha": item.get("sha", "")})
            elif "RAM-HLR" in up_base: cram_files.append({"path": path, "label": "RAM-HLR", "sha": item.get("sha", "")})
            continue
        
        if not triage_docs_only:
            cat = categorize_file(path)
            if cat: standard_files[cat].append({"path": path, "sha": item.get("sha", "")})

    # --- FETCH DOCS ---
    for doc_type, paths in docs.items():
        for path in paths:
            url = "{}/repos/{}/{}/contents/{}?ref={}".format(GITHUB_API_URL, GITHUB_ORG, component, urlquote(path), urlquote(ref))
            content = make_gh_request(url, is_raw=True)
            if content:
                if triage_docs_only:
                    phases_lists['TRIAGE_DOCS'].append(u"=== SPECIFIC DOC: {} ===\n{}\n\n".format(path, safe_decode(content)))
                else:
                    phase_key = '7_USER_GUIDE' if doc_type == "UG" else '1_SPEC_ARCHI'
                    phases_lists[phase_key].append(u"=== SPECIFIC DOC: {} ===\n{}\n\n".format(path, safe_decode(content)))

    if triage_docs_only:
        return {k: u"".join(v) for k, v in phases_lists.items() if k == 'TRIAGE_DOCS'}

    # --- FETCH XLSMS ---
    for cram in cram_files:
        if not cram.get('sha'): continue
            
        print("\n[DEBUG XLSM] Fetching blob for {}...".format(cram['label']))
        blob_url = "{}/repos/{}/{}/git/blobs/{}".format(GITHUB_API_URL, GITHUB_ORG, component, cram['sha'])
        blob_data = make_gh_request(blob_url)
        
        # Use label directly for custom targets, otherwise standard Spec Archi
        if cram['label'].startswith('XLSM_'):
            unique_phase_key = cram['label']
        else:
            unique_phase_key = '1_SPEC_ARCHI_' + cram['label']
        
        if blob_data and "content" in blob_data:
            try:
                raw_bytes = base64.b64decode(blob_data["content"])
                temp_xlsm = os.path.abspath(cram['path'].split("/")[-1])
                temp_xlsm = str(temp_xlsm) if sys.version_info[0] < 3 else temp_xlsm
                with open(temp_xlsm, 'wb') as f: f.write(raw_bytes)
                
                if os.path.getsize(temp_xlsm) < 1000 and b"message" in raw_bytes[:100]:
                    phases_lists[unique_phase_key] = [u"[!] Download failed. API Returned: {}\n\n".format(safe_decode(raw_bytes))]
                else:
                    jsonl_text = convert_xlsm_to_jsonl(temp_xlsm)
                    phases_lists[unique_phase_key] = [jsonl_text] 
                
                #if os.path.exists(temp_xlsm): os.remove(temp_xlsm)
            except Exception as e:
                phases_lists[unique_phase_key] = [u"[!] Error: {}\n\n".format(str(e))]
        else:
            phases_lists[unique_phase_key] = [u"[!] Failed to fetch blob.\n\n"]

    # --- FETCH EVERYTHING ELSE ---
    for cat, file_items in standard_files.items():
        for f_item in file_items:
            path, sha = f_item["path"], f_item["sha"]
            print("    -> Downloading: {}".format(path))
            blob_url = "{}/repos/{}/{}/git/blobs/{}".format(GITHUB_API_URL, GITHUB_ORG, component, sha)
            blob_data = make_gh_request(blob_url)
            if blob_data and "content" in blob_data:
                try:
                    raw_bytes = base64.b64decode(blob_data["content"])
                    phases_lists[cat].append(u"--- FILE: {} ---\n{}\n\n".format(path, safe_decode(raw_bytes)))
                except: pass

    return {k: u"".join(v) for k, v in phases_lists.items()}

def save_phases_to_disk(component, branch, phases_content, is_triage=False):
    if not phases_content: return None
    
    # Use Component_Branch format
    safe_branch = branch.replace('/', '_')
    output_dir = "{}_{}".format(component, safe_branch)
    
    if not os.path.exists(output_dir): 
        os.makedirs(output_dir)
        
    if is_triage:
        out_path = os.path.join(output_dir, "{}_Triage.txt".format(component))
        with codecs.open(out_path, 'w', encoding='utf-8') as f:
            f.write(phases_content['TRIAGE_PAYLOAD'])
        print("[+] Triage mode complete. Map and Docs saved to {}/".format(output_dir))
    else:
        for phase_name, content in phases_content.items():
            # Support both lists (from standard processing) and direct strings
            text_content = content if isinstance(content, str) or isinstance(content, unicode) else u"".join(content)
            
            if text_content.strip(): 
                # Give stats a clean name, otherwise append phase number
                if phase_name == '8_FILE_STATS':
                    filename = "{}_Stats.txt".format(component)
                else:
                    filename = "{}_{}.txt".format(component, phase_name)
                    
                out_path = os.path.join(output_dir, filename)
                with codecs.open(out_path, 'w', encoding='utf-8') as f:
                    f.write(text_content)
                    
        print("[+] Successfully saved extracted phases to {}/".format(output_dir))
        
    return output_dir


def get_github_diffs_for_ticket(ticket_key, component):
    """Searches GitHub for commits mentioning the ticket, and fetches their diffs."""
    search_query = "{0} repo:{1}/{2}".format(ticket_key, GITHUB_ORG, component)
    
    search_params = {
        'q': search_query,
        'sort': 'author-date',
        'order': 'asc' 
    }
    search_url = GITHUB_API_URL + "/search/commits?" + urlencode(search_params)
    
    search_results = make_gh_request(search_url)
    if not search_results or 'items' not in search_results:
        return []
        
    commits = search_results.get('items', [])
    diffs = []
    
    for commit in commits:
        sha = commit.get('sha')
        message = commit.get('commit', {}).get('message', '').split('\n')[0] 
        print("    -> Found commit {} for {}".format(sha[:7], ticket_key))
        
        diff_url = "{}/repos/{}/{}/commits/{}".format(GITHUB_API_URL, GITHUB_ORG, component, sha)
        raw_diff = make_gh_request(diff_url, is_raw=True, is_diff=True) 
        
        if raw_diff:
            diffs.append({
                'sha': sha,
                'message': message,
                'diff': safe_decode(raw_diff)
            })
            
    return diffs

def get_all_branches(component):
    """Fetches all branches for a component to find the ticket's feature branch."""
    branches = []
    page = 1
    while True:
        url = "{}/repos/{}/{}/branches?per_page=100&page={}".format(GITHUB_API_URL, GITHUB_ORG, component, page)
        resp = make_gh_request(url)
        if not resp or not isinstance(resp, list): break
        for b in resp:
            branches.append(b.get('name'))
        if len(resp) < 100: break
        page += 1
    return branches

def write_github_diffs(tickets, component, current_branch):
    """Fetches all diffs for provided tickets via Branch Compare and saves a single .diff file."""
    safe_branch = current_branch.replace('/', '_')
    output_dir = "{}_{}".format(component, safe_branch)
    
    if not os.path.exists(output_dir): 
        os.makedirs(output_dir)
        
    print("[*] Fetching branch list for {}...".format(component))
    branches = get_all_branches(component)
    base_branch = 'develop' if 'develop' in branches else 'master'
    
    for ticket in tickets:
        print("\n[*] Fetching diffs for ticket: {}".format(ticket))
        
        # 1. Look for a branch containing the ticket name
        target_branch = None
        for b in branches:
            if ticket.upper() in b.upper():
                target_branch = b
                break
                
        combined_diff_text = u""
        
        # 2. If a branch is found, use the GitHub Compare API to get the pure .diff
        if target_branch:
            print("    -> Found matching branch: {}".format(target_branch))
            print("    -> Comparing {}...{}".format(base_branch, target_branch))
            
            diff_url = "{}/repos/{}/{}/compare/{}...{}".format(GITHUB_API_URL, GITHUB_ORG, component, base_branch, urlquote(target_branch))
            # The 'is_diff=True' flag sets the Accept header to 'application/vnd.github.v3.diff'
            raw_diff = make_gh_request(diff_url, is_raw=True, is_diff=True) 
            
            if raw_diff:
                combined_diff_text = safe_decode(raw_diff)
                
        # 3. Fallback: If no branch exists (e.g. it was deleted), fall back to the Search API
        if not combined_diff_text:
            print("    -> No active branch found. Falling back to Commit Search API...")
            diffs = get_github_diffs_for_ticket(ticket, component)
            if not diffs:
                print("  [!] No commits found for {}. Skipping.".format(ticket))
                continue
            # Join the raw diffs together
            combined_diff_text = u"\n".join([d['diff'] for d in diffs])
            
        # Save as a pure .diff file for git apply compatibility
        out_path = os.path.join(output_dir, "{}_Combined.diff".format(ticket))
        with codecs.open(out_path, 'w', 'utf-8') as f:
            f.write(combined_diff_text)
                
        print("[+] Saved pure combined diff to {}".format(out_path))
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Airbus GitHub AI Context Extractor\n\nDownloads repository content, applies aggressive AI context exclusions, and converts data into optimized text phases.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("component", nargs="?", help="The component code (e.g., C00216)")
    parser.add_argument("branch", nargs="?", default="master", help="GitHub branch or tag (Defaults to 'master')")
    parser.add_argument("--map-all", action="store_true", help="MAP-ALL MODE: Map all components in GitHub to analyze sizes")
    parser.add_argument("--triage", action="store_true", help="TRIAGE MODE: Only maps the repository tree and fetches High-Level Docs. Use this to ask the AI what files to exclude before downloading.")
    parser.add_argument("--dir", nargs="*", default=[], help="TARGET MODE: Extract specific folders OR files into isolated text files (e.g., --dir src/code/main.c src/spec/data.xlsm)")    
    parser.add_argument("--include", nargs="*", default=[], help="INCLUDE OVERRIDE: Override hard exclusions for specific extensions or directories to process them normally (e.g., --include .bin testappli)")    
    parser.add_argument("--exclude", nargs="*", default=[], help="DYNAMIC EXCLUSIONS: A space-separated list of directories/files to ignore (e.g., --exclude ptfmngrsrc mybswtool)")
    parser.add_argument("--stats", action="store_true", help="STATS: Include the 8_FILE_STATS.txt output")
    parser.add_argument("--diff", nargs="+", help="DIFF MODE: Fetch combined diffs for one or more Jira tickets (e.g., --diff PROJ-1234 PROJ-5678)")

    # Spawn help menu if no arguments are passed
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    # Diff Mode: Run standalone and exit
    if args.diff:
        if not args.component:
            print("[!] Component code is required for --diff mode.")
            sys.exit(1)
        write_github_diffs(args.diff, args.component, args.branch)
        sys.exit(0)

    if args.map_all:
        map_all_components()
        sys.exit(0)
        
    if not args.component:
        print("[!] Component code is required unless using --map-all or --diff")
        sys.exit(1)
    
    print("\n[*] Mapping repository tree for {}...".format(args.component))
    # ---> FIX: Pass target_dirs and include_overrides down to the mapper! <---
    filtered_tree = get_filtered_tree_map(args.component, args.branch, target_dirs=args.dir, include_overrides=args.include)
    
    if not filtered_tree:
        print("[!] Failed to map repository.")
        sys.exit(1)

    if args.triage:
        triage_payload = u"=== TRIAGE MODE ===\n"
        
        # Always generate the map for triage, no --stats flag required
        stats_text = generate_file_statistics_text(filtered_tree)
        triage_payload += stats_text + u"\n\n"
            
        print("[*] Fetching High-Level Documentation for Triage context...")
        # ---> FIX: Pass target_dirs to the downloader in triage mode too <---
        triage_docs = download_repository_content(args.component, args.branch, filtered_tree, triage_docs_only=True, target_dirs=args.dir)
        
        if 'TRIAGE_DOCS' in triage_docs:
            triage_payload += triage_docs['TRIAGE_DOCS']
            
        save_phases_to_disk(args.component, args.branch, {'TRIAGE_PAYLOAD': triage_payload}, is_triage=True)
        
    else:
        print("[*] Downloading content...")
        if args.exclude: print("  -> Dynamic Exclusions: {}".format(args.exclude))
        if args.dir: print("  -> Directory Extraction: {}".format(args.dir))
        if args.include: print("  -> Included Overrides: {}".format(args.include))
        
        phases_data = download_repository_content(args.component, args.branch, filtered_tree, dynamic_exclusions=args.exclude, target_dirs=args.dir)
        
        # Don't generate stats if we are just extracting isolated folders
        if args.stats and not args.dir:
            phases_data['8_FILE_STATS'] = generate_file_statistics_text(filtered_tree)
            
        if phases_data:
            save_phases_to_disk(args.component, args.branch, phases_data)
