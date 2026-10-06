"""Fictional hospital RP curriculum, not clinical credentials or real patient guidance."""
import sqlite3, os, time
from pathlib import Path
COURSES = {
 'emt': ('EMT Trainee','EMT',[], 'EMS', [
 ('Scene & dispatch','Confirm the RP scene is safe before entering. Report your unit, location and requested backup. Follow city rules and your supervisor rather than improvising dangerous scenes.'),
 ('Patient interaction','Introduce your character and ask consent for examination RP. Ask what happened, listen, and describe actions without forcing another player’s response. Use fictional information only.'),
 ('Transport & handoff','Arrange RP transport with the team, tell dispatch your destination, then hand off the character name, incident, observations and actions to the receiving provider.')], [
 ('What comes before entering a scene?',['Check scene safety','Rush in alone','Ignore dispatch'],0),
 ('Which radio report is useful?',['Only your nickname','Unit, location and backup needed','Unrelated chat'],1),
 ('Before examination RP you should…',['Force the outcome','Use real medical records','Introduce yourself and ask consent'],2),
 ('A proper handoff includes…',['Incident, observations and actions','Only payment','No information'],0),
 ('Who determines another character’s reaction?',['The responding player','Your bot','You without consent'],0)]),
 'paramedic': ('Paramedic Trainee','Paramedic',['EMT'],'EMS',[
 ('Coordinating a response','Assign RP tasks clearly, request extra units when needed, and follow approved city EMS procedures. Advancement does not give command authority over hospital leadership.'),
 ('Scope & communication','Describe only interventions approved by your city’s EMS policy. When uncertain, involve a senior provider. Keep radio traffic short and never use clinical RP as real medical advice.'),
 ('Incident report','Record fictional patient identity, scene, observations, approved RP actions, transport destination and receiving staff. Debrief privately and report equipment needs.')],[
 ('Who approves intervention scope?',['City EMS policy','Your personal guess','Any spectator'],0),
 ('When uncertain, you should…',['Invent an intervention','Ask a senior provider','Hide uncertainty'],1),
 ('A paramedic promotion gives…',['Hospital Director authority','Authority to promote friends','Paramedic duties within policy'],2),
 ('Incident reports should use…',['Fictional character details','Real patient charts','Unrelated player gossip'],0),
 ('A debrief belongs…',['In public patient chat','In the private staff area','In another patient ticket'],1)]),
 'nurse': ('Nurse Trainee','Registered Nurse',[],'Nursing',[
 ('Hospital workflow','A new nurse learns hospital workflow even after EMS experience. Check in the character, confirm fictional identity, collect the reason for the visit and route to the assigned provider. Emergency RP follows the city emergency process.'),
 ('Consent & privacy','Explain the proposed RP action and ask permission. Keep fictional records in approved private staff areas. Do not post another patient’s story in the waiting room.'),
 ('Team care & documentation','Document observations and completed RP actions accurately. Notify the assigned provider about changes rather than inventing orders. Give a structured handoff at shift change.')],[
 ('Does paramedic experience skip nursing training?',['Yes always','No, learn the nursing workflow','Only if a friend agrees'],1),
 ('Patient details belong…',['In waiting-room','In screenshots for everyone','In approved private records'],2),
 ('Before an RP action…',['Explain and ask permission','Force a result','Skip consent'],0),
 ('When a character’s condition changes…',['Invent orders','Notify the assigned provider','Delete the report'],1),
 ('Documentation should describe…',['Actions you wish happened','Accurate observations and completed RP actions','Real patient identifiers'],1)]),
 'np': ('NP Trainee','Nurse Practitioner',['Registered Nurse'],'Nursing',[
 ('Provider workflow','Use the city-approved NP scope. Gather fictional history, discuss an RP care plan with the player and refer cases outside your scope. This role is not a real professional credential.'),
 ('Coordination & follow-up','Coordinate with the appropriate specialty and confirm appointment follow-up in the ticket. Do not promise another provider’s availability or guaranteed outcomes.'),
 ('Professional boundaries','Use fictional character information and respect consent. Document the encounter, communicate changes and escalate concerns to the supervising hospital provider.')],[
 ('NP duties are defined by…',['City-approved scope','Any internet tip','Personal preference alone'],0),
 ('Cases outside your scope should be…',['Ignored','Referred to the right provider','Handled by guessing'],1),
 ('Appointment availability should be…',['Guaranteed without checking','Assumed','Confirmed with staff'],2),
 ('The NP role grants…',['An RP role only','A real nursing license','Hospital Director powers'],0),
 ('A care plan should be…',['Discussed with the player','Forced silently','Posted in public'],0)]),
 'resident': ('Physician Trainee','Resident Physician',[],'Physician',[
 ('Beginning the physician track','Moving from nursing or EMS into the physician track requires physician training. Residents work under an attending in hospital RP. Rank alone does not override consent or server rules.'),
 ('Case presentation','Present the character’s concern, fictional observations, approved RP actions, and the question for the attending. Keep information organized and private.'),
 ('Specialty referrals','Family Medicine handles general clinic RP; OB-GYN pregnancy and reproductive RP; Pediatrics child-character RP; Therapy counseling RP; Physical Therapy rehabilitation RP. Route each request to its specialty.')],[
 ('Residents work with…',['An attending supervisor','No supervision','Only spectators'],0),
 ('A case presentation includes…',['Gossip','Concern, observations, actions and question','Only a nickname'],1),
 ('Pregnancy RP is routed to…',['Physical Therapy','Dispatch','OB-GYN'],2),
 ('Rehabilitation RP is routed to…',['Physical Therapy','Human Resources','Pediatrics always'],0),
 ('Changing career tracks means…',['Skipping all training','Taking that track’s training','Receiving a leadership role'],1)]),
 'doctor': ('Doctor Trainee','Attending Physician',['Resident Physician'],'Physician',[
 ('Attending responsibilities','Attending Physicians coordinate clinical RP, supervise residents, and maintain approved hospital procedures. The automatic training ladder stops here. Director, Chief and Department Head roles are assigned manually.'),
 ('Supervision & escalation','Support trainees with clear feedback, preserve player consent, involve the right specialty and escalate organizational concerns to leadership. Never award real-world qualifications.'),
 ('Quality & continuity','Review fictional documentation for accuracy, confirm handoffs and follow-up, and resolve patient concerns privately. Respect the hospital’s policies and city rules.')],[
 ('The highest training promotion is…',['Hospital Director','Attending Physician','Chief of Medicine'],1),
 ('Leadership roles are…',['Automatically awarded after a quiz','Claimed by trainees','Assigned manually'],2),
 ('Supervision should include…',['Clear feedback and consent','Forced RP outcomes','Public embarrassment'],0),
 ('Patient concerns belong…',['In public gossip','In a private appropriate channel','In unrelated tickets'],1),
 ('A training pass is…',['A real license','A hospital RP progression result','Permission to ignore policies'],1)])
}
TRAINEES=[c[0] for c in COURSES.values()]
CLINICAL=['Medical Intern','EMT','Paramedic','Registered Nurse','Nurse Practitioner','Resident Physician','Attending Physician']
PASS_PERCENT=80
RETRY_SECONDS=3600

