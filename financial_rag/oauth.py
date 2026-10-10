"""One-shot official ChatGPT plan verification; never saves credentials.

Sources: https://developers.openai.com/siwc/token-sharing-open-source/sign-in
https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference
"""
import base64
import hashlib
import json
import secrets
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ROOT = Path.home() / '.financial-report-rag'
ROOT.mkdir(parents=True, exist_ok=True)
RESULT = ROOT / 'result.json'
AUTH = 'https://auth.openai.com'
API = 'https://api.openai.com/v1'


def report(stage, **fields):
    data = {'stage': stage, 'updated_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), **fields}
    RESULT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(data, ensure_ascii=False), flush=True)


def request_json(url, data=None, headers=None, form=False):
    body = None if data is None else (urlencode(data).encode() if form else json.dumps(data).encode())
    h = {'Accept': 'application/json', **(headers or {})}
    if body is not None:
        h['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
    with urlopen(Request(url, data=body, headers=h), timeout=30) as response:
        return json.load(response)


def unb64(value):
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def verify_id_token(token, client_id, nonce, discovery):
    head, payload, signature = token.split('.')
    header = json.loads(unb64(head))
    if header.get('alg') != 'RS256':
        raise RuntimeError('unexpected_id_token_algorithm')
    keys = request_json(discovery['jwks_uri'])['keys']
    key = next(k for k in keys if k.get('kid') == header.get('kid') and k.get('kty') == 'RSA')
    public_key = rsa.RSAPublicNumbers(int.from_bytes(unb64(key['e']), 'big'), int.from_bytes(unb64(key['n']), 'big')).public_key()
    public_key.verify(unb64(signature), (head + '.' + payload).encode(), padding.PKCS1v15(), hashes.SHA256())
    claims = json.loads(unb64(payload))
    audiences = claims.get('aud', [])
    if isinstance(audiences, str):
        audiences = [audiences]
    if (claims.get('iss') != discovery['issuer'] or client_id not in audiences
            or claims.get('exp', 0) <= time.time() or claims.get('nonce') != nonce
            or not claims.get('sub') or claims.get('nbf', 0) > time.time() + 30):
        raise RuntimeError('id_token_claim_validation_failed')

def save_credentials(data):
    import ctypes
    from ctypes import wintypes
    if __import__('os').name != 'nt':
        raise RuntimeError('OAuth credential storage currently requires Windows DPAPI')
    class Blob(ctypes.Structure):
        _fields_ = [('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    raw=json.dumps(data).encode()
    buffer=ctypes.create_string_buffer(raw)
    src=Blob(len(raw),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)))
    dst=Blob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(src),None,None,None,None,0,ctypes.byref(dst)):
        raise RuntimeError('Credential encryption failed')
    try:
        encrypted=ctypes.string_at(dst.data,dst.size)
    finally:
        ctypes.windll.kernel32.LocalFree(dst.data)
    temporary=ROOT/'credentials.tmp'
    temporary.write_bytes(encrypted)
    temporary.replace(ROOT/'credentials.dpapi')

def load_credentials():
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    raw=(ROOT/'credentials.dpapi').read_bytes()
    buffer=ctypes.create_string_buffer(raw)
    src=Blob(len(raw),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte))); dst=Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(src),None,None,None,None,0,ctypes.byref(dst)):
        raise RuntimeError('Credential decryption failed')
    try:
        return json.loads(ctypes.string_at(dst.data,dst.size))
    finally:
        ctypes.windll.kernel32.LocalFree(dst.data)

def access_token():
    token=load_credentials()
    if token.get('expires_at',0)<time.time()+120:
        updated=request_json(AUTH+'/api/accounts/oauth/token',{'grant_type':'refresh_token',
            'client_id':token['client_id'],'refresh_token':token['refresh_token'],'resource':API},form=True)
        token.update(updated)
        token['expires_at']=time.time()+updated.get('expires_in',3600)
        save_credentials(token)
    return token['access_token']

def main():
    discovery=request_json(AUTH+'/.well-known/openid-configuration')
    host_file=ROOT/'host_id.txt'
    if not host_file.exists():
        host_file.write_text('urn:uuid:'+str(uuid.uuid4()),encoding='ascii')
    state,nonce,verifier=secrets.token_urlsafe(32),secrets.token_urlsafe(32),secrets.token_urlsafe(64)
    callback={}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_GET(self):
            parsed=urlsplit(self.path)
            if parsed.path!='/auth/callback':
                self.send_error(404); return
            params=parse_qs(parsed.query)
            if not secrets.compare_digest(params.get('state',[''])[0],state):
                self.send_error(400); return
            callback.update({k:v[0] for k,v in params.items()})
            self.send_response(200)
            self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Cache-Control','no-store'); self.end_headers()
            self.wfile.write('<meta charset="utf-8"><p>Authorization received. Return to Codex.</p>'.encode())
    server=HTTPServer(('127.0.0.1',0),Handler); server.timeout=1
    redirect=f'http://127.0.0.1:{server.server_port}/auth/callback'
    params={'client_id':'dynamic_agent_client','agent_name_hint':'Financial Report RAG',
        'ext_agent_host_id':host_file.read_text().strip(),'response_type':'code','redirect_uri':redirect,
        'scope':'openid profile email offline_access resource.invoke chatgpt.tokens.use.direct',
        'resource':API,'state':state,'nonce':nonce,'code_challenge_method':'S256',
        'code_challenge':base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')}
    webbrowser.open(AUTH+'/api/accounts/authorize?'+urlencode(params))
    print('Waiting for official browser authorization (15 minutes).',flush=True)
    deadline=time.monotonic()+900
    try:
        while not callback and time.monotonic()<deadline: server.handle_request()
    finally: server.server_close()
    client_id=callback.get('client_id','')
    if callback.get('error') or not client_id or not callback.get('code'):
        raise RuntimeError('Authorization not completed')
    token=request_json(AUTH+'/api/accounts/oauth/token',{'grant_type':'authorization_code',
        'client_id':client_id,'code':callback['code'],'code_verifier':verifier,'redirect_uri':redirect,'resource':API},form=True)
    verify_id_token(token['id_token'],client_id,nonce,discovery)
    if 'chatgpt.tokens.use.direct' not in token.get('scope','').split():
        raise RuntimeError('Direct inference permission missing')
    token.update(client_id=client_id,expires_at=time.time()+token.get('expires_in',3600))
    save_credentials(token)
    print('Authorization saved encrypted outside the repository.',flush=True)

if __name__=='__main__':
    main()
