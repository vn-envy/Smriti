import json,tempfile,pathlib
from smriti import Smriti,Fact
from smriti_enterprise import EnterpriseSmriti
results=[]
def record(name,got,expected):
 results.append({'name':name,'got':got,'expected':expected,'passed':got==expected})
with tempfile.TemporaryDirectory() as td:
 p=str(pathlib.Path(td)/'memory.db');a=Smriti(p);b=Smriti(p)
 a.add([{'content':'orchid project uses sqlite'}],session_id='a',timestamp='2026-01-01');b.search('orchid',channels={'semantic'})
 a.add([{'content':'zebra project codename Flamenco'}],session_id='b',timestamp='2026-01-02')
 record('cross_connection_cache',any('Flamenco' in r.text for r in b.search('zebra',channels={'semantic'})),True)
 a.close();b.close()
 m=Smriti(redact=True);m.add_fact(Fact(None,'api_key=FAKE_AUDIT_SECRET_12345',subject='user',predicate='secret'));record('redaction_direct_fact',any('FAKE_AUDIT' in r.text for r in m.search('api_key')),False);m.close()
 m=Smriti();ids={}
 for month,city in [(1,'Hyderabad'),(6,'Bengaluru'),(3,'Pune')]:ids[month]=m.add_fact(Fact(None,f'User lives in {city}',subject='user',predicate='lives_in',object=city,valid_from=f'2026-{month:02}-01'))
 record('late_middle_chain',[(m.store.get_fact(ids[n]).valid_from,m.store.get_fact(ids[n]).invalid_at) for n in [1,3,6]],[('2026-01-01','2026-03-01'),('2026-03-01','2026-06-01'),('2026-06-01',None)])
 backup=str(pathlib.Path(td)/'backup.json');m.export_json(backup);r=Smriti();r.import_json(backup);record('restore_history',r.stats()['facts'],3);m.close();r.close()
 m=EnterpriseSmriti();a=m.add_fact(Fact(None,'User lives Hyderabad',subject='user',predicate='lives_in',object='Hyderabad',valid_from='2026-01-01T00:00:00Z'));b=m.add_fact(Fact(None,'User lives Bengaluru',subject='user',predicate='lives_in',object='Bengaluru',valid_from='2026-06-01T00:00:00Z'))
 m.store.db.execute('UPDATE facts SET recorded_at=?,withdrawn_at=? WHERE id=?',('2026-01-02T00:00:00Z','2026-07-01T00:00:00Z',a));m.store.db.execute('UPDATE facts SET recorded_at=? WHERE id=?',('2026-07-01T00:00:00Z',b))
 record('known_aug_world_feb',[f.statement for f in m.facts_asof(world='2026-02-01T00:00:00Z',known='2026-08-01T00:00:00Z')],['User lives Hyderabad']);m.close()
print(json.dumps(results,indent=2));raise SystemExit(0 if all(r['passed'] for r in results) else 1)
