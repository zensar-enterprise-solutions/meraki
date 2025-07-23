import requests
import json

# API configuration
headers = {
    'X-Cisco-Meraki-API-Key': '06ad532f080407244d088cf1f465587b89ab2458',
    'Content-Type': 'application/json'
}
base_url = 'https://api.meraki.com/api/v1'

def test_meraki_api():
    # Test organizations endpoint
    try:
        orgs_response = requests.get(f'{base_url}/organizations', headers=headers)
        orgs_response.raise_for_status()
        orgs = orgs_response.json()
        print("\nOrganizations:", json.dumps(orgs, indent=2))
        
        if not orgs:
            print("No organizations found!")
            return
            
        # Use the first organization's ID
        org_id = orgs[0]['id']
        print(f"\nUsing organization ID: {org_id}")
        
        # Test networks endpoint
        networks_response = requests.get(
            f'{base_url}/organizations/{org_id}/networks',
            headers=headers
        )
        networks_response.raise_for_status()
        networks = networks_response.json()
        print("\nNetworks:", json.dumps(networks, indent=2))
        
    except requests.exceptions.RequestException as e:
        print(f"\nAPI Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Status code: {e.response.status_code}")
            print(f"Response: {e.response.text}")

if __name__ == "__main__":
    test_meraki_api()