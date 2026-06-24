# -*- coding: utf-8 -*-
# fetch_files.py
from __future__ import print_function
import os
import sys
import codecs
import requests
import urllib3
import traceback
import re
import tarfile
import zipfile
import base64
from requests.auth import HTTPBasicAuth
import argparse

# Import our existing robust tools
import github
from tools import convert_xlsm_to_jsonl
from config import ARTIFACTORY_URL, ARTIFACTORY_USER, ARTIFACTORY_TOKEN, GITHUB_API_URL, GITHUB_TOKEN, GITHUB_ORG

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def extract_robot_log_strings(html_content):
    """Mines all text strings from all window.output assignments inside Robot Framework SPAs."""
    lines = []
    
    # Find all window.output[...] = ... blocks across the script layers
    assignments = re.findall(r'window\.output\["[^"]+"\]\s*=\s*.*?;', html_content, flags=re.DOTALL)
    
    all_strings = []
    for assign in assignments:
        # Mine all string literals safely handling basic escape tokens
        tokens = re.findall(r'"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\'', assign)
        for t in tokens:
            val = t[0] if t[0] else t[1]
            val_clean = val.strip()
            
            # Filter layout tags, metadata properties, short garbage, and JS execution operators
            if not val_clean or len(val_clean) <= 1: continue
            if val_clean in ['elapsed', 'fail', 'label', 'pass', 'id', 'name', 'status', 'baseMillis', 'generatedMillis', 'generatedTimestamp']: continue
            if val_clean.startswith(('.', '#', 'div', 'span', 'thead', 'tbody', 'font-', 'background', 'color:')): continue
            if any(x in val_clean for x in ['window.output', 'function()', 'var ', 'return ', 'jQuery', 'html=true']): continue
            
            # Normalize escape sequences
            val_clean = val_clean.replace('\\"', '"').replace("\\'", "'").replace('\\n', '\n').replace('\\t', '\t')
            all_strings.append(val_clean)
            
    if all_strings:
        lines.append(u"=== ROBOT FRAMEWORK EMBEDDED LOG DATA ===")
        last_added = None
        for s in all_strings:
            if s != last_added:
                lines.append(u"  " + s)
                last_added = s
                
    if lines: return u"\n".join(lines)
    return None

