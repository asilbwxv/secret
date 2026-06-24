from __future__ import print_function
import requests

# Suppress insecure request warnings for Python 2.7's bundled urllib3
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

def get_artifactory_versions(base_url, repo, package_path, auth):
    """
    Queries the Artifactory Storage API to get a list of folders (versions) in a path.
    """
    # Notice the URL structure now expects base_url to include '/artifactory'
    api_url = "{}/api/storage/{}/{}".format(base_url, repo, package_path)
    
    try:
        # The auth parameter handles the "user:token" conversion automatically
        response = requests.get(api_url, auth=auth, verify=False)
        response.raise_for_status()  # Check for HTTP errors like 401 or 404
        
        data = response.json()
        
        versions = []
        if 'children' in data:
            for child in data['children']:
                if child.get('folder') is True:
                    versions.append(child['uri'].lstrip('/'))
        
        return versions

    except requests.exceptions.RequestException as e:
        print("Error accessing {}:\n{}".format(api_url, e))
        return []

# --- Configuration ---
# Updated BASE_URL to include the /artifactory context path
BASE_URL = "https://cisas.eu.airbus.corp:8643/artifactory"
PACKAGE_PATH = "com/airbus/avsw/C00095/C00095"

# Place your actual username and token here
# This does the exact same thing as https://user:token@... but is safer
AUTH = ("asilbwxv", "cmVmdGtuOjAxOjE3OTA4OTc0ODE6ZE1jNWx2aWhnSGNjT0hnUFhmTjJNSjBzR1lN") 

# --- 1. Scan Releases ---
print("Scanning Release Versions...")
release_repo = "avionics-software-release"
release_versions = get_artifactory_versions(BASE_URL, release_repo, PACKAGE_PATH, AUTH)
print("Found Releases: {}\n".format(release_versions))

# --- 2. Scan Snapshots ---
print("Scanning Snapshot Versions...")
snapshot_repo = "avionics-software-snapshot"
snapshot_versions = get_artifactory_versions(BASE_URL, snapshot_repo, PACKAGE_PATH, AUTH)
print("Found Snapshots: {}".format(snapshot_versions))
