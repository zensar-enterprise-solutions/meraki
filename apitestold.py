import requests

headers = {'X-Cisco-Meraki-API-Key': '06ad532f080407244d088cf1f465587b89ab2458'}

# List organizations
orgs = requests.get('https://api.meraki.com/api/v1/organizations', headers=headers)
print("Organizations:", orgs.json())

org_id = '1666125'

# List networks in the organization
networks = requests.get(f'https://api.meraki.com/api/v1/organizations/{org_id}/networks', headers=headers)
print("Networks status code:", networks.status_code)
try:
    print("Networks:", networks.json())
except Exception as e:
    print("Networks raw response:", networks.text)
    print("Error:", e)