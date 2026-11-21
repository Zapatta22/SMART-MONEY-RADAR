"""Real Chromium evaluation admin UI, no production database."""
import os,tempfile,threading,unittest
from pathlib import Path
from smart_money_radar.services.admin_http_evaluation import create_isolated_admin_http
@unittest.skipUnless(os.environ.get("SMR_BROWSER_TEST")=="1","dedicated browser CI")
class AdminFieldsBrowser(unittest.TestCase):
    def test_authenticated_fields_create_virtual_account(self):
        from playwright.sync_api import sync_playwright
        with tempfile.TemporaryDirectory() as tmp:
            srv=create_isolated_admin_http(Path(tmp)/"new",password="fixture-local-admin-123")
            t=threading.Thread(target=srv.serve_forever,daemon=True);t.start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    page=browser.new_page(viewport={"width":390,"height":844},is_mobile=True,has_touch=True)
                    page.on("dialog",lambda d:d.accept())
                    errors=[];page.on("pageerror",lambda err:errors.append(str(err)))
                    page.goto("http://"+srv.eval_host+"/dashboard")
                    page.locator("#adminPassword").fill("fixture-local-admin-123")
                    page.locator("#adminLogin").click()
                    page.get_by_text("Sessão local de avaliação autenticada.").wait_for()
                    page.locator("#adminAction").select_option("CAPITAL_CREATE")
                    page.locator("#capAccount").fill("launch-demo")
                    page.locator("#capInitial").fill("100")
                    for k in ("total_exposure","per_radar","per_strategy","per_token","per_pool","per_wallet","max_daily_loss","max_drawdown"):
                        page.locator("#lim_"+k).fill("0,5")
                    page.locator("#adminExecute").click()
                    page.wait_for_function("document.getElementById('adminResult').textContent.includes('APPLIED')")
                    self.assertEqual(errors,[])
                    browser.close()
            finally:
                srv.shutdown();srv.server_close();t.join();srv.evaluation.close()
