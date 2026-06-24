from __future__ import print_function
import urllib2
import json
import os

# --- Configuration ---
GHE_HOST = "gheprivate.intra.corp"
OWNER = "software-avionics"
REPO = "C00280"
PR_NUMBER = 49

# Replace with your actual token or export it as an environment variable
TOKEN = os.environ.get("GHE_TOKEN", "YOUR_PERSONAL_ACCESS_TOKEN_HERE")

def fetch_pr_comments():
    # Using .format() instead of f-strings for Python 2.7 compatibility
    url = "https://{}/api/v3/repos/{}/{}/pulls/{}/comments".format(GHE_HOST, OWNER, REPO, PR_NUMBER)
    
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": "token {}".format(TOKEN)
    }
    
    req = urllib2.Request(url, headers=headers)
    
    try:
        # Python 2.7.5 urllib2 does not verify SSL certificates by default
        response = urllib2.urlopen(req)
        # In Python 2, response.read() returns a string, so no need to .decode('utf-8')
        comments = json.loads(response.read())
        return comments
    except urllib2.HTTPError as e:
        print("Failed to fetch data. HTTP Error: {}".format(e.code))
        return []
    except urllib2.URLError as e:
        print("Failed to connect to the API: {}".format(e.reason))
        return []

def print_diffs_and_remarks(comments):
    if not comments:
        print("No remarks found or failed to fetch.")
        return

    print("--- Pull Request #{} Remarks ---".format(PR_NUMBER))
    print("=" * 60)

    for comment in comments:
        # Safely get dictionary keys
        file_path = comment.get('path', 'Unknown file')
        diff_hunk = comment.get('diff_hunk', 'No diff hunk available')
        
        # Safely get nested user login
        user_dict = comment.get('user', {})
        user = user_dict.get('login', 'Unknown user') if user_dict else 'Unknown user'
        
        remark = comment.get('body', '')

        print("FILE: {}".format(file_path))
        print("-" * 60)
        print(diff_hunk) 
        print("-" * 60)
        print("REMARK by @{}:".format(user))
        print(remark)
        print("=" * 60 + "\n")

if __name__ == "__main__":
    if TOKEN == "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":
        print("Please update the TOKEN variable with your GitHub Enterprise PAT.")
    else:
        comments_data = fetch_pr_comments()
        print_diffs_and_remarks(comments_data)
