# -*- coding: utf-8 -*-
# tools.py
from __future__ import print_function
import os
import json
import argparse
import pylightxl as xl
import sys
import zipfile
import xml.etree.ElementTree as ET
import re
if sys.version_info[0] < 3:
    reload(sys)
    sys.setdefaultencoding('utf-8')

def safe_unicode_cast(val):
    """Bulletproof cast to unicode for Python 2/3 compatibility."""
    if val is None: return u""
    if isinstance(val, unicode): return val
    if isinstance(val, str): return unicode(val, 'utf-8', 'replace')
    try:
        return unicode(val)
    except Exception:
        # Fallback to repr() if standard string conversion fails due to weird bytes
        return unicode(repr(val), 'utf-8', 'replace')

def clean_value(x):
    """Clean up values and handle text encoding safely."""
    if x is None:
        return u""
    if isinstance(x, (int, float, bool)):
        return x
    
    try:
        if isinstance(x, unicode): return x.strip()
        if isinstance(x, str): return unicode(x, 'utf-8', 'replace').strip()
        return safe_unicode_cast(x).strip()
    except NameError: # Python 3 fallback
        if isinstance(x, str): return x.strip()
        if isinstance(x, bytes): return x.decode('utf-8', 'replace').strip()
        return str(x).strip()

def is_data_table(ws):
    """
    Relaxed heuristic to determine if a worksheet contains data.
    """
    rows, cols = ws.size
    
    # Relaxed from 5x4 to 2x2 to allow smaller verification tables
    if rows < 2 or cols < 2:
        return False, 1
        
    # Scan the first 10 rows (instead of 5) to find the header row
    for r in range(1, min(11, rows + 1)):
        filled_cells = sum(1 for c in range(1, cols + 1) if clean_value(ws.index(row=r, col=c)) != u"")
        # Relaxed: If a row has at least 2 populated cells, assume it's a header
        if filled_cells >= 2:
            return True, r
            
    return False, 1

def emergency_xlsx_parser(file_path):
    """Pure Python standard library fallback parser. Unzips the .xlsx and rips the raw text."""
    jsonl_lines = []
    try:
        with zipfile.ZipFile(file_path, 'r') as z:
            
            # --- 1. Find and Extract Shared Strings (Case Insensitive) ---
            shared_strings = []
            ss_filename = next((f for f in z.namelist() if f.lower() == 'xl/sharedstrings.xml'), None)
            
            if ss_filename:
                xml_str = z.read(ss_filename)
                root = ET.fromstring(xml_str)
                # Bulletproof namespace stripping
                for elem in root.iter():
                    if '}' in elem.tag: elem.tag = elem.tag.split('}', 1)[1]
                    
                for si in root.findall('.//si'):
                    texts = [t.text for t in si.findall('.//t') if t.text]
                    shared_strings.append(u"".join(texts))

            # --- 2. Find and Extract Worksheets (Case Insensitive) ---
            sheet_files = [f for f in z.namelist() if f.lower().startswith('xl/worksheets/sheet') and f.lower().endswith('.xml')]
            
            for sheet_file in sheet_files:
                sname = sheet_file.split('/')[-1].replace('.xml', '') # e.g., 'sheet1'
                
                xml_str = z.read(sheet_file)
                root = ET.fromstring(xml_str)
                # Bulletproof namespace stripping
                for elem in root.iter():
                    if '}' in elem.tag: elem.tag = elem.tag.split('}', 1)[1]
                
                for row in root.findall('.//row'):
                    row_dict = {"_SheetName": safe_unicode_cast(sname)}
                    is_empty = True
                    col_idx = 1
                    
                    for c in row.findall('.//c'):
                        val = u""
                        v_node = c.find('v')
                        is_node = c.find('is') # Support for "inline" strings
                        
                        # If it uses the shared dictionary
                        if v_node is not None and v_node.text:
                            val = v_node.text
                            # 's' means it's a shared string index
                            if c.attrib.get('t', '') == 's': 
                                try:
                                    val = shared_strings[int(val)]
                                except:
                                    pass # Fallback to the raw index if dictionary lookup fails
                                    
                        # If it uses inline strings (no dictionary)
                        elif is_node is not None:
                            texts = [t.text for t in is_node.findall('.//t') if t.text]
                            val = u"".join(texts)
                                
                        if val.strip():
                            row_dict["Col_{0}".format(col_idx)] = safe_unicode_cast(val)
                            is_empty = False
                        col_idx += 1
                        
                    if not is_empty:
                        json_str = json.dumps(row_dict, ensure_ascii=False)
                        try:
                            if isinstance(json_str, bytes): json_str = json_str.decode('utf-8')
                        except NameError: pass
                        jsonl_lines.append(json_str)
                        
        if not jsonl_lines:
            return u"[!] Fallback parser ran, but found no readable text in the XML."
            
        return u"\n".join(jsonl_lines)
        
    except Exception as fallback_err:
        return u"[!] pylightxl crashed, and fallback parser also failed: " + safe_unicode_cast(fallback_err)

