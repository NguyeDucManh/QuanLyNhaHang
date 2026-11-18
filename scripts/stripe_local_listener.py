"""Verified local TEST listener; signing secret is passed only in child memory."""
import argparse,json,os,queue,re,shutil,socket,subprocess,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from restaurant_system.environment import load_environment


def verified_cli_environment(key,source,cli):
    import stripe
    from stripe._http_client import RequestsClient
    if not key.startswith(('sk_test_','rk_test_')):raise ValueError('A Stripe TEST key is required')
    stripe.default_http_client=RequestsClient(timeout=15)
    account=stripe.Account.retrieve(api_key=key)
    env=os.environ.copy();env.pop('STRIPE_API_KEY',None)
    if source=='application-key':env['STRIPE_API_KEY']=key
    else:
        who=subprocess.run([cli,'whoami','--format','json'],env=env,capture_output=True,text=True,encoding='utf-8',timeout=25)
        identity=json.loads(who.stdout) if who.returncode==0 else {}
        if identity.get('account_id')!=account.id or identity.get('mode')!='test':
            raise ValueError('CLI login must match the application TEST account; no listener started')
    return env


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',type=Path,default=ROOT/'.env')
    parser.add_argument('--credential-source',choices=('application-key','cli-login'),default='cli-login')
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--test-database')
    parser.add_argument('--run',action='store_true',help='Without this option only verify account; never start server')
    args=parser.parse_args();load_environment(args.env_file)
    if os.environ.get('RENDER','').lower()=='true':raise ValueError('Local tool only; never run on Render')
    cli=shutil.which('stripe')
    if not cli:raise ValueError('Stripe CLI is not installed')
    env=verified_cli_environment(os.environ.get('STRIPE_SECRET_KEY',''),args.credential_source,cli)
    print(json.dumps({'test_account_verified':True,'credential_source':args.credential_source,'secrets_disclosed':False}),flush=True)
    if not args.run:return
    from urllib.parse import urlsplit
    host=urlsplit(os.environ['DATABASE_URL']).hostname if os.environ.get('DATABASE_URL') else os.environ.get('DB_HOST','localhost')
    if host not in ('localhost','127.0.0.1','::1') or not 1024<=args.port<=65535:raise ValueError('Only loopback PostgreSQL/server ports permitted')
    if args.test_database:
        if not args.test_database.startswith('test_stripe_hotfix_'):raise ValueError('Expected isolated test_stripe_hotfix_ database')
        env.update(DATABASE_URL='',DB_NAME=args.test_database)
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1',args.port))==0:raise ValueError('Port occupied; stop the existing local server yourself before starting this launcher')
    events=queue.Queue();listener=None;server=None
    try:
        listener=subprocess.Popen([cli,'listen','--forward-to',f'http://127.0.0.1:{args.port}/stripe/webhook/','--events','checkout.session.completed,checkout.session.async_payment_succeeded,checkout.session.async_payment_failed,checkout.session.expired,payment_intent.payment_failed'],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
        def read():
            for line in listener.stdout:events.put(line)
        threading.Thread(target=read,daemon=True).start();secret=None;deadline=time.monotonic()+45
        while time.monotonic()<deadline and not secret:
            try:line=events.get(timeout=1)
            except queue.Empty:
                if listener.poll() is not None:break
                continue
            match=re.search(r'whsec_[A-Za-z0-9]+',line)
            if match:secret=match.group(0)
            if 'stripecli_session_write' in line:raise ValueError('CLI needs Debugging Tools Write; no server started')
        if not secret:raise ValueError('Stripe listener not ready; no server started')
        env.update(STRIPE_WEBHOOK_SECRET=secret,STRIPE_PUBLIC_BASE_URL=f'http://127.0.0.1:{args.port}',DJANGO_DEBUG='true',RENDER='false',PYTHONIOENCODING='utf-8')
        server=subprocess.Popen([sys.executable,'manage.py','runserver',f'127.0.0.1:{args.port}','--noreload'],cwd=ROOT,env=env)
        print(json.dumps({'listener_ready':True,'server_port':args.port,'signing_secret_injected_in_memory':True,'env_file_changed':False}),flush=True)
        while server.poll() is None and listener.poll() is None:
            try:line=events.get(timeout=1)
            except queue.Empty:continue
            status=re.search(r'\[(\d{3})\]',line);event=re.search(r'evt_[A-Za-z0-9]+',line)
            if status and event:print(json.dumps({'event_id':event.group(0),'webhook_http':int(status.group(1))}),flush=True)
    finally:
        # Only children started by this launcher; never stop another server/listener.
        for process in (server,listener):
            if process and process.poll() is None:
                if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                else:process.terminate()


if __name__=='__main__':
    try:main()
    except (ValueError,KeyError) as exc:print(str(exc),file=sys.stderr);raise SystemExit(2)
    except Exception as exc:print('Local Stripe check failed: '+type(exc).__name__+' (details suppressed)',file=sys.stderr);raise SystemExit(2)
