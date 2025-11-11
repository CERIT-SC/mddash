#!/usr/bin/env python3

import sys
import requests
import textwrap

ALG='RS256'

if len(sys.argv) != 2:
	raise TypeError(f"usage: sys.argv[0] keycloak_base_url")

base = sys.argv[1]
conf = base + '/.well-known/openid-configuration'
r = requests.get(conf)
r.raise_for_status()

jwt_uri = r.json()['jwks_uri']

r = requests.get(jwt_uri)
r.raise_for_status()

# XXX: somewhat hardcoded
cert=[ k['x5c'] for k in r.json()['keys'] if k['alg'] == ALG ][0][0]

body = "\n".join(textwrap.wrap(cert, 64))
with open('cert.pem','w') as c:
    c.write(f"-----BEGIN CERTIFICATE-----\n{body}\n-----END CERTIFICATE-----\n")

