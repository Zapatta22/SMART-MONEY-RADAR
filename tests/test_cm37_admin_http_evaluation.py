"""Adversarial HTTP tests, exclusively new temporary isolated databases."""
import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from smart_money_radar.services.admin_http_evaluation import create_isolated_admin_http
from smart_money_radar.services.dashboard_http import create_read_only_server
from smart_money_radar.storage.event_store import SQLiteEventStore

class AdminHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now=1000.
        self.server=create_isolated_admin_http(Path(self.temp.name)/"new",password="fixture-http-password",clock=lambda:self.now)
        self.addCleanup(self.server.evaluation.close)
        self.addCleanup(self.server.server_close)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join,5)
        self.addCleanup(self.server.shutdown)
        self.url="http://"+self.server.eval_host
        self.token=None;self.csrf=None
    def post(self,route,body=None,*,origin=None,csrf=None,expected=200,headers=None):
        h={"Content-Type":"application/json","Origin":self.url if origin is None else origin}
        if self.token: h["Authorization"]="Bearer "+self.token;h["X-SMR-CSRF"]=self.csrf if csrf is None else csrf
        h.update(headers or {})
        req=urllib.request.Request(self.url+"/evaluation/admin/"+route,data=json.dumps(body or {}).encode(),headers=h,method="POST")
        try:
            with urllib.request.urlopen(req,timeout=5) as res:
                self.assertEqual(res.status,expected)
                self.assertEqual(res.headers.get("Cache-Control"),"no-store")
                self.assertIsNone(res.headers.get("Access-Control-Allow-Origin"))
                return json.load(res)
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code,expected)
            self.assertEqual(exc.headers.get("Cache-Control"),"no-store")
            return json.load(exc)
    def login(self):
        data=self.post("login",{"password":"fixture-http-password"})
        self.token=data["session"];self.csrf=data["csrf"]
    def test_origin_csrf_and_external_host(self):
        self.post("login",{"password":"fixture-http-password"},origin="https://evil.invalid",expected=403)
        self.post("login",{"password":"fixture-http-password"},headers={"Host":"evil.invalid"},expected=403)
        self.login()
        self.post("confirm",{"action":"START","radar":"launch"},csrf="wrong"*8,expected=401)
    def test_logout_expiry_and_no_unauthenticated_outcome(self):
        self.post("session",expected=401)
        self.login();self.post("logout");self.post("session",expected=401)
        self.login();self.now+=901;self.post("session",expected=401)
    def test_persisted_transition_replay_and_confirmation(self):
        self.login()
        request={"request_id":"unique-test-00000001","action":"START","radar":"launch","confirmation":None}
        self.post("execute",request,expected=401)
        request["confirmation"]=self.post("confirm",{"action":"START","radar":"launch"})["confirmation"]
        result=self.post("execute",request)
        self.assertTrue(result["executed"])
        self.assertEqual(self.post("outcome",{"request_id":request["request_id"]})["status"],"APPLIED")
        self.post("execute",request,expected=401)
        self.assertEqual(len(self.post("session")["items"]),1)
    def test_strict_commands_and_no_financial_operations(self):
        self.login()
        self.post("confirm",{"action":"BUY","radar":"launch"},expected=400)
        self.post("confirm",{"action":"START","radar":"launch","extra":True},expected=400)
    def test_standard_server_keeps_admin_routes_disabled(self):
        store=SQLiteEventStore(Path(self.temp.name)/"ordinary.sqlite")
        server=create_read_only_server(store,auth_token="x"*32,port=0)
        self.addCleanup(store.close);self.addCleanup(server.server_close)
        t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
        self.addCleanup(t.join,5);self.addCleanup(server.shutdown)
        req=urllib.request.Request("http://127.0.0.1:"+str(server.server_port)+"/evaluation/admin/login",data=b"{}")
        with self.assertRaises(urllib.error.HTTPError) as ctx:urllib.request.urlopen(req,timeout=5)
        self.assertEqual(ctx.exception.code,405)
    def test_no_token_in_url_or_html_and_no_cache(self):
        with urllib.request.urlopen(self.url+"/dashboard",timeout=5) as res:
            html=res.read().decode()
            self.assertIn("adminEval",html)
            self.assertEqual(res.headers.get("Cache-Control"),"no-store")
            self.assertNotIn("localStorage",html)
        self.login()
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.url+"/evaluation/admin/session?session="+self.token,timeout=5)
        self.assertEqual(ctx.exception.code,405)
