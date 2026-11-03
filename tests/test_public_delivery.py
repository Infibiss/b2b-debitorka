from test_api import client, register

def test_optional_session_does_not_log_an_error_for_anonymous_but_never_grants_access(client):
    response=client.get('/api/auth/session')
    assert response.status_code==200 and response.json()=={'session':None}
    assert response.headers['cache-control']=='no-store'
    assert client.get('/api/commercial/account').status_code==401
    session=register(client)
    current=client.get('/api/auth/session').json()['session']
    assert current['csrf_token']==session['csrf_token']
    assert current['user']['email']==session['user']['email']
    assert client.post('/api/auth/logout',headers={'X-CSRF-Token':current['csrf_token']}).status_code==200
    assert client.get('/api/auth/session').json()=={'session':None}

def test_public_compression_and_asset_cache_are_separate_from_private_api(client):
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, Response
    from fastapi.testclient import TestClient
    from starlette.middleware.gzip import GZipMiddleware
    from server.main import GuardMiddleware
    assert any(m.cls is GZipMiddleware for m in client.app.user_middleware)
    app=FastAPI()
    @app.get('/')
    def html():return HTMLResponse('<p>'+('public content '*500)+'</p>',headers={'Cache-Control':'no-cache'})
    @app.get('/assets/bundle-abc12345.js')
    def asset():return Response('/*'+('asset '*500)+'*/',media_type='application/javascript')
    @app.get('/api/private-example')
    def private():return {'data':'private'}
    app.add_middleware(GZipMiddleware,minimum_size=1000,compresslevel=6)
    app.add_middleware(GuardMiddleware,config=client.app.state.config)
    with TestClient(app) as delivery:
        public=delivery.get('/',headers={'Accept-Encoding':'gzip'})
        assert public.headers['content-encoding']=='gzip'
        assert public.headers['cache-control']=='no-cache'
        asset=delivery.get('/assets/bundle-abc12345.js')
        assert asset.headers['cache-control']=='public, max-age=31536000, immutable'
        assert delivery.get('/api/private-example').headers['cache-control']=='no-store'
        assert 'immutable' not in delivery.get('/assets/missing.js').headers.get('cache-control','')
