# artifactory_client.py
import requests
import urllib3
from config import ARTIFACTORY_BASE, ARTIFACTORY_AUTH

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_artifactory_versions(component_code, repo_type="release"):
    """Queries Artifactory for release or snapshot versions."""
    repo = "avionics-software-release" if repo_type == "release" else "avionics-software-snapshot"
    package_path = f"com/airbus/avsw/{component_code}/{component_code}"
    api_url = f"{ARTIFACTORY_BASE}/api/storage/{repo}/{package_path}"
    
    try:
        response = requests.get(api_url, auth=ARTIFACTORY_AUTH, verify=False)
        response.raise_for_status()
        data = response.json()
        
        versions = []
        if 'children' in data:
            for child in data['children']:
                if child.get('folder') is True:
                    versions.append(child['uri'].lstrip('/'))
        return sorted(versions, reverse=True)
        
    except requests.exceptions.RequestException as e:
        print(f"[!] Artifactory Error accessing {api_url}:\n{e}")
        return []

if __name__ == "__main__":
    # Test execution
    releases = get_artifactory_versions("C00095", "release")
    print(f"Found {len(releases)} releases.")
