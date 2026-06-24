import urllib2
import json
import ssl
from config import GITHUB_API_URL, GITHUB_TOKEN, GITHUB_ORG, REQUEST_DELAY


try:
    CTX = ssl._create_unverified_context()
except AttributeError:
    CTX = None

url = "https://gheprivate.intra.corp/api/v3/repos/software-avionics/C00216/git/trees/master?recursive=1"
req = urllib2.Request(url)
req.add_header("Authorization", "Bearer " + GITHUB_TOKEN)

print("Fetching full repository tree from GitHub API...")
response = urllib2.urlopen(req, context=CTX) if CTX else urllib2.urlopen(req)
tree = json.loads(response.read())['tree']

print("\n--- MATCHING PATHS IN REPO ---")
found = 0
for item in tree:
    path = item['path']
    # Let's search broadly for ANY path containing these keywords
    if 'A615A' in path.upper() or 'ENVIRONMENT' in path.upper():
        print(path)
        found += 1

print("\nTotal matched paths: {}".format(found))
