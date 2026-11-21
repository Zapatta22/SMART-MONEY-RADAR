"""CM37A: public static PWA resources, private API, no mutation."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.request import urlopen,Request
from urllib.error import HTTPError
from smart_money_radar.services.dashboard_http import create_read_only_server
from smart_money_radar.storage.event_store import SQLiteEventStore


class PwaReadOnly(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path=Path(temp.name)/"smr.sqlite"
        store=SQLiteEventStore(path)
        self.addCleanup(store.close)
        server=create_read_only_server(store,auth_token="fixture"*8,port=0)
        thread=Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join,5)
        self.addCleanup(server.shutdown)
        self.base="http://127.0.0.1:"+str(server.server_port)

    def test_public_manifest_icon_worker_have_no_store(self):
        for path in ("/manifest.webmanifest","/smr-icon.svg","/smr-sw.js"):
            with urlopen(self.base+path,timeout=5) as r:
                self.assertEqual(r.headers["Cache-Control"],"no-store")
                data=r.read().decode()
                self.assertNotIn("fixture"*8,data)
                if path.endswith("webmanifest"):
                    self.assertEqual(json.loads(data)["start_url"],"/dashboard")
                if path.endswith("sw.js"):
                    self.assertNotIn("caches.",data)
                    self.assertNotIn("fetch(",data)

    def test_api_private_and_admin_write_blocked(self):
        for path,method,status in (("/api/v1/dashboard","GET",401),("/api/v1/admin","POST",405)):
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(self.base+path,method=method),timeout=5)
            self.assertEqual(error.exception.code,status)

    def test_mobile_sections_and_scope(self):
        with urlopen(self.base+"/dashboard",timeout=5) as r:
            html=r.read().decode()
            for section in ("patrimonio","radares","oportunidades","negociacoes","capital","carteiras","alertas","supervisor","configuracoes"):
                self.assertIn('id="'+section+'"',html)
            self.assertIn("SIMULAÇÃO SINTÉTICA",html)
            self.assertIn("COMANDOS EXTERNOS BLOQUEADOS",html)

    def test_equity_history_has_explicit_synthetic_scope(self):
        with urlopen(self.base+"/dashboard",timeout=5) as r:
            html=r.read().decode()
            self.assertIn('id="equityHistory"',html)
            self.assertIn("não é taxa de trades",html)
            self.assertIn("Histórico insuficiente",html)

    def test_scoped_filters_and_unavailable_state_are_present(self):
        with urlopen(self.base+"/dashboard",timeout=5) as r:
            html=r.read().decode()
            for key in ("filterRadar","filterStrategy","filterSince","filterUntil","filteredPositions"):
                self.assertIn('id="'+key+'"',html)
            self.assertIn("não ao saldo global",html)
            self.assertIn("Dados indisponíveis",html)