def connect():
 p=Path(os.getenv('TRAINING_DB','data/training.sqlite3'));p.parent.mkdir(parents=True,exist_ok=True)
 db=sqlite3.connect(p)
 db.execute('CREATE TABLE IF NOT EXISTS enrollments (guild INTEGER, member INTEGER, course TEXT, last_attempt REAL DEFAULT 0, PRIMARY KEY(guild,member))')
 if 'started' not in [r[1] for r in db.execute('PRAGMA table_info(enrollments)')]:
  db.execute('ALTER TABLE enrollments ADD COLUMN started REAL DEFAULT 0')
 db.execute('CREATE TABLE IF NOT EXISTS attempts (guild INTEGER, member INTEGER, course TEXT, score INTEGER, passed INTEGER, time REAL)')
 return db

def enrollment(guild,member):
 with connect() as db:return db.execute('SELECT course,last_attempt FROM enrollments WHERE guild=? AND member=?',(guild,member)).fetchone()
def enroll(guild,member,course):
 with connect() as db:db.execute('INSERT OR REPLACE INTO enrollments (guild,member,course,last_attempt,started) VALUES (?,?,?,0,?)',(guild,member,course,time.time()))
def clear(guild,member):
 with connect() as db:db.execute('DELETE FROM enrollments WHERE guild=? AND member=?',(guild,member))
def attempt(guild,member,course,score,passed,now):
 with connect() as db:
  db.execute('INSERT INTO attempts VALUES (?,?,?,?,?,?)',(guild,member,course,score,int(passed),now))
  db.execute('UPDATE enrollments SET last_attempt=? WHERE guild=? AND member=?',(now,guild,member))
