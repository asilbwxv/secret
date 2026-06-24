#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
import os
import re
import subprocess
import sys
import argparse
import shutil
import glob

JENKINSFILE_PATHS = ["src/toolchain/jenkins/Jenkinsfile", "Jenkinsfile"]

# --- GLOBAL AVIONICS COMMANDS (From Confluence) ---
GLOBAL_COMMANDS = [
    ("Retrieve Dependencies", "./gradlew fwk_retrieve_dependencies --refresh-dependencies"),
    ("Initialize Toolchains (FOI)", "./gradlew fwk_optimases_initialize -x fwk_retrieve_dependencies"),
    ("Generate HTML Docs (ALL)", "./gradlew fwk_docops_GEN_HTML_ALL"),
    ("Check Codda Design (TC0018)", "./gradlew f_o_g --action codda_run_check --opt=\"-j 8\""),
    ("Codda Merge Code (TC0018)", "./gradlew f_o_g --action codda_merge_code"),
    ("Codda Import Code (TC0018)", "./gradlew f_o_g --action codda_import_code"),
    ("Check All Code (TC0013)", "./gradlew f_o_g --action all_check_code --opt=\"-j 8\""),
    ("Check All Flow (TC0021)", "./gradlew f_o_g --action all_check_flow --opt=\"-j 8\""),
    ("All Check Build (TC0020)", "./gradlew f_o_g --action all_check_build --opt=\"-j 8\""),
    ("Generate Traceability (CRAM NORM)", "./gradlew fwk_GEN_DATA_CRAM_NORM"),
    ("Generate Traceability (CRAM UG)", "./gradlew fwk_GEN_DATA_CRAM_UG"),
    ("Generate Traceability (RAM-HLR)", "./gradlew fwk_GEN_DATA_RAM-HLR")
]

def find_jenkinsfile():
    for path in JENKINSFILE_PATHS:
        if os.path.exists(path):
            return path
    return None

def extract_commands(filepath):
    commands = []
    # FIX: Matches the opening quote, captures everything until that SAME quote appears again
    pattern = re.compile(r"task\s*=\s*(['\"])(.*?)\1")
    with open(filepath, 'r') as f:
        for line in f:
            match = pattern.search(line)
            if match:
                cmd = match.group(2).strip() # group(2) is the actual command now
                if cmd not in commands:
                    commands.append(cmd)
    return commands

def parse_selection(selection_str, max_val):
    indices = set()
    parts = selection_str.split(',')
    for part in parts:
        part = part.strip()
        if '-' in part:
            try:
                start, end = map(int, part.split('-'))
                start = max(0, min(start, max_val)) # Allow 0
                end = max(0, min(end, max_val))     # Allow 0
                if start <= end:
                    indices.update(range(start, end + 1))
            except ValueError:
                pass
        else:
            try:
                val = int(part)
                if 0 <= val <= max_val: # Allow 0
                    indices.add(val)
            except ValueError:
                pass
    return sorted(list(indices))

def generate_filename(cmd, index):
    action_match = re.search(r'(?:ACTION=|action\s+)([A-Za-z0-9_-]+)', cmd)
    if action_match:
        base = action_match.group(1)
    else:
        # Otherwise, just sanitize the first 40 chars of the command
        base = re.sub(r'[^a-zA-Z0-9]+', '_', cmd)[:40].strip('_')
    
    # Prefix with a 2-digit zero-padded index (e.g., 01_..., 02_...)
    return "%02d_%s_output.txt" % (index, base)

def auto_copy_artifacts(cmd):
    """Automatically copies generated docs and traceability matrices as per your old aliases."""
    if "fwk_docops_GEN_HTML" in cmd:
        print "\n[System] Doc generation detected. Searching for HTML artifacts to copy to src/spec..."
        # Add your \cp logic here, using shutil or subprocess
        subprocess.call("cp -rf tmp/docops/task_documentation/ src/spec/ 2>/dev/null", shell=True)
        print "[System] Copy attempted."
    elif "GEN_DATA" in cmd or "GEN_TRACEDATA" in cmd:
        print "\n[System] Traceability generation detected. Attempting to copy Excel files to src/spec..."
        subprocess.call("cp -f build/verif/traceability/tracedata/*.xlsm src/spec/ 2>/dev/null", shell=True)
        print "[System] Copy attempted."

