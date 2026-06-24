# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import json
import pylightxl as xl

XLSM_PATH = "C00216_RAM-HLR.xlsm"
OUT_FILE = "C00216_RAM-HLR.jsonl"

def clean_value(x):
    """Clean up values and handle text encoding safely."""
    if x is None:
        return ""
    if isinstance(x, (int, float, bool)):
        return x
    
    try:
        if isinstance(x, unicode):
            return x.strip()
        if isinstance(x, str):
            return unicode(x, 'utf-8', 'replace').strip()
        return unicode(x).strip()
    except NameError:
        if isinstance(x, str):
            return x.strip()
        if isinstance(x, bytes):
            return x.decode('utf-8', 'replace').strip()
        return str(x).strip()

def is_data_table(ws):
    """
    Heuristic to determine if a worksheet is a real tabular dataset 
    and not just a cover page or metadata sheet.
    """
    rows, cols = ws.size
    
    # Rule 1: A data table needs a minimum number of rows and columns
    if rows < 5 or cols < 4:
        return False, 1
        
    # Rule 2: A data table should have a dense header row.
    # We check the first few rows. If we find a row where most columns have text, 
    # it's highly likely to be a data table.
    for r in range(1, min(5, rows + 1)):
        filled_cells = sum(1 for c in range(1, cols + 1) if clean_value(ws.index(row=r, col=c)) != "")
        
        # If at least 60% of the columns in this row have text, it's a solid header
        if filled_cells >= (cols * 0.6) and filled_cells >= 3:
            return True, r  # Return True and the index of the header row
            
    return False, 1

def main():
    db = xl.readxl(fn=XLSM_PATH)

    with open(OUT_FILE, "wb") as f:
        for sname in db.ws_names:
            ws = db.ws(ws=sname)
            
            # --- APPLY HEURISTIC TO IGNORE NON-DATA TABS ---
            valid_table, header_row_idx = is_data_table(ws)
            if not valid_table:
                print("Skipping non-data tab (Metadata/Cover Page):", sname)
                continue
                
            print("Processing tabular data tab:", sname)

            # Extract headers (using the row identified by our heuristic)
            headers = []
            for c in range(1, ws.size[1] + 1):
                val = ws.index(row=header_row_idx, col=c)
                header_str = clean_value(val)
                if not header_str:
                    header_str = "Col_{0}".format(c)
                headers.append(header_str)

            # Extract Data Rows
            for r in range(header_row_idx + 1, ws.size[0] + 1):
                row_dict = {"_SheetName": sname}
                is_empty_row = True
                
                for c in range(1, ws.size[1] + 1):
                    v = clean_value(ws.index(row=r, col=c))
                    # Only add data if it isn't blank (Saves massive file space)
                    if v != "":
                        row_dict[headers[c-1]] = v
                        is_empty_row = False
                
                # Only write the row if it contains actual data
                if not is_empty_row:
                    json_str = json.dumps(row_dict, ensure_ascii=False)
                    
                    try:
                        if isinstance(json_str, unicode):
                            json_bytes = json_str.encode('utf-8')
                        else:
                            json_bytes = json_str
                    except NameError:
                        if isinstance(json_str, str):
                            json_bytes = json_str.encode('utf-8')
                        else:
                            json_bytes = json_str

                    f.write(json_bytes + b'\n')
                    
    print("Successfully finished writing:", OUT_FILE)

if __name__ == "__main__":
    main()
