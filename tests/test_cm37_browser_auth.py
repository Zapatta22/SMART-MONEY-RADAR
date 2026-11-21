"""Executable Chromium browser regression in the isolated CI environment."""
import os
import tempfile
import threading
import unittest
from pathlib import Path
from smart_money_radar.storage.event_store import SQLiteEventStore
from smart_money_radar.services.dashboard_http import create_read_only_server

@unittest.skipUnless(os.environ.get("SMR_BROWSER_TEST")=="1","dedicated browser CI")
class BrowserAuth(unittest.TestCase):
    def test_android_viewport_empty_database_authentication(self):
        from playwright.sync_api import sync_playwright
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"eval.sqlite"
            SQLiteEventStore(path).close()
            store=SQLiteEventStore(path,read_only=True)
            server=create_read_only_server(store,auth_token="a"*64,port=0)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    page=browser.new_page(viewport={"width":390,"height":844},is_mobile=True,has_touch=True)
                    errors=[]
                    page.on("pageerror",lambda error:errors.append(str(error)))
                    page.goto("http://127.0.0.1:"+str(server.server_port))
                    page.get_by_text("Interface pronta.",exact=False).wait_for()
                    page.locator("#token").fill("b"*64)
                    page.locator("#connect").click()
                    page.get_by_text("Token inválido ou expirado.",exact=False).wait_for()
                    page.locator("#token").fill("  "+"a"*64+"  ")
                    page.locator("#connect").click()
                    page.get_by_text("Conexão aprovada",exact=False).wait_for()
                    self.assertIn("Nenhuma conta",page.locator("#equityCards").inner_text())
                    self.assertEqual(errors,[])
                    browser.close()
            finally:
                server.shutdown();server.server_close();thread.join();store.close()
