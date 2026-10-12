# Google login spike (2026-10-12)

Versions tested: Authlib 1.8.0, cryptography 50.0.2, Python 3.14 (shared venv).

## 1. Authlib outside a framework

Working calls (verified):

```python
from authlib.integrations.requests_client import OAuth2Session
from authlib.jose import JsonWebKey, jwt

s = OAuth2Session(client_id, client_secret, scope="openid email profile",
                  redirect_uri=redirect_uri, code_challenge_method="S256")
url, state = s.create_authorization_url(
    "https://accounts.google.com/o/oauth2/v2/auth",
    state=my_state, nonce=my_nonce, code_verifier=my_verifier)   # all three honoured

# jwks = parsed JSON of Google's jwks_uri; keys carry their own "kid"
keyset = JsonWebKey.import_key_set(jwks)          # a plain {"keys": [...]} dict also works
claims = jwt.decode(id_token, keyset, claims_options={
    "iss": {"values": ["https://accounts.google.com", "accounts.google.com"]},
    "aud": {"value": client_id},
    "exp": {"essential": True},
    "nonce": {"essential": True, "value": my_nonce}})
claims.validate()          # exp/iss/aud/nonce are checked HERE, not in decode
```

Observations:

- The authorization URL contains `code_challenge=...`, `code_challenge_method=S256`, `nonce=n`,
  and the `state=` passed in is used verbatim (returned `state` equals it).
- `code_verifier` passed to `create_authorization_url` yields the S256 challenge; the same verifier
  must be given again at token exchange.
- `jwt.encode` returns `bytes`; `jwt.decode` accepts str or bytes.
- Key lookup is by the token header `kid` against the key set. A key whose `kid` is absent from the
  set raises `ValueError("Key not found")` (not a JoseError). `JsonWebKey.generate_key` assigns a
  thumbprint `kid`, so tests must set the same `kid` in the header and the key set.
- `authlib.jose` emits `AuthlibDeprecationWarning` (use `joserfc` instead; "compatible before
  version 2.0.0"). Works in 1.8.0; pin Authlib `<2` or consider `joserfc` later.
- Building the authorization URL makes no network call (socket `connect` patched to raise; never hit).
- `exp` is only enforced by `validate()`; mark it `essential` so a token without `exp` is refused.

Refusal experiments (each token otherwise valid, key set containing the right key):

| Case | Raised | By |
|---|---|---|
| Signed by a different key (same kid) | `BadSignatureError` | `decode` |
| Wrong `iss` | `InvalidClaimError` | `validate` |
| Wrong `aud` | `InvalidClaimError` | `validate` |
| Expired `exp` | `ExpiredTokenError` | `validate` |
| Wrong `nonce` | `InvalidClaimError` | `validate` |
| Missing `nonce` (essential) | `MissingClaimError` | `validate` |
| `alg: none`, with trailing dot | `UnsupportedAlgorithmError` | `decode` |
| `alg: none`, no signature segment | `DecodeError` | `decode` |
| HS256 signed with the public key PEM (alg confusion) | `builtins.KeyError: 0` | `decode` |
| Unknown `kid` | `builtins.ValueError("Key not found")` | `decode` |

All refused. Two of them raise plain builtins (`KeyError`, `ValueError`), not `JoseError`, so the
implementation must treat ANY exception from `decode`/`validate` as a failed login (catch `Exception`
around the pair, fail closed, never log the token).

## 2. Google redirect URI rules

Source: https://developers.google.com/identity/protocols/oauth2/web-server (redirect URI validation rules).

- `http://localhost`: allowed over plain HTTP. "Localhost URIs (including localhost IP address URIs) are exempt from this rule." The page's testing example uses a port: `http://localhost:8080`.
- `http://127.0.0.1:<port>`: the page does not name it explicitly; it is covered by "localhost IP address URIs" exempt wording. Not literally stated for Web application clients, so confirm in Task 10.
- Path: allowed; only "Redirect URIs cannot contain a path traversal". The value "must exactly match" a registered URI (port and path included).
- Other hosts: "Redirect URIs must use the HTTPS scheme, not plain HTTP." and "Hosts cannot be raw IP addresses."

Caveat: only the first 100000 of 121533 characters of the page were read by the fetch tool.

## 3. Issuer and discovery

Source: https://developers.google.com/identity/openid-connect/openid-connect

- `iss` is "https://accounts.google.com or accounts.google.com": accept both exactly.
- Discovery document: `https://accounts.google.com/.well-known/openid-configuration` (gives `jwks_uri`, `authorization_endpoint`, `token_endpoint`).

## Verdict

- Authlib `OAuth2Session` with PKCE S256, state and nonce outside a framework: works.
- `authlib.jose` ID-token verification (signature, iss, aud, exp, nonce, alg none, alg confusion): works, all refused.
- Google accepts `http://localhost:<port>/<path>` for Web clients: works per docs; `127.0.0.1` implied, not explicit.
- Task 7 must change: (a) wrap decode+validate in a fail-closed `except Exception` (KeyError/ValueError escape JoseError); (b) pass `iss` as `values` with both Google issuer forms; (c) mark `exp` essential; (d) suppress or filter the `authlib.jose` deprecation warning and pin `authlib<2`; (e) register the exact redirect URI (including port and path) and prefer `localhost` over `127.0.0.1`.

Live end-to-end run: pending, done in Task 10