def convert_html_to_text(html_content):
    """Removes HTML tags and converts block elements to clean text for AI consumption."""
    if not html_content: return u""
    
    # Aggressively wipe out the browser warning div block at the absolute start
    html_content = re.sub(r'<div id="javascript-disabled">.*?</div>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    
    # DETECT AND RESCUE ROBOT FRAMEWORK DATA (SPA Escape Hatch)
    if "window.output" in html_content:
        print("    -> [ROBOT FRAMEWORK DETECTED] Processing deep internal text records...")
        robot_text = extract_robot_log_strings(html_content)
        if robot_text:
            return u"=== ROBOT FRAMEWORK LOG TEXT EXTRACT ===\n\n" + robot_text
            
    text = html_content
    # 1. Remove <head>, <style>, <script> entirely so we don't get standard CSS/JS code
    text = re.sub(r'<(head|style|script)[^>]*>.*?</\1>', '', text, flags=re.IGNORECASE | re.DOTALL)
    # 2. Replace block-level tags with newlines
    text = re.sub(r'<(br|p|div|li|tr|h[1-6]|table|/table)[^>]*>', '\n', text, flags=re.IGNORECASE)
    # 3. Replace table cells with tabs
    text = re.sub(r'<(td|th)[^>]*>', ' \t ', text, flags=re.IGNORECASE)
    # 4. Remove all remaining tags
    text = re.sub(r'<[^>]+>', '', text)
    # 5. Unescape basic HTML entities
    entities = {'&nbsp;': ' ', '&lt;': '<', '&gt;': '>', '&amp;': '&', '&quot;': '"', '&#8217;': "'", '&#8220;': '"', '&#8221;': '"', '&#8211;': '-', '&#8212;': '--', '&#39;': "'"}
    for k, v in entities.items(): text = text.replace(k, v)
    # 6. Collapse multiple blank lines
    text = re.sub(r'\n\s*\n', '\n\n', text)
    return text.strip()

def process_raw_bytes(raw_data, filename):
    """Converts raw binary payloads into clean text structures based on extensions."""
    if filename.lower().endswith('.xlsm') or filename.lower().endswith('.xlsx'):
        temp_excel = "temp_fetch_" + filename.split('/')[-1]
        with open(temp_excel, 'wb') as f: f.write(raw_data)
        try:
            text_data = convert_xlsm_to_jsonl(temp_excel)
        except Exception as e:
            text_data = "[!] Excel Conversion Failed: {}".format(str(e))
            
        if os.path.exists(temp_excel): os.remove(temp_excel)
        return u"=== EXCEL EXTRACT: {} ===\n{}\n".format(filename, text_data)
        
    elif filename.lower().endswith('.html') or filename.lower().endswith('.htm'):
        decoded = raw_data.decode('utf-8', errors='replace')
        return convert_html_to_text(decoded)
        
    else:
        return raw_data.decode('utf-8', errors='replace')

def get_github_file(component, target, mode="direct", branch="master"):
    """Searches GitHub for the file and pulls the pure binary data layer."""
    print("  [*] Searching GitHub in {} (Branch: {})...".format(component, branch))
    
    tree_data = github.get_file_tree(component, branch)
    if not tree_data or "tree" not in tree_data:
        print("    [!] Could not fetch GitHub tree.")
        return None, None

    exact_path = None
    sha = None
    
    if mode == "search":
        for item in tree_data["tree"]:
            if item.get("type") != "blob": continue
            if target.lower() in item.get("path", "").lower():
                exact_path = item.get("path", "")
                sha = item.get("sha")
                break
    else:
        norm_target = target.replace('\\', '/').lower()
        for item in tree_data["tree"]:
            if item.get("type") != "blob": continue
            if item.get("path", "").lower() == norm_target:
                exact_path = item.get("path", "")
                sha = item.get("sha")
                break
            
    if not exact_path or not sha:
        print("    [!] Not found in GitHub tree.")
        return None, None
        
    print("    -> Found in GitHub: {}".format(exact_path))
    
    blob_url = "{}/repos/{}/{}/git/blobs/{}".format(GITHUB_API_URL, GITHUB_ORG, component, sha)
    headers = {"Authorization": "Bearer " + GITHUB_TOKEN, "Accept": "application/vnd.github.v3+json"}
    
    try:
        resp = requests.get(blob_url, headers=headers, verify=False)
        if resp.status_code == 200:
            blob_data = resp.json()
            if blob_data and "content" in blob_data:
                raw_bytes = base64.b64decode(blob_data["content"])
                processed_text = process_raw_bytes(raw_bytes, exact_path)
                return processed_text, raw_bytes
    except Exception as e:
        print("    [!] GitHub blob extraction crash: {}".format(e))
        
    return None, None

def extract_from_local_archive(archive_url, auth, inner_path, is_zip=False):
    """Downloads archive to local disk and rips the file out using Python."""
    print("    -> API Extraction blocked. Downloading archive locally to force extraction...")
    tmp_path = "temp_arti_archive" + (".zip" if is_zip else ".tar.gz")
    
    try:
        r = requests.get(archive_url, auth=auth, verify=False, stream=True)
        r.raise_for_status()
        
        with open(tmp_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk: f.write(chunk)
        r.close()

        content = None
        if is_zip:
            with zipfile.ZipFile(tmp_path, 'r') as z:
                if inner_path in z.namelist(): content = z.read(inner_path)
        else:
            with tarfile.open(tmp_path, 'r:gz') as t:
                try:
                    member = t.getmember(inner_path)
                    extracted_f = t.extractfile(member)
                    if extracted_f: content = extracted_f.read()
                except KeyError: pass 
                    
        if os.path.exists(tmp_path): os.remove(tmp_path)
        return content
    except Exception as e:
        print("      [!] Error during local extraction: {}".format(e))
        if os.path.exists(tmp_path): os.remove(tmp_path)
        return None

def get_artifactory_file(component, filename, branch="master", rel_path=None, repo_name="avionics-software-release"):
    """Searches Artifactory repo variants, handles suffix-less tarballs, and extracts content."""
    print("  [*] Attempting Artifactory Extraction for '{}' in repository '{}'...".format(filename, repo_name))
    if not rel_path: rel_path = filename

    # Included '' to support un-partitioned clean release names
    suffixes = ['', 'other', 'doc', 'src', 'bin', 'test', 'verif']
    norm_path = rel_path.replace('\\', '/').lstrip('/')
    inner_paths = ["{}/{}".format(component, norm_path), norm_path]
    
    auth = HTTPBasicAuth(ARTIFACTORY_USER, ARTIFACTORY_TOKEN)
    
    for suffix in suffixes:
        if suffix:
            tar_name = "{}-{}-{}.tar.gz".format(component, branch, suffix)
            zip_name = "{}-{}-{}.zip".format(component, branch, suffix)
        else:
            tar_name = "{}-{}.tar.gz".format(component, branch)
            zip_name = "{}-{}.zip".format(component, branch)
        
        for archive_name in [tar_name, zip_name]:
            base_archive_url = "{}/{}/com/airbus/avsw/{}/{}/{}/{}".format(
                ARTIFACTORY_URL, repo_name, component, component, branch, archive_name
            )
            try:
                head_resp = requests.head(base_archive_url, auth=auth, verify=False)
                if head_resp.status_code != 200: continue
            except requests.exceptions.RequestException: continue
                
            print("    -> Found matching archive: {}".format(archive_name))
            
            for inner in inner_paths:
                target_uri = "{}!/{}".format(base_archive_url, inner)
                try:
                    resp = requests.get(target_uri, auth=auth, verify=False)
                    content_type = resp.headers.get('Content-Type', '').lower()
                    if resp.status_code == 200 and 'json' not in content_type and b'"errors"' not in resp.content[:50]:
                        print("    -> [SUCCESS] Extracted via API!")
                        processed_text = process_raw_bytes(resp.content, filename)
                        return processed_text, resp.content
                except requests.exceptions.RequestException: pass 

                raw_bytes = extract_from_local_archive(base_archive_url, auth, inner, is_zip=archive_name.endswith('.zip'))
                if raw_bytes:
                    print("    -> [SUCCESS] Extracted via Python fallback!")
                    processed_text = process_raw_bytes(raw_bytes, filename)
                    return processed_text, raw_bytes
                    
    print("    [!] Could not locate file directly in Artifactory archives.")
    return None, None

def process_input_file(input_file="input.txt", mode="direct"):
    """Reads input.txt, maps parameters (2, 3, or 4 args), and coordinates downloads."""
    if not os.path.exists(input_file):
        print("[!] {} not found.".format(input_file))
        sys.exit(1)
        
    output_dir = "output"
    raw_dir = "output_raw"
    
    if not os.path.exists(output_dir): os.makedirs(output_dir)
    if not os.path.exists(raw_dir): os.makedirs(raw_dir)

    print("[*] Reading {} (Mode: {})".format(input_file, mode.upper()))
    with codecs.open(input_file, 'r', 'utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]

    for line in lines:
        print("\n" + "="*70)
        parts = line.split()
        repo_override = "avionics-software-release"
        
        # Flex-Parser mapping inputs with optional 4th parameter overrides
        if len(parts) >= 4:
            # Format: COMPONENT BRANCH REPO_NAME PATH
            component = parts[0].upper()
            branch = parts[1]
            repo_override = parts[2]
            target = " ".join(parts[3:])
        elif len(parts) == 3:
            # Format: COMPONENT BRANCH PATH
            component = parts[0].upper()
            branch = parts[1]
            target = parts[2]
        elif len(parts) == 2:
            # Format: COMPONENT PATH
            component = parts[0].upper()
            branch = "master"
            target = parts[1]
        else: continue
            
        if mode == "direct":
            target_github = target.replace('\\', '/')
            filename = target_github.split('/')[-1]
            rel_path = target_github
            print("Target: {} | Branch: {} | Repo: {} | Path: {}".format(component, branch, repo_override, rel_path))
        else:
            target_github = target
            filename = target
            rel_path = None
            print("Target: {} | Branch: {} | Repo: {} | Search: {}".format(component, branch, repo_override, target))
        
        # Pipeline execution passes the custom repo down to Artifactory
        content, raw_bytes = get_github_file(component, target_github, mode=mode, branch=branch)
        if not content:
            content, raw_bytes = get_artifactory_file(component, filename, branch=branch, rel_path=rel_path, repo_name=repo_override)
            
        if content and raw_bytes:
            # Save Formatted Converted Text Summary Segment
            safe_filename = filename.replace('.html', '').replace('.xlsm', '').replace('.xlsx', '')
            out_path = os.path.join(output_dir, "{}_{}_{}.txt".format(component, branch.replace('/', '_'), safe_filename))
            with codecs.open(out_path, 'w', 'utf-8') as out_f:
                out_f.write(content)
            print("[+] Saved clean text summary to: {}".format(out_path))
            
            # Save Original Untouched Source Asset File
            raw_path = os.path.join(raw_dir, "{}_{}_{}".format(component, branch.replace('/', '_'), filename))
            with open(raw_path, 'wb') as raw_f:
                raw_f.write(raw_bytes)
            print("[+] Saved untouched source file to: {}".format(raw_path))
        else:
            print("[-] FAILED to retrieve {} from any source.".format(filename))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Airbus Multi-Source File Fetcher")
    parser.add_argument("-i", "--input", default="input.txt")
    parser.add_argument("--mode", choices=["direct", "search"], default="direct")
    args = parser.parse_args()
    process_input_file(args.input, args.mode)