def run_menu(commands, source_name, is_dict=False):
    print "\n--- Available Commands (%s) ---" % source_name
    print " 0) rm -rf ./tmp ./build ./external ./.gradle (Deep Clean)"
    for i, cmd in enumerate(commands, 1):
        display_name = cmd[0] if is_dict else cmd
        print "%2d) %s" % (i, display_name)
    print " q) Exit"

    choice = raw_input("\nSelect commands to run (e.g., 0, 1, 3, 4-6): ")
    if choice.strip().lower() == 'q':
        sys.exit(0)
        
    selected_indices = parse_selection(choice, len(commands))
    if not selected_indices:
        print "Invalid selection."
        sys.exit(1)

    for idx in selected_indices:
        if idx == 0:
            actual_cmd = "rm -rf ./tmp ./build ./external ./.gradle"
            print "\n============================================================"
            print "Running step 0: Deep Clean"
            print "============================================================\n"
            subprocess.call(actual_cmd, shell=True)
            continue
            
        actual_cmd = commands[idx - 1][1] if is_dict else commands[idx - 1]
        
        # Format the actual gradle command
        if not actual_cmd.startswith("./gradlew") and not actual_cmd.startswith("gradle"):
             full_cmd = "./gradlew " + actual_cmd 
        else:
             full_cmd = actual_cmd

        # WARNING 1: Handle Virtual Displays (xvfb-run)
        if "verif_titv" in full_cmd or "anastack" in full_cmd:
             print "[System] GUI task detected. Prepending 'xvfb-run -a'..."
             full_cmd = "xvfb-run -a " + full_cmd

        log_file = generate_filename(full_cmd, idx)
        full_cmd_with_log = full_cmd + " 2>&1 | tee " + log_file
        
        print "\n============================================================"
        print "Running step %d: %s" % (idx, full_cmd)
        print "Logging to: %s" % log_file
        print "============================================================\n"
        
        subprocess.call(full_cmd_with_log, shell=True)
        auto_copy_artifacts(full_cmd)
        
    print "\n[✓] Finished executing sequence."

def print_help():
    help_text = """
========================================================================
                      AIRAVIONICS TOOLCHAIN CHEAT SHEET
========================================================================

--- DESIGN (TC0018 & TC0024) ---
* codda_run_check        : Checks CoDDA and DCSL files.
* codda_merge_code       : Generates code (.h, .i, .c) & merges user code.
* codda_import_code      : Copies merged code to src/main.
* check_design_<service> : Checks detailed design for a specific service.

--- CODE & FLOW (TC0013 & TC0021) ---
* check_code_<machine>   : Checks generated code against coding standards.
* check_flow_<service>   : Checks data/control flow against DCSL.

--- UNIT TEST & PROOF (TC0023 & TC0015) ---
* verif_proof_<service>  : Checks compliance of code against detailed design.
* prepare_tcsl_<service> : Generates a template TCSL file.
* check_tcsl_<service>   : Validates model against constraints.
* verif_tcsl_<service>   : Executes test binary on target.

--- TROUBLESHOOTING ---
1. Build failing early? 
   Run: `gradle --fix` (Deletes tmp/workspace_optimases)
2. Ghost processes / Gradle Locks?
   Run: `gradle --fix` (Finds and deletes *.lock files)
3. UT failed with Exception 13?
   Use: powerpc-freescale-eabi-addr2line -e tcsl_<SERVICE>.elf <SRR0_ADDR>
========================================================================
"""
    print help_text

def run_troubleshooter():
    print "\n--- Running Automated Troubleshooting ---"
    
    # 1. Kill ghost gradle locks
    print "[*] Searching for and deleting ghost .lock files in ~/.gradle..."
    subprocess.call('find ~/.gradle -type f -name "*.lock" -delete', shell=True)
    
    # 2. Clear optimases mounting point / workspace
    print "[*] Clearing tmp/workspace_optimases directory to force a clean environment..."
    subprocess.call('rm -rf tmp/workspace_optimases', shell=True)
    
    # 3. Kill hung processes (Optional, requires user confirmation)
    user = os.environ.get('USER', 'asilbwxv')
    ans = raw_input("[?] Do you want to kill all hanging processes for user '%s'? This will close the SSH session! (y/N): " % user)
    if ans.lower() == 'y':
        print "[!] Killing processes..."
        subprocess.call('pkill -u ' + user, shell=True)
    else:
        print "[*] Skipping process kill."

    print "\n[✓] Troubleshooting clean-up complete."

def main():
    parser = argparse.ArgumentParser(description="Airbus Avionics Gradle Helper")
    parser.add_argument('-g', '--global-menu', action='store_true', help='Open the universal toolchain commands menu')
    parser.add_argument('--fix', action='store_true', help='Run automated troubleshooting (clear locks, clean tmp)')
    
    args = parser.parse_args()

    # If -h or --help is passed, argparse handles it automatically, 
    # but we will override it to show our cheat sheet.
    if '-h' in sys.argv or '--help' in sys.argv:
        print_help()
        sys.exit(0)

    if args.fix:
        run_troubleshooter()
        sys.exit(0)

    if args.global_menu:
        run_menu(GLOBAL_COMMANDS, "Global Wiki Commands", is_dict=True)
        sys.exit(0)

    # Default Behavior: Parse local Jenkinsfile
    j_file = find_jenkinsfile()
    if not j_file:
        print "\n[!] No Jenkinsfile found in expected locations."
        sys.exit(1)
    
    commands = extract_commands(j_file)
    if not commands:
        print "\n[!] No gradlew tasks found in " + j_file
        sys.exit(1)

    run_menu(commands, j_file)

if __name__ == "__main__":
    # Custom help intercept
    if len(sys.argv) == 2 and sys.argv[1] in ['-h', '--help']:
        print_help()
        sys.exit(0)
    main()
