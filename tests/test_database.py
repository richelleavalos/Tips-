import tempfile,unittest
from pathlib import Path
from backend.config import Settings
from backend.database import connect,initialize

class DatabaseTests(unittest.TestCase):
    def test_schema_initializes_and_enforces_foreign_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings=Settings('test','127.0.0.1',8000,Path(tmp)/'tips.db',('http://127.0.0.1:8000',),'test-secret',False,3600,1048576,120)
            initialize(settings)
            with connect(settings) as db:
                tables={r['name'] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
                self.assertIn('products',tables); self.assertIn('orders',tables); self.assertIn('portfolio_projects',tables); self.assertEqual(db.execute('PRAGMA foreign_keys').fetchone()[0],1)

if __name__=='__main__': unittest.main()
