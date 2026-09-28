from pathlib import Path

ROOT = Path(__file__).resolve().parent
js = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
html = (ROOT / "templates/dashboard.html").read_text(encoding="utf-8")
app = (ROOT / "app.py").read_text(encoding="utf-8")

assert "const UI_VERSION = '2.7.9';" in js
assert 'PROTOTYPE_VERSION = "2.7.9"' in app
assert "preferredDemoHiveId" in js
assert "showNewHiveDemoAction" not in js
assert 'registration-demo-action' not in js and 'registration-demo-action' not in html
assert 'run-new-hive-demo' not in js and 'run-new-hive-demo' not in html
assert "location.hash = 'ledger'" in js
assert 'body:JSON.stringify({hive_id:hiveId})' in js
assert "$('seed-demo')" in js
assert "/api/demo/seed" in js
assert "clearEventLog();" in js
assert "state.verifications = {};" in js
assert "state.preferredDemoHiveId = null;" in js
assert 'DEMO_CONTROLS_ENABLED' in app
assert 'current_base_url())' in app
assert '?v=2.7.9' in html
print("PASS: v2.7.9 hive registration -> selected demo hive -> harvest -> ledger + reset UI contract")