def convert_xlsm_to_jsonl(file_path):
    """Reads an Excel file, applies heuristics, and returns a JSONL string."""
    try:
        db = xl.readxl(fn=file_path)
    except Exception as e:
        # Pylightxl crashed! Trigger the emergency parser!
        print("    -> [WARNING] pylightxl crashed with '{}'. Triggering emergency Zip/XML parser...".format(safe_unicode_cast(e)))
        return emergency_xlsx_parser(file_path)

    jsonl_lines = []
    
    for sname in db.ws_names:
        ws = db.ws(ws=sname)
        valid_table, header_row_idx = is_data_table(ws)
        
        if not valid_table:
            continue

        headers = []
        for c in range(1, ws.size[1] + 1):
            val = ws.index(row=header_row_idx, col=c)
            header_str = clean_value(val)
            if not header_str: header_str = u"Col_{0}".format(c)
            headers.append(header_str)

        for r in range(header_row_idx + 1, ws.size[0] + 1):
            row_dict = {"_SheetName": safe_unicode_cast(sname)}
            is_empty_row = True
            
            for c in range(1, ws.size[1] + 1):
                v = clean_value(ws.index(row=r, col=c))
                if v != u"":
                    row_dict[headers[c-1]] = v
                    is_empty_row = False
            
            if not is_empty_row:
                json_str = json.dumps(row_dict, ensure_ascii=False)
                try:
                    if isinstance(json_str, bytes): json_str = json_str.decode('utf-8')
                except NameError: pass
                jsonl_lines.append(json_str)

    if not jsonl_lines:
        return u"[!] Excel parsed successfully, but no sheets matched the tabular data heuristic (tables might be empty or formatting is too complex)."

    return u"\n".join(jsonl_lines)


if __name__ == "__main__":
    import sys
    parser = argparse.ArgumentParser(
        description="Airbus XLSM to JSONL Converter\n\nExtracts tabular data from Airbus Excel sheets and converts it to a token-efficient JSONL format.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("input_file", nargs="?", help="Path to the .xlsm or .xlsx file to convert")
    parser.add_argument("-o", "--output", help="Optional: Path to save the JSONL output. If omitted, prints to console.")
    
    # Spawn help menu if no arguments are passed
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
        
    args = parser.parse_args()
    
    if not args.input_file or not os.path.exists(args.input_file):
        print("[!] File not found or not provided.")
        sys.exit(1)
        
    print("[*] Processing {}...".format(args.input_file))
    result = convert_xlsm_to_jsonl(args.input_file)
    
    if args.output:
        with open(args.output, "wb") as f:
            f.write(result.encode('utf-8'))
        print("[+] Saved optimized JSONL to {}".format(args.output))
    else:
        # encode for terminal printing to avoid UnicodeEncodeError on stdout
        print("\n" + result.encode('utf-8', 'replace'))
