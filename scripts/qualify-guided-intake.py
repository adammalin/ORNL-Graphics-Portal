"""Explicit synthetic-only loopback qualification of the real portal code.

No real Microsoft/Smartsheet credentials, config, tunnel, source rows or mail.
Uses the project's existing injected transport fixtures and private temporary DB.
Never import this launcher into the actual pilot or expose it through a tunnel.
"""
import copy
import argparse
from datetime import timedelta
from pathlib import Path
import sys
import re

root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root),str(root/'tests')]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--synthetic',action='store_true',required=True)
parser.add_argument('--port',type=int,default=18771)
args=parser.parse_args()

from test_microsoft_intake import MicrosoftIntakeTests, OTHER, MEMBER
from backend.pilot import SESSION_COOKIE
from backend.microsoft_intake import COOKIE
from backend.guided_intake import today_eastern
from flask import redirect, jsonify, Response
from waitress import serve

p=MicrosoftIntakeTests();p.setUp()
today=today_eastern()
p.value['guidedIntake']={'enabled':True,'calendar':{'approved':True,'label':'Fictional qualification calendar — not the approved ORNL schedule','validThrough':(today+timedelta(days=365)).isoformat(),'closedDates':['2026-11-26','2026-11-27']}}

p.value['staffIntakeRules']=copy.deepcopy(p.value['guidedIntake'])
p.value['staffIntakeRules']['calendar'].update(approved=False,testOnly=True)

@p.app.get('/qa')
def qa_home():
    return Response('''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Graphics Portal workflow qualification</title><link rel="stylesheet" href="/ornl-design-tokens.css"><link rel="stylesheet" href="/styles.css"></head><body><main class="pilot-login"><div class="eyebrow">ISOLATED SYNTHETIC WORKFLOW TEST</div><h1>Try the whole request workflow.</h1><p>This runs the actual portal application with fictional Microsoft/Smartsheet transports and a temporary database. No real request or notification is sent.</p><div class="notice">The holiday dates are sample test closures, not the approved ORNL calendar. Role links below are simulator controls and do not exist in the real pilot.</div><p><a class="button button-primary" href="/qa/requester">1. Employee request form</a></p><p><a class="button" href="/qa/staff">2. Coordinator workspace</a></p><p><a class="button" href="/qa/designer">3. Designer workspace</a></p><p><a class="button" href="/qa/my-requests">4. Employee My Requests</a></p><p><a class="button" href="/qa/other-requester">Other employee — no access to first employee's requests</a></p><p>All test state resets when this qualification server stops.</p></main></body></html>''',mimetype='text/html')

def requester_response(sid,path):
    response=redirect(path);response.set_cookie(COOKIE,sid,secure=True,httponly=True,samesite='Lax',path='/');return response

@p.app.get('/qa/requester')
def qa_requester():return requester_response(requester_sid,'/request')
@p.app.get('/qa/my-requests')
def qa_my_requests():return requester_response(requester_sid,'/my-requests')
@p.app.get('/qa/other-requester')
def qa_other_requester():return requester_response(other_sid,'/my-requests')

def staff_response(who,path):
    state,browser=p.runtime.begin_login();sid,_=p.runtime.complete_login(state,browser,who)
    response=redirect(path);response.set_cookie(SESSION_COOKIE,sid,secure=True,httponly=True,samesite='Lax',path='/');return response
@p.app.get('/qa/staff')
def qa_staff():return staff_response('coord','/#/projects')
@p.app.get('/qa/designer')
def qa_designer():return staff_response('designer','/#/my-work')
@p.app.get('/qa/metrics')
def qa_metrics():return jsonify(synthetic=True,rows=len(p.fake.rows),writeCalls=sum(c[0]!='GET' for c in p.fake.calls),externalServices='fictional injected transports only')

@p.app.after_request
def qa_simulation_banner(response):
    if response.mimetype=='text/html':
        response.direct_passthrough=False
        html=response.get_data(as_text=True)
        html=re.sub(r'(<body\b[^>]*>)', r'\1<div class="mode-banner"><strong>ISOLATED WORKFLOW SIMULATION</strong> — Fictional sign-ins, records and calendar. No real Microsoft, Smartsheet or email connection.</div>', html, count=1)
        response.set_data(html)
    return response

employee=p.ms_login();requester_sid=next(iter(p.intake.sessions))
p.ms.claims['oid']=OTHER;p.ms.profile['id']=OTHER;p.ms.profile['displayName']='Other Fictional Employee';other=p.ms_login()
other_sid=next(sid for sid in p.intake.sessions if sid!=requester_sid)
p.ms.claims['oid']=MEMBER;p.ms.profile['id']=MEMBER
p.runtime.config.value['guidedIntake']=p.value['guidedIntake']
p.runtime.config.value['staffIntakeRules']=p.value['staffIntakeRules']
p.runtime.config.origin=f'http://localhost:{args.port}'
p.runtime.config.host='localhost';p.runtime.reload_config=None


print(f'Synthetic integrated workflow: http://localhost:{args.port}/qa',flush=True)
try:serve(p.app,host='127.0.0.1',port=args.port,threads=4)
finally:p.tearDown()
