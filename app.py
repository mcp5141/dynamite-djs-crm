from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response
import sqlite3, os, secrets
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
from functools import wraps

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, 'dynamite_djs.db')
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

PACKAGES = [
    ('Gold', 2400, 'Core professional DJ/MC reception service'),
    ('Platinum', 2700, 'DJ/MC, ceremony sound, static monogram, digital photo booth'),
    ('Diamond', 3100, 'Platinum + highlight video'),
    ('Essentials', 2000, 'Reception-only DJ/MC + sound/music; no premium enhancements'),
]
SOURCES = ['Website','Google','Facebook','Instagram','Referral','Wedding venue','Wedding planner','Past client','WeddingWire','The Knot','Phone call','Email','Other']
LEAD_STATUSES = ['New Inquiry','Contacted','Consultation Scheduled','Consultation Completed','Proposal Sent','Follow-Up','Booked','Lost','Not Qualified']
TASK_PRIORITIES = ['Critical','High','Normal','Low']


def db():
    c=sqlite3.connect(DB)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

def init_db():
    c=db()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'DJ', active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS clients(id INTEGER PRIMARY KEY, first_name TEXT NOT NULL, last_name TEXT NOT NULL, partner_name TEXT, email TEXT, phone TEXT, notes TEXT, internal_notes TEXT, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS leads(id INTEGER PRIMARY KEY, client_id INTEGER, first_name TEXT NOT NULL, last_name TEXT NOT NULL, partner_name TEXT, email TEXT, phone TEXT, event_type TEXT DEFAULT 'Wedding', event_date TEXT, venue TEXT, guest_count INTEGER, budget REAL, package TEXT, source TEXT, message TEXT, notes TEXT, status TEXT NOT NULL DEFAULT 'New Inquiry', consultation_date TEXT, assigned_user_id INTEGER, created_at TEXT NOT NULL, last_contacted TEXT, next_follow_up TEXT, lost_reason TEXT, FOREIGN KEY(client_id) REFERENCES clients(id), FOREIGN KEY(assigned_user_id) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, client_id INTEGER NOT NULL, lead_id INTEGER, event_name TEXT, event_type TEXT DEFAULT 'Wedding', event_date TEXT NOT NULL, venue TEXT, venue_address TEXT, package TEXT, assigned_user_id INTEGER, guest_count INTEGER, planning_status TEXT DEFAULT 'Planning', total REAL DEFAULT 0, paid REAL DEFAULT 0, notes TEXT, created_at TEXT NOT NULL, FOREIGN KEY(client_id) REFERENCES clients(id), FOREIGN KEY(lead_id) REFERENCES leads(id), FOREIGN KEY(assigned_user_id) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, title TEXT NOT NULL, due_date TEXT NOT NULL, priority TEXT DEFAULT 'Normal', status TEXT DEFAULT 'Open', assigned_user_id INTEGER, client_id INTEGER, event_id INTEGER, task_type TEXT, notes TEXT, created_at TEXT NOT NULL, FOREIGN KEY(assigned_user_id) REFERENCES users(id), FOREIGN KEY(client_id) REFERENCES clients(id), FOREIGN KEY(event_id) REFERENCES events(id));
    CREATE TABLE IF NOT EXISTS audit_logs(id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT, entity_type TEXT, entity_id INTEGER, created_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS automation_rules(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, description TEXT, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS automation_runs(id INTEGER PRIMARY KEY, rule_id INTEGER NOT NULL, entity_type TEXT NOT NULL, entity_id INTEGER NOT NULL, run_key TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(rule_id,entity_type,entity_id,run_key), FOREIGN KEY(rule_id) REFERENCES automation_rules(id));
    CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT NOT NULL, message TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'Normal', entity_type TEXT, entity_id INTEGER, read INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS add_ons(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, price REAL NOT NULL DEFAULT 0, description TEXT, active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS quotes(id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'Draft', package TEXT, subtotal REAL NOT NULL DEFAULT 0, discount REAL NOT NULL DEFAULT 0, tax REAL NOT NULL DEFAULT 0, total REAL NOT NULL DEFAULT 0, retainer REAL NOT NULL DEFAULT 250, notes TEXT, created_at TEXT NOT NULL, sent_at TEXT, viewed_at TEXT, FOREIGN KEY(event_id) REFERENCES events(id));
    CREATE TABLE IF NOT EXISTS quote_items(id INTEGER PRIMARY KEY, quote_id INTEGER NOT NULL, item_type TEXT NOT NULL, item_id INTEGER, name TEXT NOT NULL, quantity REAL NOT NULL DEFAULT 1, unit_price REAL NOT NULL DEFAULT 0, total REAL NOT NULL DEFAULT 0, FOREIGN KEY(quote_id) REFERENCES quotes(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS contracts(id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL, quote_id INTEGER, name TEXT NOT NULL DEFAULT 'Dynamite DJs Service Agreement', status TEXT NOT NULL DEFAULT 'Created', sent_at TEXT, viewed_at TEXT, signed_at TEXT, declined_at TEXT, expires_at TEXT, content TEXT, FOREIGN KEY(event_id) REFERENCES events(id), FOREIGN KEY(quote_id) REFERENCES quotes(id));
    CREATE TABLE IF NOT EXISTS invoices(id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL, quote_id INTEGER, invoice_number TEXT UNIQUE NOT NULL, total REAL NOT NULL DEFAULT 0, due_date TEXT, status TEXT NOT NULL DEFAULT 'Due', created_at TEXT NOT NULL, FOREIGN KEY(event_id) REFERENCES events(id), FOREIGN KEY(quote_id) REFERENCES quotes(id));
    CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL, invoice_id INTEGER, amount REAL NOT NULL, payment_date TEXT NOT NULL, method TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Paid', reference TEXT, notes TEXT, created_at TEXT NOT NULL, FOREIGN KEY(event_id) REFERENCES events(id), FOREIGN KEY(invoice_id) REFERENCES invoices(id));
    CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY, client_id INTEGER, event_id INTEGER, name TEXT NOT NULL, doc_type TEXT NOT NULL DEFAULT 'Other', status TEXT NOT NULL DEFAULT 'Created', file_name TEXT, content TEXT, created_at TEXT NOT NULL, sent_at TEXT, viewed_at TEXT, signed_at TEXT, FOREIGN KEY(client_id) REFERENCES clients(id), FOREIGN KEY(event_id) REFERENCES events(id));
    CREATE TABLE IF NOT EXISTS questionnaires(id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Draft', due_date TEXT, token TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL, completed_at TEXT, FOREIGN KEY(event_id) REFERENCES events(id));
    CREATE TABLE IF NOT EXISTS questionnaire_questions(id INTEGER PRIMARY KEY, questionnaire_id INTEGER NOT NULL, label TEXT NOT NULL, field_type TEXT NOT NULL DEFAULT 'short', options TEXT, required INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 0, FOREIGN KEY(questionnaire_id) REFERENCES questionnaires(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS questionnaire_answers(id INTEGER PRIMARY KEY, question_id INTEGER NOT NULL, questionnaire_id INTEGER NOT NULL, answer TEXT, updated_at TEXT NOT NULL, UNIQUE(question_id,questionnaire_id), FOREIGN KEY(question_id) REFERENCES questionnaire_questions(id) ON DELETE CASCADE, FOREIGN KEY(questionnaire_id) REFERENCES questionnaires(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS communications(id INTEGER PRIMARY KEY, client_id INTEGER, event_id INTEGER, lead_id INTEGER, type TEXT NOT NULL, direction TEXT DEFAULT 'Internal', subject TEXT, message TEXT NOT NULL, user_id INTEGER, created_at TEXT NOT NULL, FOREIGN KEY(client_id) REFERENCES clients(id), FOREIGN KEY(event_id) REFERENCES events(id), FOREIGN KEY(lead_id) REFERENCES leads(id), FOREIGN KEY(user_id) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS review_requests(id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL, channel TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Not requested', requested_at TEXT, completed_at TEXT, FOREIGN KEY(event_id) REFERENCES events(id));
    CREATE TABLE IF NOT EXISTS timeline_items(id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL, title TEXT NOT NULL, start_time TEXT, duration INTEGER, description TEXT, person_responsible TEXT, music TEXT, mc_notes TEXT, special_instructions TEXT, sort_order INTEGER NOT NULL DEFAULT 0, FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS songs(id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL, category TEXT NOT NULL DEFAULT 'Dancing', title TEXT NOT NULL, artist TEXT, notes TEXT, timing TEXT, special_edit TEXT, requested_by TEXT, status TEXT NOT NULL DEFAULT 'Requested', sort_order INTEGER NOT NULL DEFAULT 0, FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS event_planning(id INTEGER PRIMARY KEY, event_id INTEGER UNIQUE NOT NULL, ceremony_location TEXT, ceremony_time TEXT, cocktail_time TEXT, reception_time TEXT, guest_arrival_time TEXT, grand_entrance_time TEXT, first_dance TEXT, parent_dances TEXT, announcements TEXT, traditions TEXT, vendor_info TEXT, day_of_contact TEXT, emergency_contact TEXT, ceremony_notes TEXT, reception_notes TEXT, genres TEXT, special_instructions TEXT, FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS equipment_checklist(id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL, item TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'General', checked INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 0, FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE);
    ''')
    if c.execute('SELECT COUNT(*) n FROM users').fetchone()['n']==0:
        c.execute('INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)',('Marcus Pettenati','admin@dynamitedjs.com',generate_password_hash('dynamite2026'),'Admin'))
        c.execute('INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)',('Nick Pettenati','nick@dynamitedjs.com',generate_password_hash('dynamite2026'),'DJ'))
    for name,price,desc in PACKAGES:
        c.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)',(f'package:{name}',str(price)))
    addons=[('Ceremony Sound',200,'Ceremony sound reinforcement'),('Digital Photo Booth',400,'Reception digital booth'),('Static Monogram',150,'Static custom monogram'),('Animated Monogram',200,'Animated custom monogram'),('Highlight Video',400,'Event highlight video'),('Additional Wireless Mic',100,'Additional wireless microphone')]
    for n,p,d in addons: c.execute('INSERT OR IGNORE INTO add_ons(name,price,description) VALUES(?,?,?)',(n,p,d))
    rules=[
      ('New inquiry follow-up','Create a follow-up task when a new inquiry has not been contacted within 24 hours.'),
      ('Proposal follow-up 1','Create a follow-up task 3 days after a proposal is sent.'),
      ('Proposal follow-up 2','Create a second follow-up task 7 days after a proposal is sent.'),
      ('Proposal final follow-up','Create a final follow-up task 14 days after a proposal is sent.'),
      ('Booked welcome workflow','Create a welcome task and planning questionnaire around 90 days before a booked event.'),
      ('30-day planning','Create a final planning task 30 days before an event.'),
      ('7-day final confirmation','Create a final confirmation task 7 days before an event.'),
      ('Payment reminders','Create payment reminder tasks 60, 30 and 14 days before payment due dates, plus overdue alerts.'),
      ('Completed event review','Create a review request and thank-you task when an event is marked completed.')]
    for n,d in rules: c.execute('INSERT OR IGNORE INTO automation_rules(name,description,created_at) VALUES(?,?,?)',(n,d,datetime.now().isoformat(timespec='seconds')))
    c.execute("CREATE TABLE IF NOT EXISTS integration_settings(id INTEGER PRIMARY KEY, provider TEXT UNIQUE NOT NULL, enabled INTEGER NOT NULL DEFAULT 0, config TEXT, updated_at TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS webhook_events(id INTEGER PRIMARY KEY, provider TEXT NOT NULL, event_type TEXT, payload TEXT, status TEXT NOT NULL DEFAULT 'Received', created_at TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS public_inquiries(id INTEGER PRIMARY KEY, lead_id INTEGER, ip_hash TEXT, user_agent TEXT, created_at TEXT NOT NULL, FOREIGN KEY(lead_id) REFERENCES leads(id))")
    c.commit(); c.close()

init_db()


def automation_enabled(c,name):
    r=c.execute('SELECT enabled FROM automation_rules WHERE name=?',(name,)).fetchone()
    return bool(r and r['enabled'])

def notify(c,user_id,title,message,severity='Normal',etype=None,eid=None):
    c.execute('INSERT INTO notifications(user_id,title,message,severity,entity_type,entity_id,created_at) VALUES(?,?,?,?,?,?,?)',(user_id,title,message,severity,etype,eid,datetime.now().isoformat(timespec='seconds')))

def automation_task(c,rule_name,entity_type,entity_id,run_key,title,due_date,priority='Normal',user_id=None,client_id=None,event_id=None,task_type='Automation',notes=''):
    r=c.execute('SELECT id FROM automation_rules WHERE name=? AND enabled=1',(rule_name,)).fetchone()
    if not r: return False
    exists=c.execute('SELECT 1 FROM automation_runs WHERE rule_id=? AND entity_type=? AND entity_id=? AND run_key=?',(r['id'],entity_type,entity_id,run_key)).fetchone()
    if exists: return False
    c.execute('INSERT INTO tasks(title,due_date,priority,status,assigned_user_id,client_id,event_id,task_type,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(title,due_date,priority,user_id,client_id,event_id,task_type,notes,datetime.now().isoformat(timespec='seconds')))
    c.execute('INSERT INTO automation_runs(rule_id,entity_type,entity_id,run_key,created_at) VALUES(?,?,?,?,?)',(r['id'],entity_type,entity_id,run_key,datetime.now().isoformat(timespec='seconds')))
    return True

def run_automations():
    c=db(); today=date.today()
    users=c.execute('SELECT id FROM users WHERE active=1').fetchall(); default_user=users[0]['id'] if users else None
    created=0
    # Lead follow-ups
    leads=c.execute("SELECT * FROM leads WHERE status NOT IN ('Booked','Lost','Not Qualified')").fetchall()
    for l in leads:
        if automation_enabled(c,'New inquiry follow-up') and l['status']=='New Inquiry' and l['created_at']:
            age=(datetime.now()-datetime.fromisoformat(l['created_at'])).total_seconds()/86400
            if age>=1:
                due=today.isoformat();
                if automation_task(c,'New inquiry follow-up','Lead',l['id'],'24h',f"Contact {l['first_name']} {l['last_name']} — new inquiry",due,'Normal',l['assigned_user_id'] or default_user,l['client_id'],None,'Lead Follow-up','New inquiry has not been contacted within 24 hours.'): created+=1
        # Proposal timing is based on sent_at when a quote exists
        q=c.execute("SELECT * FROM quotes WHERE event_id IN (SELECT id FROM events WHERE lead_id=?) AND status='Sent' ORDER BY sent_at DESC LIMIT 1",(l['id'],)).fetchone()
        if q and q['sent_at']:
            age=(datetime.now()-datetime.fromisoformat(q['sent_at'])).days
            for days,label in [(3,'1'),(7,'2'),(14,'Final')]:
                if age>=days:
                    due=(datetime.fromisoformat(q['sent_at'])+timedelta(days=days)).date().isoformat()
                    if automation_task(c,f"Proposal follow-up {label if label!='Final' else 'final'}" if label!='Final' else 'Proposal final follow-up','Lead',l['id'],f'proposal-{days}',f"Proposal follow-up — {l['first_name']} {l['last_name']}",due,'Normal',l['assigned_user_id'] or default_user,l['client_id'],None,'Proposal Follow-up',f'Proposal was sent {days} days ago and has not been marked booked.'): created+=1
    # Booked events and milestones
    events=c.execute("SELECT e.*,c.first_name,c.last_name FROM events e JOIN clients c ON c.id=e.client_id WHERE e.event_date>=?",(today.isoformat(),)).fetchall()
    for e in events:
        event_date=date.fromisoformat(e['event_date'])
        days=(event_date-today).days
        assignee=e['assigned_user_id'] or default_user
        if automation_enabled(c,'Booked welcome workflow') and days<=90:
            if automation_task(c,'Booked welcome workflow','Event',e['id'],'welcome',f"Welcome & onboarding — {e['first_name']} {e['last_name']}",today.isoformat(),'Normal',assignee,e['client_id'],e['id'],'Booking','Booked event onboarding.'): created+=1
            if not c.execute('SELECT 1 FROM questionnaires WHERE event_id=?',(e['id'],)).fetchone():
                token=secrets.token_urlsafe(24); due=(event_date-timedelta(days=30)).isoformat()
                c.execute('INSERT INTO questionnaires(event_id,title,status,due_date,token,created_at) VALUES(?,?,?,?,?,?)',(e['id'],'Wedding Planning Questionnaire','Draft',due,token,datetime.now().isoformat(timespec='seconds')))
                qid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']
                defaults=['Couple names','Ceremony location','Ceremony time','Reception time','Guest count','Grand entrance','First dance','Parent dances','Must Play songs','Do Not Play songs','Genres / music preferences','Announcements','Traditions','Vendor information','Day-of contact','Emergency contact','Special instructions']
                for i,label in enumerate(defaults):
                    ftype='long' if label in ['Must Play songs','Do Not Play songs','Vendor information','Special instructions'] else 'short'
                    c.execute('INSERT INTO questionnaire_questions(questionnaire_id,label,field_type,required,sort_order) VALUES(?,?,?,?,?)',(qid,label,ftype,0,i))
                notify(c,assignee,'Questionnaire created',f'A planning questionnaire was created for {e["first_name"]} {e["last_name"]}.','Normal','Event',e['id'])
        if days<=30 and days>=0 and automation_enabled(c,'30-day planning'):
            if automation_task(c,'30-day planning','Event',e['id'],'30d',f"30-day final planning — {e['first_name']} {e['last_name']}",event_date.isoformat(),'High',assignee,e['client_id'],e['id'],'Planning','Review questionnaire, timeline, music and vendor details.'): created+=1
        if days<=7 and days>=0 and automation_enabled(c,'7-day final confirmation'):
            if automation_task(c,'7-day final confirmation','Event',e['id'],'7d',f"Final confirmation — {e['first_name']} {e['last_name']}",event_date.isoformat(),'High',assignee,e['client_id'],e['id'],'Final Confirmation','Confirm venue, timeline, ceremony, reception, equipment and client details.'): created+=1
    # Payment reminders from invoices
    if automation_enabled(c,'Payment reminders'):
        invoices=c.execute("SELECT i.*,e.client_id,e.assigned_user_id,e.event_date,c.first_name,c.last_name FROM invoices i JOIN events e ON e.id=i.event_id JOIN clients c ON c.id=e.client_id WHERE i.due_date IS NOT NULL AND i.status!='Paid'").fetchall()
        for inv in invoices:
            due=date.fromisoformat(inv['due_date']); delta=(due-today).days; assignee=inv['assigned_user_id'] or default_user
            if delta in (60,30,14):
                if automation_task(c,'Payment reminders','Invoice',inv['id'],f'{delta}d',f"Payment due in {delta} days — {inv['first_name']} {inv['last_name']}",today.isoformat(),'High',assignee,inv['client_id'],inv['event_id'],'Payment Reminder',f'Invoice {inv["invoice_number"]} is due {inv["due_date"]}.'): created+=1
            if delta<0:
                if automation_task(c,'Payment reminders','Invoice',inv['id'],'overdue',f"Payment overdue — {inv['first_name']} {inv['last_name']}",today.isoformat(),'High',assignee,inv['client_id'],inv['event_id'],'Payment Reminder',f'Invoice {inv["invoice_number"]} is overdue.'): created+=1
    # Completed events
    completed=c.execute("SELECT e.*,c.first_name,c.last_name FROM events e JOIN clients c ON c.id=e.client_id WHERE e.planning_status='Completed'").fetchall()
    for e in completed:
        assignee=e['assigned_user_id'] or default_user
        if automation_enabled(c,'Completed event review'):
            if automation_task(c,'Completed event review','Event',e['id'],'thank-you',f"Send thank-you — {e['first_name']} {e['last_name']}",today.isoformat(),'Normal',assignee,e['client_id'],e['id'],'Review','Thank the client and invite feedback/review.'): created+=1
            if not c.execute("SELECT 1 FROM review_requests WHERE event_id=?",(e['id'],)).fetchone():
                c.execute("INSERT INTO review_requests(event_id,channel,status) VALUES(?,?,?)",(e['id'],'Google','Not requested'))
                notify(c,assignee,'Review request ready',f'Review request is ready for {e["first_name"]} {e["last_name"]}.','Normal','Event',e['id'])
    # Due/overdue notifications for open tasks
    due_tasks=c.execute("SELECT t.*,u.id uid FROM tasks t LEFT JOIN users u ON u.id=t.assigned_user_id WHERE t.status!='Done' AND t.due_date<=?",(today.isoformat(),)).fetchall()
    for t in due_tasks:
        if t['uid']:
            exists=c.execute("SELECT 1 FROM notifications WHERE user_id=? AND entity_type='Task' AND entity_id=? AND date(created_at)=date('now')",(t['uid'],t['id'])).fetchone()
            if not exists: notify(c,t['uid'],'Task due',t['title'],'High' if t['due_date']<today.isoformat() else 'Normal','Task',t['id'])
    c.commit(); c.close(); return created

def login_required(f):
    @wraps(f)
    def wrap(*a,**kw):
        if 'user_id' not in session: return redirect(url_for('login'))
        return f(*a,**kw)
    return wrap

def current_user():
    if 'user_id' not in session: return None
    c=db(); u=c.execute('SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone(); c.close(); return u
@app.context_processor
def inject(): return {'current_user':current_user(), 'today':date.today().isoformat()}

def audit(action,etype,eid=None):
    if 'user_id' not in session:return
    c=db(); c.execute('INSERT INTO audit_logs(user_id,action,entity_type,entity_id,created_at) VALUES(?,?,?,?,?)',(session['user_id'],action,etype,eid,datetime.now().isoformat(timespec='seconds'))); c.commit(); c.close()

def package_price(name):
    c=db(); r=c.execute('SELECT value FROM settings WHERE key=?',(f'package:{name}',)).fetchone(); c.close(); return float(r['value']) if r else 0

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        c=db(); u=c.execute('SELECT * FROM users WHERE email=? AND active=1',(request.form['email'].strip().lower(),)).fetchone(); c.close()
        valid = bool(u and (check_password_hash(u['password'],request.form['password']) if (u['password'].startswith('scrypt:') or u['password'].startswith('pbkdf2:')) else u['password']==request.form['password']))
        if valid: session['user_id']=u['id']; return redirect(url_for('dashboard'))
        flash('Invalid email or password.','error')
    return render_template('login.html')
@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    run_automations()
    c=db(); today=date.today().isoformat(); soon=(date.today()+timedelta(days=30)).isoformat()
    stats={
      'new_leads':c.execute("SELECT COUNT(*) n FROM leads WHERE status='New Inquiry'").fetchone()['n'],
      'followups':c.execute("SELECT COUNT(*) n FROM leads WHERE next_follow_up IS NOT NULL AND next_follow_up<=? AND status NOT IN ('Booked','Lost','Not Qualified')",(today,)).fetchone()['n'],
      'upcoming':c.execute('SELECT COUNT(*) n FROM events WHERE event_date>=?',(today,)).fetchone()['n'],
      'month':c.execute("SELECT COUNT(*) n FROM events WHERE substr(event_date,1,7)=?",(today[:7],)).fetchone()['n'],
      'outstanding':c.execute('SELECT COALESCE(SUM(total-paid),0) n FROM events').fetchone()['n'],
      'tasks':c.execute("SELECT COUNT(*) n FROM tasks WHERE status!='Done' AND due_date<=?",(today,)).fetchone()['n'],
    }
    upcoming=c.execute('''SELECT e.*, c.first_name,c.last_name,u.name dj FROM events e JOIN clients c ON c.id=e.client_id LEFT JOIN users u ON u.id=e.assigned_user_id WHERE e.event_date>=? ORDER BY e.event_date LIMIT 8''',(today,)).fetchall()
    recent=c.execute('SELECT * FROM leads ORDER BY id DESC LIMIT 6').fetchall(); c.close()
    return render_template('dashboard.html',stats=stats,upcoming=upcoming,recent=recent)

@app.route('/leads')
@login_required
def leads():
    q=request.args.get('q','').strip(); status=request.args.get('status','')
    c=db(); sql='SELECT l.*,u.name assignee FROM leads l LEFT JOIN users u ON u.id=l.assigned_user_id WHERE 1=1'; args=[]
    if q: sql += ' AND (l.first_name||" "||l.last_name LIKE ? OR l.email LIKE ? OR l.phone LIKE ? OR l.venue LIKE ?)'; args += [f'%{q}%']*4
    if status: sql+=' AND l.status=?'; args.append(status)
    rows=c.execute(sql+' ORDER BY l.id DESC',args).fetchall(); c.close(); return render_template('leads.html',rows=rows,statuses=LEAD_STATUSES)
@app.route('/leads/new',methods=['GET','POST'])
@login_required
def new_lead():
    if request.method=='POST':
        c=db(); f=request.form
        c.execute('''INSERT INTO leads(first_name,last_name,partner_name,email,phone,event_type,event_date,venue,guest_count,budget,package,source,message,notes,status,assigned_user_id,created_at,next_follow_up) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
          (f['first_name'],f['last_name'],f.get('partner_name'),f.get('email'),f.get('phone'),f.get('event_type','Wedding'),f.get('event_date') or None,f.get('venue'),int(f['guest_count']) if f.get('guest_count') else None,float(f['budget']) if f.get('budget') else None,f.get('package'),f.get('source'),f.get('message'),f.get('notes'),'New Inquiry',int(f['assigned_user_id']) if f.get('assigned_user_id') else None,datetime.now().isoformat(timespec='seconds'),(date.today()+timedelta(days=1)).isoformat()))
        lid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']; c.commit(); c.close(); audit('Created lead','Lead',lid); flash('Lead created.','success'); return redirect(url_for('leads'))
    c=db(); users=c.execute('SELECT id,name FROM users WHERE active=1').fetchall(); c.close(); return render_template('lead_form.html',users=users,lead=None,sources=SOURCES,packages=[p[0] for p in PACKAGES])
@app.route('/leads/<int:lid>',methods=['GET','POST'])
@login_required
def lead_detail(lid):
    c=db();
    if request.method=='POST':
        f=request.form
        c.execute('''UPDATE leads SET first_name=?,last_name=?,partner_name=?,email=?,phone=?,event_type=?,event_date=?,venue=?,guest_count=?,budget=?,package=?,source=?,notes=?,status=?,consultation_date=?,assigned_user_id=?,last_contacted=?,next_follow_up=?,lost_reason=? WHERE id=?''',
         (f['first_name'],f['last_name'],f.get('partner_name'),f.get('email'),f.get('phone'),f.get('event_type'),f.get('event_date') or None,f.get('venue'),int(f['guest_count']) if f.get('guest_count') else None,float(f['budget']) if f.get('budget') else None,f.get('package'),f.get('source'),f.get('notes'),f.get('status'),f.get('consultation_date') or None,int(f['assigned_user_id']) if f.get('assigned_user_id') else None,f.get('last_contacted') or None,f.get('next_follow_up') or None,f.get('lost_reason'),lid)); c.commit(); c.close(); audit('Updated lead','Lead',lid); flash('Lead updated.','success'); return redirect(url_for('lead_detail',lid=lid))
    row=c.execute('SELECT * FROM leads WHERE id=?',(lid,)).fetchone(); users=c.execute('SELECT id,name FROM users WHERE active=1').fetchall(); c.close()
    if not row:return 'Not found',404
    return render_template('lead_form.html',lead=row,users=users,sources=SOURCES,packages=[p[0] for p in PACKAGES])

@app.route('/clients')
@login_required
def clients():
    q=request.args.get('q','').strip(); c=db();
    if q: rows=c.execute('SELECT * FROM clients WHERE first_name||" "||last_name LIKE ? OR email LIKE ? OR phone LIKE ? ORDER BY last_name',(f'%{q}%',f'%{q}%',f'%{q}%')).fetchall()
    else: rows=c.execute('SELECT * FROM clients ORDER BY id DESC').fetchall()
    c.close(); return render_template('clients.html',rows=rows)
@app.route('/clients/new',methods=['GET','POST'])
@login_required
def new_client():
    if request.method=='POST':
        f=request.form; c=db(); c.execute('INSERT INTO clients(first_name,last_name,partner_name,email,phone,notes,internal_notes,created_at) VALUES(?,?,?,?,?,?,?,?)',(f['first_name'],f['last_name'],f.get('partner_name'),f.get('email'),f.get('phone'),f.get('notes'),f.get('internal_notes'),datetime.now().isoformat(timespec='seconds'))); cid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']; c.commit(); c.close(); audit('Created client','Client',cid); flash('Client created.','success'); return redirect(url_for('clients'))
    return render_template('client_form.html',client=None)
@app.route('/clients/<int:cid>')
@login_required
def client_detail(cid):
    c=db(); client=c.execute('SELECT * FROM clients WHERE id=?',(cid,)).fetchone(); events=c.execute('SELECT e.*,u.name dj FROM events e LEFT JOIN users u ON u.id=e.assigned_user_id WHERE client_id=? ORDER BY event_date',(cid,)).fetchall(); leads=c.execute('SELECT * FROM leads WHERE client_id=? ORDER BY id DESC',(cid,)).fetchall(); c.close(); return render_template('client_detail.html',client=client,events=events,leads=leads)

@app.route('/events')
@login_required
def events():
    q=request.args.get('q','').strip(); c=db(); sql='''SELECT e.*,c.first_name,c.last_name,u.name dj FROM events e JOIN clients c ON c.id=e.client_id LEFT JOIN users u ON u.id=e.assigned_user_id WHERE 1=1'''; args=[]
    if q: sql+=' AND (c.first_name||" "||c.last_name LIKE ? OR e.venue LIKE ? OR e.event_date LIKE ?)'; args += [f'%{q}%']*3
    rows=c.execute(sql+' ORDER BY event_date',args).fetchall(); c.close(); return render_template('events.html',rows=rows)
@app.route('/events/new',methods=['GET','POST'])
@login_required
def new_event():
    c=db()
    if request.method=='POST':
        f=request.form; cid=int(f['client_id']); pkg=f.get('package'); total=float(f.get('total') or package_price(pkg));
        c.execute('INSERT INTO events(client_id,event_name,event_type,event_date,venue,venue_address,package,assigned_user_id,guest_count,planning_status,total,paid,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(cid,f.get('event_name'),f.get('event_type','Wedding'),f['event_date'],f.get('venue'),f.get('venue_address'),pkg,int(f['assigned_user_id']) if f.get('assigned_user_id') else None,int(f['guest_count']) if f.get('guest_count') else None,f.get('planning_status','Planning'),total,float(f.get('paid') or 0),f.get('notes'),datetime.now().isoformat(timespec='seconds'))); eid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']; c.commit(); c.close(); audit('Created event','Event',eid); flash('Event created.','success'); return redirect(url_for('event_detail',eid=eid))
    clients=c.execute('SELECT id,first_name,last_name,partner_name FROM clients ORDER BY last_name').fetchall(); users=c.execute('SELECT id,name FROM users WHERE active=1').fetchall(); c.close(); return render_template('event_form.html',clients=clients,users=users,packages=[p[0] for p in PACKAGES],prices={p[0]:p[1] for p in PACKAGES})
@app.route('/events/<int:eid>')
@login_required
def event_detail(eid):
    c=db(); e=c.execute('''SELECT e.*,c.first_name,c.last_name,c.partner_name,c.email,c.phone,u.name dj FROM events e JOIN clients c ON c.id=e.client_id LEFT JOIN users u ON u.id=e.assigned_user_id WHERE e.id=?''',(eid,)).fetchone(); tasks=c.execute('SELECT t.*,u.name assignee FROM tasks t LEFT JOIN users u ON u.id=t.assigned_user_id WHERE event_id=? ORDER BY due_date',(eid,)).fetchall(); c.close();
    if not e:return 'Not found',404
    return render_template('event_detail.html',event=e,tasks=tasks)

@app.route('/tasks',methods=['GET','POST'])
@login_required
def tasks():
    c=db()
    if request.method=='POST':
        f=request.form; c.execute('INSERT INTO tasks(title,due_date,priority,status,assigned_user_id,task_type,notes,created_at) VALUES(?,?,?,?,?,?,?,?)',(f['title'],f['due_date'],f.get('priority','Normal'),'Open',int(f['assigned_user_id']) if f.get('assigned_user_id') else None,f.get('task_type'),f.get('notes'),datetime.now().isoformat(timespec='seconds'))); tid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']; c.commit(); c.close(); audit('Created task','Task',tid); flash('Task created.','success'); return redirect(url_for('tasks'))
    rows=c.execute('SELECT t.*,u.name assignee FROM tasks t LEFT JOIN users u ON u.id=t.assigned_user_id ORDER BY CASE status WHEN "Open" THEN 0 ELSE 1 END,due_date').fetchall(); users=c.execute('SELECT id,name FROM users WHERE active=1').fetchall(); c.close(); return render_template('tasks.html',rows=rows,users=users,priorities=TASK_PRIORITIES)
@app.post('/tasks/<int:tid>/toggle')
@login_required
def toggle_task(tid):
    c=db(); c.execute("UPDATE tasks SET status=CASE WHEN status='Done' THEN 'Open' ELSE 'Done' END WHERE id=?",(tid,)); c.commit(); c.close(); audit('Toggled task','Task',tid); return redirect(request.referrer or url_for('tasks'))

@app.route('/calendar')
@login_required
def calendar():
    c=db(); rows=c.execute('SELECT e.*,c.first_name,c.last_name FROM events e JOIN clients c ON c.id=e.client_id ORDER BY event_date').fetchall(); c.close(); return render_template('calendar.html',rows=rows)
@app.route('/packages')
@login_required
def packages():
    c=db(); rows=[dict(name=n,price=float(c.execute('SELECT value FROM settings WHERE key=?',(f'package:{n}',)).fetchone()['value']),desc=d) for n,p,d in PACKAGES]; c.close(); return render_template('packages.html',rows=rows)
@app.route('/team')
@login_required
def team():
    c=db(); rows=c.execute('SELECT id,name,email,role,active FROM users ORDER BY name').fetchall(); c.close(); return render_template('team.html',rows=rows)
@app.route('/search')
@login_required
def search():
    q=request.args.get('q','').strip(); c=db(); leads=c.execute('SELECT id,first_name,last_name,email,venue,event_date FROM leads WHERE first_name||" "||last_name LIKE ? OR email LIKE ? OR phone LIKE ? OR venue LIKE ? LIMIT 10',(f'%{q}%',)*4).fetchall(); clients=c.execute('SELECT id,first_name,last_name,email,phone FROM clients WHERE first_name||" "||last_name LIKE ? OR email LIKE ? OR phone LIKE ? LIMIT 10',(f'%{q}%',)*3).fetchall(); events=c.execute('SELECT e.id,e.event_date,e.venue,c.first_name,c.last_name FROM events e JOIN clients c ON c.id=e.client_id WHERE e.event_date LIKE ? OR e.venue LIKE ? OR c.first_name||" "||c.last_name LIKE ? LIMIT 10',(f'%{q}%',)*3).fetchall(); c.close(); return render_template('search.html',q=q,leads=leads,clients=clients,events=events)


def recalc_quote(c,qid):
    subtotal=float(c.execute('SELECT COALESCE(SUM(total),0) n FROM quote_items WHERE quote_id=?',(qid,)).fetchone()['n'] or 0)
    q=c.execute('SELECT discount,tax FROM quotes WHERE id=?',(qid,)).fetchone()
    total=max(0,subtotal-float(q['discount'] or 0)+float(q['tax'] or 0))
    c.execute('UPDATE quotes SET subtotal=?,total=? WHERE id=?',(subtotal,total,qid)); return subtotal,total

def sync_event(c,eid):
    paid=float(c.execute("SELECT COALESCE(SUM(amount),0) n FROM payments WHERE event_id=? AND status='Paid'",(eid,)).fetchone()['n'] or 0)
    q=c.execute("SELECT total FROM quotes WHERE event_id=? AND status NOT IN ('Declined','Expired') ORDER BY id DESC LIMIT 1",(eid,)).fetchone()
    total=float(q['total']) if q else float(c.execute('SELECT total FROM events WHERE id=?',(eid,)).fetchone()['total'] or 0)
    c.execute('UPDATE events SET total=?,paid=? WHERE id=?',(total,paid,eid))
    return total,paid

@app.route('/quotes')
@login_required
def quotes():
    c=db(); rows=c.execute("""SELECT q.*,e.event_date,c.first_name,c.last_name FROM quotes q JOIN events e ON e.id=q.event_id JOIN clients c ON c.id=e.client_id ORDER BY q.id DESC""").fetchall(); c.close(); return render_template('quotes.html',rows=rows)

@app.route('/events/<int:eid>/quote/new',methods=['GET','POST'])
@login_required
def new_quote(eid):
    c=db(); event=c.execute('SELECT * FROM events WHERE id=?',(eid,)).fetchone()
    if not event:return 'Not found',404
    addons=c.execute('SELECT * FROM add_ons WHERE active=1 ORDER BY name').fetchall()
    if request.method=='POST':
        f=request.form; pkg=f.get('package') or event['package']; ret=float(f.get('retainer') or 250); disc=float(f.get('discount') or 0); tax=float(f.get('tax') or 0)
        c.execute('INSERT INTO quotes(event_id,status,package,discount,tax,retainer,notes,created_at) VALUES(?,?,?,?,?,?,?,?)',(eid,'Draft',pkg,disc,tax,ret,f.get('notes'),datetime.now().isoformat(timespec='seconds'))); qid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']
        pp=package_price(pkg); c.execute('INSERT INTO quote_items(quote_id,item_type,name,quantity,unit_price,total) VALUES(?,?,?,?,?,?)',(qid,'Package',pkg,1,pp,pp))
        for aid in f.getlist('addons'):
            a=c.execute('SELECT * FROM add_ons WHERE id=?',(aid,)).fetchone()
            if a:c.execute('INSERT INTO quote_items(quote_id,item_type,item_id,name,quantity,unit_price,total) VALUES(?,?,?,?,?,?,?)',(qid,'AddOn',a['id'],a['name'],1,a['price'],a['price']))
        _,total=recalc_quote(c,qid); c.execute('UPDATE events SET package=?,total=? WHERE id=?',(pkg,total,eid)); c.commit(); c.close(); audit('Created quote','Quote',qid); return redirect(url_for('quote_detail',qid=qid))
    c.close(); return render_template('quote_form.html',event=event,addons=addons,packages=[p[0] for p in PACKAGES],prices={p[0]:p[1] for p in PACKAGES})

@app.route('/quotes/<int:qid>',methods=['GET','POST'])
@login_required
def quote_detail(qid):
    c=db(); q=c.execute("""SELECT q.*,e.id eid,e.event_date,e.venue,c.first_name,c.last_name,c.partner_name,c.email FROM quotes q JOIN events e ON e.id=q.event_id JOIN clients c ON c.id=e.client_id WHERE q.id=?""",(qid,)).fetchone()
    if not q:return 'Not found',404
    if request.method=='POST':
        f=request.form; c.execute('UPDATE quotes SET status=?,discount=?,tax=?,retainer=?,notes=? WHERE id=?',(f.get('status'),float(f.get('discount') or 0),float(f.get('tax') or 0),float(f.get('retainer') or 250),f.get('notes'),qid)); _,total=recalc_quote(c,qid); c.execute('UPDATE events SET total=? WHERE id=?',(total,q['eid'])); c.commit(); c.close(); audit('Updated quote','Quote',qid); return redirect(url_for('quote_detail',qid=qid))
    items=c.execute('SELECT * FROM quote_items WHERE quote_id=?',(qid,)).fetchall(); c.close(); return render_template('quote_detail.html',q=q,items=items)

@app.post('/quotes/<int:qid>/send')
@login_required
def send_quote(qid):
    c=db(); c.execute("UPDATE quotes SET status='Sent',sent_at=? WHERE id=?",(datetime.now().isoformat(timespec='seconds'),qid)); c.commit(); c.close(); audit('Sent quote','Quote',qid); return redirect(url_for('quote_detail',qid=qid))

@app.route('/contracts')
@login_required
def contracts():
    c=db(); rows=c.execute("""SELECT ct.*,e.event_date,c.first_name,c.last_name FROM contracts ct JOIN events e ON e.id=ct.event_id JOIN clients c ON c.id=e.client_id ORDER BY ct.id DESC""").fetchall(); c.close(); return render_template('contracts.html',rows=rows)

@app.route('/events/<int:eid>/contract/new',methods=['GET','POST'])
@login_required
def new_contract(eid):
    c=db(); e=c.execute("SELECT e.*,c.first_name,c.last_name,c.partner_name FROM events e JOIN clients c ON c.id=e.client_id WHERE e.id=?",(eid,)).fetchone(); q=c.execute('SELECT * FROM quotes WHERE event_id=? ORDER BY id DESC LIMIT 1',(eid,)).fetchone()
    if request.method=='POST':
        f=request.form; c.execute('INSERT INTO contracts(event_id,quote_id,name,status,expires_at,content) VALUES(?,?,?,?,?,?)',(eid,q['id'] if q else None,f.get('name') or 'Dynamite DJs Service Agreement',f.get('status','Created'),f.get('expires_at') or None,f.get('content'))); cid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']; c.commit(); c.close(); audit('Created contract','Contract',cid); return redirect(url_for('contract_detail',cid=cid))
    c.close(); return render_template('contract_form.html',event=e,quote=q)

@app.route('/contracts/<int:cid>',methods=['GET','POST'])
@login_required
def contract_detail(cid):
    c=db(); ct=c.execute("""SELECT ct.*,e.event_date,c.first_name,c.last_name,c.partner_name,c.email FROM contracts ct JOIN events e ON e.id=ct.event_id JOIN clients c ON c.id=e.client_id WHERE ct.id=?""",(cid,)).fetchone()
    if not ct:return 'Not found',404
    if request.method=='POST':
        f=request.form; status=f.get('status'); now=datetime.now().isoformat(timespec='seconds'); c.execute('UPDATE contracts SET status=?,sent_at=?,signed_at=?,expires_at=?,content=? WHERE id=?',(status,now if status=='Sent' else ct['sent_at'],now if status=='Signed' else ct['signed_at'],f.get('expires_at') or None,f.get('content'),cid)); c.commit(); c.close(); audit('Updated contract','Contract',cid); return redirect(url_for('contract_detail',cid=cid))
    c.close(); return render_template('contract_detail.html',ct=ct)

@app.route('/invoices')
@login_required
def invoices():
    c=db(); rows=c.execute("""SELECT i.*,e.event_date,c.first_name,c.last_name FROM invoices i JOIN events e ON e.id=i.event_id JOIN clients c ON c.id=e.client_id ORDER BY i.id DESC""").fetchall(); c.close(); return render_template('invoices.html',rows=rows)

@app.route('/events/<int:eid>/invoice/new',methods=['GET','POST'])
@login_required
def new_invoice(eid):
    c=db(); e=c.execute("SELECT e.*,c.first_name,c.last_name FROM events e JOIN clients c ON c.id=e.client_id WHERE e.id=?",(eid,)).fetchone(); q=c.execute('SELECT * FROM quotes WHERE event_id=? ORDER BY id DESC LIMIT 1',(eid,)).fetchone()
    if request.method=='POST':
        f=request.form; num=f.get('invoice_number') or f'INV-{datetime.now().strftime("%Y%m%d")}-{eid:04d}'; total=float(f.get('total') or (q['total'] if q else e['total'] or 0)); c.execute('INSERT INTO invoices(event_id,quote_id,invoice_number,total,due_date,status,created_at) VALUES(?,?,?,?,?,?,?)',(eid,q['id'] if q else None,num,total,f.get('due_date') or None,f.get('status','Due'),datetime.now().isoformat(timespec='seconds'))); iid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']; c.commit(); c.close(); audit('Created invoice','Invoice',iid); return redirect(url_for('invoice_detail',iid=iid))
    c.close(); return render_template('invoice_form.html',event=e,quote=q)

@app.route('/invoices/<int:iid>',methods=['GET','POST'])
@login_required
def invoice_detail(iid):
    c=db(); inv=c.execute("""SELECT i.*,e.id eid,e.event_date,c.first_name,c.last_name FROM invoices i JOIN events e ON e.id=i.event_id JOIN clients c ON c.id=e.client_id WHERE i.id=?""",(iid,)).fetchone()
    if not inv:return 'Not found',404
    if request.method=='POST':
        f=request.form; c.execute('UPDATE invoices SET total=?,due_date=?,status=? WHERE id=?',(float(f.get('total') or 0),f.get('due_date') or None,f.get('status'),iid)); c.commit(); c.close(); audit('Updated invoice','Invoice',iid); return redirect(url_for('invoice_detail',iid=iid))
    pays=c.execute('SELECT * FROM payments WHERE invoice_id=? ORDER BY payment_date DESC',(iid,)).fetchall(); paid=sum(float(p['amount']) for p in pays if p['status']=='Paid'); c.close(); return render_template('invoice_detail.html',inv=inv,payments=pays,paid=paid,balance=max(0,float(inv['total'])-paid))

@app.post('/invoices/<int:iid>/payment')
@login_required
def add_payment(iid):
    c=db(); inv=c.execute('SELECT * FROM invoices WHERE id=?',(iid,)).fetchone(); f=request.form; amount=float(f.get('amount') or 0); c.execute('INSERT INTO payments(event_id,invoice_id,amount,payment_date,method,status,reference,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(inv['event_id'],iid,amount,f.get('payment_date') or date.today().isoformat(),f.get('method','Other'),f.get('status','Paid'),f.get('reference'),f.get('notes'),datetime.now().isoformat(timespec='seconds'))); pid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']; paid=c.execute("SELECT COALESCE(SUM(amount),0) n FROM payments WHERE invoice_id=? AND status='Paid'",(iid,)).fetchone()['n']; c.execute('UPDATE invoices SET status=? WHERE id=?',('Paid' if paid>=inv['total'] else 'Partial',iid)); sync_event(c,inv['event_id']); c.commit(); c.close(); audit('Recorded payment','Payment',pid); return redirect(url_for('invoice_detail',iid=iid))

@app.route('/documents')
@login_required
def documents():
    c=db(); rows=c.execute("""SELECT d.*,c.first_name,c.last_name,e.event_date FROM documents d LEFT JOIN clients c ON c.id=d.client_id LEFT JOIN events e ON e.id=d.event_id ORDER BY d.id DESC""").fetchall(); c.close(); return render_template('documents.html',rows=rows)

@app.route('/events/<int:eid>/document/new',methods=['GET','POST'])
@login_required
def new_document(eid):
    c=db(); e=c.execute("SELECT e.*,c.id client_id,c.first_name,c.last_name FROM events e JOIN clients c ON c.id=e.client_id WHERE e.id=?",(eid,)).fetchone()
    if request.method=='POST':
        f=request.form; c.execute('INSERT INTO documents(client_id,event_id,name,doc_type,status,content,created_at) VALUES(?,?,?,?,?,?,?)',(e['client_id'],eid,f['name'],f.get('doc_type','Other'),f.get('status','Created'),f.get('content'),datetime.now().isoformat(timespec='seconds'))); did=c.execute('SELECT last_insert_rowid() id').fetchone()['id']; c.commit(); c.close(); audit('Created document','Document',did); return redirect(url_for('documents'))
    c.close(); return render_template('document_form.html',event=e)

@app.route('/questionnaires')
@login_required
def questionnaires():
    c=db(); rows=c.execute("""SELECT q.*,e.event_date,c.first_name,c.last_name FROM questionnaires q JOIN events e ON e.id=q.event_id JOIN clients c ON c.id=e.client_id ORDER BY q.id DESC""").fetchall(); c.close(); return render_template('questionnaires.html',rows=rows)

@app.route('/events/<int:eid>/questionnaire/new',methods=['GET','POST'])
@login_required
def new_questionnaire(eid):
    c=db(); e=c.execute("SELECT e.*,c.first_name,c.last_name FROM events e JOIN clients c ON c.id=e.client_id WHERE e.id=?",(eid,)).fetchone()
    if request.method=='POST':
        f=request.form; token=secrets.token_urlsafe(20); c.execute('INSERT INTO questionnaires(event_id,title,status,due_date,token,created_at) VALUES(?,?,?,?,?,?)',(eid,f.get('title') or 'Wedding Planning Questionnaire',f.get('status','Draft'),f.get('due_date') or None,token,datetime.now().isoformat(timespec='seconds'))); qid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']; labels=[x.strip() for x in f.get('questions','').splitlines() if x.strip()]
        for i,label in enumerate(labels): c.execute('INSERT INTO questionnaire_questions(questionnaire_id,label,field_type,sort_order) VALUES(?,?,?,?)',(qid,label,'long',i))
        c.commit(); c.close(); audit('Created questionnaire','Questionnaire',qid); return redirect(url_for('questionnaire_detail',qid=qid))
    c.close(); return render_template('questionnaire_form.html',event=e)

@app.route('/questionnaires/<int:qid>')
@login_required
def questionnaire_detail(qid):
    c=db(); q=c.execute("""SELECT q.*,e.event_date,c.first_name,c.last_name,c.email FROM questionnaires q JOIN events e ON e.id=q.event_id JOIN clients c ON c.id=e.client_id WHERE q.id=?""",(qid,)).fetchone(); qs=c.execute('SELECT * FROM questionnaire_questions WHERE questionnaire_id=? ORDER BY sort_order',(qid,)).fetchall(); c.close(); return render_template('questionnaire_detail.html',q=q,questions=qs)

@app.route('/portal/<token>',methods=['GET','POST'])
def client_portal(token):
    c=db(); q=c.execute("""SELECT q.*,e.id eid,e.event_date,e.venue,e.package,e.total,e.paid,c.first_name,c.last_name,c.partner_name,c.email,c.phone FROM questionnaires q JOIN events e ON e.id=q.event_id JOIN clients c ON c.id=e.client_id WHERE q.token=?""",(token,)).fetchone()
    if not q:return 'Portal link not found.',404
    if request.method=='POST':
        for key,val in request.form.items():
            if key.startswith('q_'):
                qid=int(key[2:]); c.execute('INSERT INTO questionnaire_answers(question_id,questionnaire_id,answer,updated_at) VALUES(?,?,?,?) ON CONFLICT(question_id,questionnaire_id) DO UPDATE SET answer=excluded.answer,updated_at=excluded.updated_at',(qid,q['id'],val,datetime.now().isoformat(timespec='seconds')))
        c.execute("UPDATE questionnaires SET status='Completed',completed_at=? WHERE id=?",(datetime.now().isoformat(timespec='seconds'),q['id'])); c.commit(); c.close(); return render_template('portal.html',q=q,questions=[],submitted=True)
    qs=c.execute('SELECT * FROM questionnaire_questions WHERE questionnaire_id=? ORDER BY sort_order',(q['id'],)).fetchall(); c.close(); return render_template('portal.html',q=q,questions=qs,submitted=False)

@app.route('/communications',methods=['GET','POST'])
@login_required
def communications():
    c=db()
    if request.method=='POST':
        f=request.form; c.execute('INSERT INTO communications(client_id,event_id,type,direction,subject,message,user_id,created_at) VALUES(?,?,?,?,?,?,?,?)',(int(f['client_id']) if f.get('client_id') else None,int(f['event_id']) if f.get('event_id') else None,f.get('type','Note'),f.get('direction','Internal'),f.get('subject'),f['message'],session['user_id'],datetime.now().isoformat(timespec='seconds'))); c.commit(); c.close(); return redirect(url_for('communications'))
    rows=c.execute("""SELECT m.*,u.name user_name,c.first_name,c.last_name FROM communications m LEFT JOIN users u ON u.id=m.user_id LEFT JOIN clients c ON c.id=m.client_id ORDER BY m.id DESC LIMIT 100""").fetchall(); clients_=c.execute('SELECT id,first_name,last_name FROM clients ORDER BY last_name').fetchall(); events_=c.execute('SELECT id,event_date,event_name FROM events ORDER BY event_date DESC').fetchall(); c.close(); return render_template('communications.html',rows=rows,clients=clients_,events=events_)

@app.route('/api/package-price/<name>')
def package_api(name): return jsonify({'name':name,'price':package_price(name)})

# ---------------- Phase 6: Integrations & Go-Live ----------------
INTEGRATION_PROVIDERS = [
    ('Google Calendar','Calendar sync connection point; OAuth credentials belong in environment variables.'),
    ('Gmail','Email connection point; authorize externally before enabling.'),
    ('Microsoft Outlook','Outlook email/calendar connection point.'),
    ('Stripe','Online payment connection point; raw card data is never stored.'),
    ('PayPal','Payment connection point.'),
    ('Venmo','Payment reconciliation/deep-link connection point.'),
    ('HoneyBook','CSV compatibility bridge for migration/export.'),
    ('Google Drive','Document storage connection point.'),
    ('Website Lead Form','Public inquiry form is active in this build.'),
]

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'): return redirect(url_for('login'))
        c=db(); u=c.execute('SELECT role FROM users WHERE id=?',(session['user_id'],)).fetchone(); c.close()
        if not u or u['role'] != 'Admin': return 'Admin access required.',403
        return fn(*args, **kwargs)
    return wrapper

def hash_token(v):
    import hashlib
    return hashlib.sha256(v.encode()).hexdigest()

def get_setting(c,key,default=''):
    r=c.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone(); return r['value'] if r else default

@app.route('/inquiry', methods=['GET','POST'])
def public_inquiry():
    if request.method=='POST':
        f=request.form
        if f.get('website'): return render_template('inquiry.html', submitted=True)
        first=(f.get('first_name') or '').strip(); last=(f.get('last_name') or '').strip(); email=(f.get('email') or '').strip()
        if not first or not last or not email or not f.get('event_date'):
            return render_template('inquiry.html', form=f, error='Please provide your name, email, and event date.'),400
        c=db(); now=datetime.now().isoformat(timespec='seconds')
        vals=(first,last,f.get('partner_name'),email,f.get('phone'),f.get('event_type','Wedding'),f.get('event_date'),f.get('venue'),int(f.get('guest_count') or 0) or None,float(f.get('budget') or 0) or None,f.get('package'),f.get('source') or 'Website',f.get('message'),'New Inquiry',now,(date.today()+timedelta(days=1)).isoformat())
        c.execute("INSERT INTO leads(first_name,last_name,partner_name,email,phone,event_type,event_date,venue,guest_count,budget,package,source,message,status,created_at,next_follow_up) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",vals)
        lid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']
        c.execute("INSERT INTO tasks(title,due_date,priority,status,task_type,notes,created_at) VALUES(?,?,?,?,?,?,?)",('Contact new website inquiry',(date.today()+timedelta(days=1)).isoformat(),'High','Open','Lead Follow-Up',f'New website inquiry from {first} {last}. Lead #{lid}',now))
        c.execute('INSERT INTO public_inquiries(lead_id,ip_hash,user_agent,created_at) VALUES(?,?,?,?)',(lid,hash_token(request.remote_addr or ''),request.headers.get('User-Agent','')[:300],now))
        c.commit(); c.close(); return render_template('inquiry.html', submitted=True)
    return render_template('inquiry.html',form={})

@app.route('/api/public/leads', methods=['POST'])
def public_lead_api():
    configured=os.environ.get('CRM_PUBLIC_API_KEY')
    if configured and request.headers.get('X-CRM-Key') != configured: return jsonify({'error':'Unauthorized'}),401
    data=request.get_json(silent=True) or {}; required=['first_name','last_name','email','event_date']; missing=[x for x in required if not str(data.get(x) or '').strip()]
    if missing:return jsonify({'error':'Missing required fields','fields':missing}),400
    c=db(); now=datetime.now().isoformat(timespec='seconds')
    vals=(data['first_name'],data['last_name'],data.get('partner_name'),data['email'],data.get('phone'),data.get('event_type','Wedding'),data['event_date'],data.get('venue'),data.get('guest_count'),data.get('budget'),data.get('package'),data.get('source','Website'),data.get('message'),'New Inquiry',now,(date.today()+timedelta(days=1)).isoformat())
    c.execute("INSERT INTO leads(first_name,last_name,partner_name,email,phone,event_type,event_date,venue,guest_count,budget,package,source,message,status,created_at,next_follow_up) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",vals)
    lid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']; c.execute("INSERT INTO tasks(title,due_date,priority,status,task_type,notes,created_at) VALUES(?,?,?,?,?,?,?)",('Contact new website inquiry',(date.today()+timedelta(days=1)).isoformat(),'High','Open','Lead Follow-Up',f'API website inquiry. Lead #{lid}',now)); c.commit(); c.close()
    return jsonify({'ok':True,'lead_id':lid}),201

@app.route('/integrations', methods=['GET','POST'])
@admin_required
def integrations():
    c=db()
    if request.method=='POST':
        for provider,_ in INTEGRATION_PROVIDERS:
            enabled=1 if request.form.get('provider_'+provider)=='on' else 0
            c.execute("INSERT INTO integration_settings(provider,enabled,config,updated_at) VALUES(?,?,?,?) ON CONFLICT(provider) DO UPDATE SET enabled=excluded.enabled,updated_at=excluded.updated_at",(provider,enabled,'',datetime.now().isoformat(timespec='seconds')))
        c.commit(); c.close(); return redirect(url_for('integrations'))
    rows={r['provider']:r for r in c.execute('SELECT * FROM integration_settings').fetchall()}; base=get_setting(c,'PUBLIC_BASE_URL',request.url_root.rstrip('/')); c.close()
    return render_template('integrations.html',providers=INTEGRATION_PROVIDERS,rows=rows,base_url=base)

@app.route('/settings', methods=['GET','POST'])
@admin_required
def settings_page():
    c=db()
    if request.method=='POST':
        for k,v in request.form.items():
            if k.startswith('setting_'): c.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(k[8:],v))
        c.commit(); c.close(); return redirect(url_for('settings_page'))
    vals={r['key']:r['value'] for r in c.execute('SELECT * FROM settings ORDER BY key').fetchall()}; c.close(); return render_template('settings.html',vals=vals)

@app.route('/api/calendar/event/<int:eid>.ics')
@login_required
def event_ics(eid):
    c=db(); e=c.execute('SELECT e.*,c.first_name,c.last_name FROM events e JOIN clients c ON c.id=e.client_id WHERE e.id=?',(eid,)).fetchone(); c.close()
    if not e:return 'Not found',404
    dt=e['event_date'].replace('-',''); summary=(e['event_name'] or f"{e['first_name']} {e['last_name']} — {e['event_type']}").replace(',','\\,'); venue=(e['venue'] or '').replace(',','\\,')
    body=f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Dynamite DJs CRM//EN\r\nBEGIN:VEVENT\r\nUID:dynamitedjs-event-{eid}@crm\r\nDTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}\r\nDTSTART;VALUE=DATE:{dt}\r\nDTEND;VALUE=DATE:{dt}\r\nSUMMARY:{summary}\r\nLOCATION:{venue}\r\nDESCRIPTION:Package: {e['package'] or ''}\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    return Response(body,mimetype='text/calendar',headers={'Content-Disposition':f'attachment; filename="event-{eid}.ics"'})

@app.route('/honeybook/export.csv')
@login_required
def honeybook_export():
    c=db(); rows=c.execute("SELECT l.id,l.first_name,l.last_name,l.partner_name,l.email,l.phone,l.event_date,l.venue,l.package,l.source,l.status,e.id event_id,e.total,e.paid FROM leads l LEFT JOIN events e ON e.lead_id=l.id ORDER BY l.id").fetchall(); c.close()
    import csv,io; out=io.StringIO(); w=csv.writer(out); w.writerow(['Lead ID','First Name','Last Name','Partner','Email','Phone','Event Date','Venue','Package','Source','Lead Status','Event ID','Event Total','Paid'])
    for r in rows:w.writerow([r[k] for k in ['id','first_name','last_name','partner_name','email','phone','event_date','venue','package','source','status','event_id','total','paid']])
    return Response(out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename="dynamite-djs-honeybook-export.csv"'})

@app.route('/api/webhooks/<provider>', methods=['POST'])
def inbound_webhook(provider):
    key=os.environ.get('CRM_WEBHOOK_KEY')
    if key and request.headers.get('X-Webhook-Key') != key:return jsonify({'error':'Unauthorized'}),401
    payload=request.get_json(silent=True) or {}; import json; c=db(); now=datetime.now().isoformat(timespec='seconds')
    c.execute('INSERT INTO webhook_events(provider,event_type,payload,status,created_at) VALUES(?,?,?,?,?)',(provider,payload.get('type') if isinstance(payload,dict) else None,json.dumps(payload),'Received',now)); c.commit(); c.close(); return jsonify({'ok':True}),202

@app.errorhandler(404)
def notfound(e): return render_template('404.html'),404

# ---------------- Phase 3: Wedding Management ----------------
TIMELINE_DEFAULTS = ['Guest Arrival','Ceremony','Cocktail Hour','Grand Entrance','First Dance','Parent Dances','Dinner','Toasts','Cake','Bouquet','Garter','Open Dancing','Last Call','Last Dance','Grand Exit']
MUSIC_CATEGORIES = ['Must Play','Do Not Play','Ceremony','Cocktail','Dinner','Dancing','Special Dances']
MUSIC_STATUSES = ['Requested','Approved','Planned','Played','Skipped']

@app.route('/events/<int:eid>/timeline', methods=['GET','POST'])
@login_required
def event_timeline(eid):
    c=db(); e=c.execute('SELECT e.*,c.first_name,c.last_name FROM events e JOIN clients c ON c.id=e.client_id WHERE e.id=?',(eid,)).fetchone()
    if not e: c.close(); return 'Not found',404
    if request.method=='POST':
        f=request.form; mx=c.execute('SELECT COALESCE(MAX(sort_order),-1) m FROM timeline_items WHERE event_id=?',(eid,)).fetchone()['m']
        c.execute('INSERT INTO timeline_items(event_id,title,start_time,duration,description,person_responsible,music,mc_notes,special_instructions,sort_order) VALUES(?,?,?,?,?,?,?,?,?,?)',(eid,f['title'],f.get('start_time'),int(f['duration']) if f.get('duration') else None,f.get('description'),f.get('person_responsible'),f.get('music'),f.get('mc_notes'),f.get('special_instructions'),mx+1)); c.commit(); c.close(); audit('Added timeline item','Event',eid); return redirect(url_for('event_timeline',eid=eid))
    items=c.execute('SELECT * FROM timeline_items WHERE event_id=? ORDER BY sort_order,id',(eid,)).fetchall()
    if not items:
        for i,title in enumerate(TIMELINE_DEFAULTS): c.execute('INSERT INTO timeline_items(event_id,title,sort_order) VALUES(?,?,?)',(eid,title,i))
        c.commit(); items=c.execute('SELECT * FROM timeline_items WHERE event_id=? ORDER BY sort_order,id',(eid,)).fetchall()
    c.close(); return render_template('timeline.html',event=e,items=items)

@app.post('/events/<int:eid>/timeline/<int:item_id>/update')
@login_required
def update_timeline_item(eid,item_id):
    f=request.form; c=db(); c.execute('UPDATE timeline_items SET title=?,start_time=?,duration=?,description=?,person_responsible=?,music=?,mc_notes=?,special_instructions=? WHERE id=? AND event_id=?',(f['title'],f.get('start_time'),int(f['duration']) if f.get('duration') else None,f.get('description'),f.get('person_responsible'),f.get('music'),f.get('mc_notes'),f.get('special_instructions'),item_id,eid)); c.commit(); c.close(); return redirect(url_for('event_timeline',eid=eid))

@app.post('/events/<int:eid>/timeline/<int:item_id>/delete')
@login_required
def delete_timeline_item(eid,item_id):
    c=db(); c.execute('DELETE FROM timeline_items WHERE id=? AND event_id=?',(item_id,eid)); c.commit(); c.close(); return redirect(url_for('event_timeline',eid=eid))

@app.route('/events/<int:eid>/music', methods=['GET','POST'])
@login_required
def event_music(eid):
    c=db(); e=c.execute('SELECT e.*,c.first_name,c.last_name FROM events e JOIN clients c ON c.id=e.client_id WHERE e.id=?',(eid,)).fetchone()
    if not e: c.close(); return 'Not found',404
    if request.method=='POST':
        f=request.form; mx=c.execute('SELECT COALESCE(MAX(sort_order),-1) m FROM songs WHERE event_id=?',(eid,)).fetchone()['m']
        c.execute('INSERT INTO songs(event_id,category,title,artist,notes,timing,special_edit,requested_by,status,sort_order) VALUES(?,?,?,?,?,?,?,?,?,?)',(eid,f.get('category','Dancing'),f['title'],f.get('artist'),f.get('notes'),f.get('timing'),f.get('special_edit'),f.get('requested_by'),f.get('status','Requested'),mx+1)); c.commit(); c.close(); return redirect(url_for('event_music',eid=eid))
    songs=c.execute('SELECT * FROM songs WHERE event_id=? ORDER BY CASE category WHEN "Must Play" THEN 0 WHEN "Do Not Play" THEN 1 ELSE 2 END,sort_order,id',(eid,)).fetchall(); c.close(); return render_template('music.html',event=e,songs=songs,categories=MUSIC_CATEGORIES,statuses=MUSIC_STATUSES)

@app.post('/events/<int:eid>/music/<int:song_id>/update')
@login_required
def update_song(eid,song_id):
    f=request.form; c=db(); c.execute('UPDATE songs SET category=?,title=?,artist=?,notes=?,timing=?,special_edit=?,requested_by=?,status=? WHERE id=? AND event_id=?',(f['category'],f['title'],f.get('artist'),f.get('notes'),f.get('timing'),f.get('special_edit'),f.get('requested_by'),f.get('status','Requested'),song_id,eid)); c.commit(); c.close(); return redirect(url_for('event_music',eid=eid))

@app.post('/events/<int:eid>/music/<int:song_id>/delete')
@login_required
def delete_song(eid,song_id):
    c=db(); c.execute('DELETE FROM songs WHERE id=? AND event_id=?',(song_id,eid)); c.commit(); c.close(); return redirect(url_for('event_music',eid=eid))

@app.route('/events/<int:eid>/planning', methods=['GET','POST'])
@login_required
def event_planning(eid):
    c=db(); e=c.execute('SELECT e.*,c.first_name,c.last_name,c.partner_name,c.email,c.phone FROM events e JOIN clients c ON c.id=e.client_id WHERE e.id=?',(eid,)).fetchone()
    if not e: c.close(); return 'Not found',404
    p=c.execute('SELECT * FROM event_planning WHERE event_id=?',(eid,)).fetchone()
    if request.method=='POST':
        f=request.form; keys=['ceremony_location','ceremony_time','cocktail_time','reception_time','guest_arrival_time','grand_entrance_time','first_dance','parent_dances','announcements','traditions','vendor_info','day_of_contact','emergency_contact','ceremony_notes','reception_notes','genres','special_instructions']; vals=[f.get(k) for k in keys]
        if p: c.execute('UPDATE event_planning SET ceremony_location=?,ceremony_time=?,cocktail_time=?,reception_time=?,guest_arrival_time=?,grand_entrance_time=?,first_dance=?,parent_dances=?,announcements=?,traditions=?,vendor_info=?,day_of_contact=?,emergency_contact=?,ceremony_notes=?,reception_notes=?,genres=?,special_instructions=? WHERE event_id=?',(*vals,eid))
        else: c.execute('INSERT INTO event_planning(event_id,ceremony_location,ceremony_time,cocktail_time,reception_time,guest_arrival_time,grand_entrance_time,first_dance,parent_dances,announcements,traditions,vendor_info,day_of_contact,emergency_contact,ceremony_notes,reception_notes,genres,special_instructions) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(eid,*vals))
        c.commit(); c.close(); return redirect(url_for('event_planning',eid=eid))
    c.close(); return render_template('planning.html',event=e,planning=p)

@app.route('/events/<int:eid>/checklist', methods=['GET','POST'])
@login_required
def event_checklist(eid):
    c=db(); e=c.execute('SELECT e.*,c.first_name,c.last_name FROM events e JOIN clients c ON c.id=e.client_id WHERE e.id=?',(eid,)).fetchone()
    if not e: c.close(); return 'Not found',404
    if request.method=='POST':
        f=request.form; mx=c.execute('SELECT COALESCE(MAX(sort_order),-1) m FROM equipment_checklist WHERE event_id=?',(eid,)).fetchone()['m']; c.execute('INSERT INTO equipment_checklist(event_id,item,category,checked,sort_order) VALUES(?,?,?,?,?)',(eid,f['item'],f.get('category','General'),0,mx+1)); c.commit(); c.close(); return redirect(url_for('event_checklist',eid=eid))
    if c.execute('SELECT COUNT(*) n FROM equipment_checklist WHERE event_id=?',(eid,)).fetchone()['n']==0:
        defaults=[('Speakers','Audio'),('Mixer','Audio'),('Wireless mics','Audio'),('Ceremony equipment','Ceremony'),('Lighting','Lighting'),('Photo booth','Enhancements'),('Monogram','Enhancements'),('Backup system','Backup'),('Laptop / iPad','Backup'),('Cables / adapters','General'),('Power / extension cords','General'),('Music backup','Backup'),('Arrived','Event Day'),('Setup complete','Event Day'),('Soundcheck complete','Event Day'),('Ceremony complete','Event Day'),('Reception complete','Event Day'),('Packed','Event Day')]
        for i,(item,cat) in enumerate(defaults): c.execute('INSERT INTO equipment_checklist(event_id,item,category,sort_order) VALUES(?,?,?,?)',(eid,item,cat,i))
        c.commit()
    rows=c.execute('SELECT * FROM equipment_checklist WHERE event_id=? ORDER BY sort_order,id',(eid,)).fetchall(); c.close(); return render_template('checklist.html',event=e,rows=rows)

@app.post('/events/<int:eid>/checklist/<int:item_id>/toggle')
@login_required
def toggle_checklist(eid,item_id):
    c=db(); c.execute('UPDATE equipment_checklist SET checked=CASE WHEN checked=1 THEN 0 ELSE 1 END WHERE id=? AND event_id=?',(item_id,eid)); c.commit(); c.close(); return redirect(request.referrer or url_for('event_checklist',eid=eid))

@app.route('/events/<int:eid>/day-mode')
@login_required
def event_day_mode(eid):
    c=db(); e=c.execute('SELECT e.*,c.first_name,c.last_name,c.partner_name,c.email,c.phone,u.name dj FROM events e JOIN clients c ON c.id=e.client_id LEFT JOIN users u ON u.id=e.assigned_user_id WHERE e.id=?',(eid,)).fetchone(); timeline=c.execute('SELECT * FROM timeline_items WHERE event_id=? ORDER BY sort_order,id',(eid,)).fetchall(); songs=c.execute('SELECT * FROM songs WHERE event_id=? ORDER BY CASE category WHEN "Must Play" THEN 0 WHEN "Do Not Play" THEN 1 ELSE 2 END,sort_order,id',(eid,)).fetchall(); p=c.execute('SELECT * FROM event_planning WHERE event_id=?',(eid,)).fetchone(); checks=c.execute('SELECT * FROM equipment_checklist WHERE event_id=? ORDER BY sort_order,id',(eid,)).fetchall(); c.close()
    if not e:return 'Not found',404
    return render_template('day_mode.html',event=e,timeline=timeline,songs=songs,planning=p,checks=checks)

@app.route('/events/<int:eid>/brief')
@login_required
def event_brief(eid):
    c=db(); e=c.execute('SELECT e.*,c.first_name,c.last_name,c.partner_name,c.email,c.phone,u.name dj FROM events e JOIN clients c ON c.id=e.client_id LEFT JOIN users u ON u.id=e.assigned_user_id WHERE e.id=?',(eid,)).fetchone(); timeline=c.execute('SELECT * FROM timeline_items WHERE event_id=? ORDER BY sort_order,id',(eid,)).fetchall(); songs=c.execute('SELECT * FROM songs WHERE event_id=? ORDER BY category,sort_order,id',(eid,)).fetchall(); p=c.execute('SELECT * FROM event_planning WHERE event_id=?',(eid,)).fetchone(); checks=c.execute('SELECT * FROM equipment_checklist WHERE event_id=? ORDER BY sort_order,id',(eid,)).fetchall(); c.close()
    if not e:return 'Not found',404
    return render_template('brief.html',event=e,timeline=timeline,songs=songs,planning=p,checks=checks)


@app.route('/reports')
@login_required
def reports():
    c=db(); today=date.today()
    start=request.args.get('start') or f'{today.year}-01-01'; end=request.args.get('end') or f'{today.year}-12-31'
    params=(start,end)
    events=c.execute("""SELECT e.*, c.first_name,c.last_name,u.name dj,
        COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.event_id=e.id AND p.status='Paid'),0) collected,
        (e.total-COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.event_id=e.id AND p.status='Paid'),0)) balance
        FROM events e JOIN clients c ON c.id=e.client_id LEFT JOIN users u ON u.id=e.assigned_user_id
        WHERE e.event_date BETWEEN ? AND ? ORDER BY e.event_date""",params).fetchall()
    leads=c.execute('SELECT * FROM leads WHERE date(created_at) BETWEEN ? AND ? ORDER BY created_at',params).fetchall()
    booked=len(events); revenue=c.execute("SELECT COALESCE(SUM(total),0) n FROM events WHERE event_date BETWEEN ? AND ? AND planning_status!='Cancelled'",params).fetchone()['n']
    collected=c.execute("SELECT COALESCE(SUM(p.amount),0) n FROM payments p JOIN events e ON e.id=p.event_id WHERE e.event_date BETWEEN ? AND ? AND p.status='Paid'",params).fetchone()['n']
    outstanding=max(float(revenue)-float(collected),0)
    overdue=c.execute("""SELECT COALESCE(SUM(i.total-COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.invoice_id=i.id AND p.status='Paid'),0)),0) n
        FROM invoices i JOIN events e ON e.id=i.event_id WHERE i.due_date < ? AND (i.total-COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.invoice_id=i.id AND p.status='Paid'),0)) > 0 AND e.event_date BETWEEN ? AND ?""",(today.isoformat(),start,end)).fetchone()['n']
    avg=float(revenue)/booked if booked else 0; lead_count=len(leads); won_leads=sum(1 for l in leads if l['status']=='Booked'); conversion=won_leads/lead_count*100 if lead_count else 0
    package_rows=c.execute("""SELECT COALESCE(e.package,'Unspecified') package, COUNT(*) events, COALESCE(SUM(e.total),0) revenue, COALESCE(AVG(e.total),0) avg_value
        FROM events e WHERE e.event_date BETWEEN ? AND ? GROUP BY COALESCE(e.package,'Unspecified') ORDER BY events DESC,revenue DESC""",params).fetchall()
    source_rows=c.execute("""SELECT COALESCE(l.source,'Unknown') source, COUNT(*) leads, SUM(CASE WHEN l.status='Booked' THEN 1 ELSE 0 END) booked,
        CASE WHEN COUNT(*)=0 THEN 0.0 ELSE SUM(CASE WHEN l.status='Booked' THEN 1.0 ELSE 0 END)*100.0/COUNT(*) END conversion
        FROM leads l WHERE date(l.created_at) BETWEEN ? AND ? GROUP BY COALESCE(l.source,'Unknown') ORDER BY leads DESC,booked DESC""",params).fetchall()
    month_rows=c.execute("""SELECT substr(event_date,1,7) month, COUNT(*) events, COALESCE(SUM(total),0) revenue, COALESCE(SUM(paid),0) recorded_paid
        FROM events WHERE event_date BETWEEN ? AND ? GROUP BY substr(event_date,1,7) ORDER BY month""",params).fetchall()
    venue_rows=c.execute("""SELECT COALESCE(NULLIF(venue,''),'Venue TBD') venue, COUNT(*) events, COALESCE(SUM(total),0) revenue
        FROM events WHERE event_date BETWEEN ? AND ? GROUP BY COALESCE(NULLIF(venue,''),'Venue TBD') ORDER BY events DESC,revenue DESC LIMIT 15""",params).fetchall()
    dj_rows=c.execute("""SELECT COALESCE(u.name,'Unassigned') dj, COUNT(*) events, COALESCE(SUM(e.total),0) revenue,
        COALESCE(SUM(e.total-COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.event_id=e.id AND p.status='Paid'),0)),0) outstanding
        FROM events e LEFT JOIN users u ON u.id=e.assigned_user_id WHERE e.event_date BETWEEN ? AND ? GROUP BY COALESCE(u.name,'Unassigned') ORDER BY events DESC""",params).fetchall()
    upcoming=c.execute("""SELECT e.*,c.first_name,c.last_name,u.name dj FROM events e JOIN clients c ON c.id=e.client_id LEFT JOIN users u ON u.id=e.assigned_user_id WHERE e.event_date>=? ORDER BY e.event_date LIMIT 10""",(today.isoformat(),)).fetchall(); c.close()
    stats={'booked':booked,'revenue':revenue,'collected':collected,'outstanding':outstanding,'overdue':overdue,'avg':avg,'lead_count':lead_count,'won_leads':won_leads,'conversion':conversion}
    return render_template('reports.html',start=start,end=end,stats=stats,package_rows=package_rows,source_rows=source_rows,month_rows=month_rows,venue_rows=venue_rows,dj_rows=dj_rows,upcoming=upcoming,events=events)

@app.route('/reports/export')
@login_required
def reports_export():
    start=request.args.get('start') or f'{date.today().year}-01-01'; end=request.args.get('end') or f'{date.today().year}-12-31'
    c=db(); rows=c.execute("""SELECT e.id,e.event_date,c.first_name||' '||c.last_name client,e.venue,e.package,COALESCE(u.name,'Unassigned') dj,e.planning_status,e.total,
        COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.event_id=e.id AND p.status='Paid'),0) collected,
        e.total-COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.event_id=e.id AND p.status='Paid'),0) balance
        FROM events e JOIN clients c ON c.id=e.client_id LEFT JOIN users u ON u.id=e.assigned_user_id WHERE e.event_date BETWEEN ? AND ? ORDER BY e.event_date""",(start,end)).fetchall(); c.close()
    import csv,io; out=io.StringIO(); w=csv.writer(out); w.writerow(['Event ID','Event Date','Client','Venue','Package','DJ','Planning Status','Total','Collected','Balance'])
    for r in rows: w.writerow(list(r))
    return Response(out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':f'attachment; filename=dynamite-djs-events-{start}-to-{end}.csv'})

@app.route('/automations')
@login_required
def automations():
    run_automations()
    c=db(); rules=c.execute('SELECT * FROM automation_rules ORDER BY id').fetchall(); notes=c.execute("SELECT n.*,u.name FROM notifications n LEFT JOIN users u ON u.id=n.user_id ORDER BY n.read,n.created_at DESC LIMIT 30").fetchall(); c.close(); return render_template('automations.html',rules=rules,notifications=notes)

@app.post('/automations/<int:rid>/toggle')
@login_required
def toggle_automation(rid):
    c=db(); c.execute("UPDATE automation_rules SET enabled=CASE WHEN enabled=1 THEN 0 ELSE 1 END WHERE id=?",(rid,)); c.commit(); c.close(); audit('Toggled automation','AutomationRule',rid); return redirect(url_for('automations'))

@app.post('/automations/run')
@login_required
def run_automations_now():
    n=run_automations(); flash(f'Automation engine ran. {n} new task(s) created.','success'); return redirect(url_for('automations'))

@app.post('/notifications/<int:nid>/read')
@login_required
def mark_notification_read(nid):
    c=db(); c.execute('UPDATE notifications SET read=1 WHERE id=? AND user_id=?',(nid,session['user_id'])); c.commit(); c.close(); return redirect(request.referrer or url_for('automations'))

@app.post('/events/<int:eid>/status')
@login_required
def update_event_status(eid):
    status=request.form.get('planning_status','Planning'); c=db(); c.execute('UPDATE events SET planning_status=? WHERE id=?',(status,eid)); c.commit(); c.close(); audit('Updated event planning status','Event',eid); flash('Event status updated.','success'); return redirect(request.referrer or url_for('event_detail',eid=eid))


if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)),debug=True)
