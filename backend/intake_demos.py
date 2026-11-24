"""Staff-authenticated, browser-only comparison demos. No native write adapter."""
from datetime import timedelta
import json
from flask import Response, redirect
from backend.server import WEB
from backend.guided_intake import SERVICES, today_eastern, minimum_date


def register(app, signed_in):
    def checked(version):
        signed_in()
        if version not in ('classic', 'guided'):
            from backend.dev_store import WriteError
            raise WriteError('Choose the Classic or Guided demo.', 404)

    @app.get('/intake-demos', endpoint='intake_demo_home')
    def home():
        signed_in()
        return redirect('/intake-demos/guided', 303)

    @app.get('/intake-demos/<version>', endpoint='intake_demo_page')
    def page(version):
        checked(version)
        if version == 'classic':
            html = (WEB / 'index.html').read_text().replace('href="./', 'href="/').replace('src="./', 'src="/')
            html = html.replace('src="/runtime-config.js"', 'src="/intake-demos/classic/config.js"')
            html = html.replace('<div id="mode-banner"', '<nav class="mode-banner" aria-label="Intake demo versions"><a href="/intake-demos/classic#/new" aria-current="page">Classic form demo</a> · <a href="/intake-demos/guided">Guided form demo</a> · <a href="/">Return to DEV workspace</a></nav><div id="mode-banner"')
        else:
            html = (WEB / 'intake-demo.html').read_text()
        return Response(html, mimetype='text/html')

    @app.get('/intake-demos/<version>/config.js', endpoint='intake_demo_config')
    def configuration(version):
        checked(version)
        today = today_eastern()
        # Sample test closures are explicitly not an approved operational calendar.
        closed = ['2026-11-26', '2026-11-27']
        demo = {'dataMode': 'demo', 'intakeComparison': True, 'intakeVersion': version,
                'demoCalendar': {'enabled': True, 'ready': True, 'today': today.isoformat(),
                    'earliest': minimum_date(today, closed).isoformat(), 'closedDates': closed,
                    'validThrough': (today + timedelta(days=365)).isoformat(),
                    'calendarLabel': 'Sample closures for demo only — official ORNL calendar pending',
                    'notificationsEnabled': False,
                    'services': [{'id': sid, 'label': s[0], 'team': s[1], 'choices': s[2]} for sid, s in SERVICES.items()]}}
        return Response('window.PORTAL_CONFIG=Object.freeze(' + json.dumps(demo) + ');', mimetype='text/javascript')
