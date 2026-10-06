"""Hospital workflow features. All records are fictional RP."""
import asyncio, io, logging, time, json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import discord
from discord import app_commands
from discord.ext import tasks
H=None
ZONE=ZoneInfo('America/New_York')
SPECS={'Family Medicine':('Family Medicine','family-medicine-records','🏡'),'OB-GYN':('OB-GYN','obgyn-records','🤰'),'Therapy':('Therapist','therapy-records','🧠'),'Pediatrician':('Pediatrician','pediatric-records','🧸'),'Physical Therapy':('Physical Therapist','physical-therapy-records','🦽')}
LOCKS={}
def lock(key):return LOCKS.setdefault(key,asyncio.Lock())
def db():
    d=H.training.connect()
    d.execute('CREATE TABLE IF NOT EXISTS appointments (channel INTEGER PRIMARY KEY, guild INTEGER, patient INTEGER, service TEXT, provider INTEGER DEFAULT 0, status TEXT DEFAULT "requested", scheduled REAL DEFAULT 0, revision INTEGER DEFAULT 0, hour_sent INTEGER DEFAULT 0, quarter_sent INTEGER DEFAULT 0)')
    d.execute('CREATE TABLE IF NOT EXISTS trainer_signoffs (id INTEGER PRIMARY KEY AUTOINCREMENT, guild INTEGER, member INTEGER, course TEXT, trainer INTEGER, signed REAL, notes TEXT, enrolled REAL DEFAULT 0)')
    d.execute('CREATE TABLE IF NOT EXISTS leave_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, guild INTEGER, member INTEGER, starts REAL, ends REAL, reason TEXT, status TEXT DEFAULT "pending", reviewer INTEGER DEFAULT 0, applied INTEGER DEFAULT 0)')
    d.execute('CREATE TABLE IF NOT EXISTS recognition (id INTEGER PRIMARY KEY AUTOINCREMENT, guild INTEGER, member INTEGER, actor INTEGER, reason TEXT, created REAL)')
    d.execute('CREATE TABLE IF NOT EXISTS workflow_state (key TEXT PRIMARY KEY, value TEXT)')
    return d
def appointment(cid):
    with db() as d:
        d.row_factory=__import__('sqlite3').Row
        r=d.execute('SELECT * FROM appointments WHERE channel=?',(cid,)).fetchone()
        return dict(r) if r else None
def appointment_staff(m,service):
    return m.guild_permissions.administrator or any(H.base_name(r.name) in H.LEAD+['Receptionist',SPECS[service][0]] for r in m.roles) and not (service=='Therapy' and all(H.base_name(r.name) not in H.LEAD+['Therapist'] for r in m.roles))
def specialty_staff(m,service):
    return m.guild_permissions.administrator or any(H.base_name(r.name) in H.LEAD+[SPECS[service][0]] for r in m.roles)
def unused_signoff(gid,uid,key):
    with db() as d:return d.execute('SELECT id FROM trainer_signoffs WHERE guild=? AND member=? AND course=? AND enrolled=0 ORDER BY signed DESC LIMIT 1',(gid,uid,key)).fetchone()
def consume_signoff(gid,uid,key,sid):
    with db() as d:
        r=d.execute('SELECT started FROM enrollments WHERE guild=? AND member=? AND course=?',(gid,uid,key)).fetchone()
        if not r:raise ValueError('No enrollment to link')
        result=d.execute('UPDATE trainer_signoffs SET enrolled=? WHERE id=? AND enrolled=0',(r[0],sid))
        if result.rowcount!=1:raise ValueError('Signoff already consumed')
        d.execute('UPDATE trainer_signoffs SET enrolled=-1 WHERE guild=? AND member=? AND course=? AND enrolled=0',(gid,uid,key))
def enrollment_signed(gid,uid,key):
    with db() as d:
        return d.execute('SELECT 1 FROM trainer_signoffs s JOIN enrollments e ON e.guild=s.guild AND e.member=s.member AND e.course=s.course AND e.started=s.enrolled WHERE e.guild=? AND e.member=? AND e.course=?',(gid,uid,key)).fetchone() is not None
async def dm(uid,g,text):
    try:
        member=g.get_member(uid) or await g.fetch_member(uid)
        await member.send(text)
        return True
    except (discord.Forbidden,discord.NotFound):return False
async def attach_appointment(c,patient,service):
    with db() as d:d.execute('INSERT OR IGNORE INTO appointments (channel,guild,patient,service) VALUES (?,?,?,?)',(c.id,c.guild.id,patient,service))
    specialist=H.role(c.guild,SPECS[service][0])
    if specialist:await c.set_permissions(specialist,view_channel=True,send_messages=True,read_message_history=True)
    existing=[m async for m in c.history(limit=100)]
    if not any(m.author==H.bot.user and m.embeds and m.embeds[0].footer.text=='STB appointment controls v1' for m in existing):
        e=discord.Embed(title='📅 APPOINTMENT MANAGEMENT',description='Assigned staff: claim the visit, confirm a time, reschedule or complete it. Patient: your confirmed date/time will appear in this ticket. Reminders are sent here and by DM when possible.',color=0xb71c1c);e.set_footer(text='STB appointment controls v1')
        await c.send(embed=e,view=AppointmentControls())
class ScheduleForm(discord.ui.Modal):
    def __init__(self,cid,reschedule):
        super().__init__(title='Reschedule appointment' if reschedule else 'Confirm appointment')
        self.cid=cid;self.reschedule=reschedule
        self.when=discord.ui.TextInput(label='Date/time: YYYY-MM-DD HH:MM (24-hour)',placeholder='2026-10-10 18:30',max_length=16)
        self.zone=discord.ui.TextInput(label='Timezone (IANA name)',default='America/New_York',placeholder='America/New_York',max_length=60)
        self.note=discord.ui.TextInput(label='Optional scheduling note',required=False,max_length=500,style=discord.TextStyle.paragraph)
        for v in [self.when,self.zone,self.note]:self.add_item(v)
    async def on_submit(self,i):
        row=appointment(self.cid)
        if not row or not appointment_staff(i.user,row['service']):return await i.response.send_message('Authorized appointment staff required.',ephemeral=True)
        try:
            naive=datetime.strptime(str(self.when),'%Y-%m-%d %H:%M');zone=ZoneInfo(str(self.zone).strip())
            a=naive.replace(tzinfo=zone,fold=0);b=naive.replace(tzinfo=zone,fold=1)
            if a.utcoffset()!=b.utcoffset():raise ValueError('Ambiguous or nonexistent DST time; choose a different time')
            stamp=a.timestamp()
            if datetime.fromtimestamp(stamp,zone).replace(tzinfo=None)!=naive or stamp<=time.time():raise ValueError('Use a future, valid local time')
        except Exception as e:return await i.response.send_message(f'Invalid date/time. Use YYYY-MM-DD HH:MM and a timezone such as America/New_York. {e}',ephemeral=True)
        await i.response.defer(ephemeral=True)
        async with lock(('appt',self.cid)):
            row=appointment(self.cid)
            if row['status'] in ['completed','closed']:return await i.followup.send('This appointment has already ended.',ephemeral=True)
            with db() as d:d.execute('UPDATE appointments SET scheduled=?,status="confirmed",revision=revision+1,hour_sent=0,quarter_sent=0 WHERE channel=?',(stamp,self.cid))
            await i.channel.send(f'📅 **{"Rescheduled" if self.reschedule else "Confirmed"}** for <@{row["patient"]}>: <t:{int(stamp)}:F> (<t:{int(stamp)}:R>).\nStaff: {i.user.mention}\n{self.note.value}')
            sent=await dm(row['patient'],i.guild,f'St. Bernards: your {row["service"]} appointment is confirmed for <t:{int(stamp)}:F>. Ticket: {i.channel.jump_url}')
            await i.followup.send('Appointment saved.'+(' Patient DM sent.' if sent else ' Patient DMs are closed; confirmation is in the ticket.'),ephemeral=True)
class AppointmentControls(discord.ui.View):
    def __init__(self):super().__init__(timeout=None)
    async def check(self,i):
        r=appointment(i.channel.id)
        if not r or not appointment_staff(i.user,r['service']):
            await i.response.send_message('Only the appropriate appointment staff can manage this visit.',ephemeral=True);return None
        if r['status'] in ['completed','closed']:
            await i.response.send_message('This appointment has already ended.',ephemeral=True);return None
        return r
    @discord.ui.button(label='Claim',emoji='🩺',custom_id='stb:appt:claim',style=discord.ButtonStyle.primary)
    async def claim(self,i,button):
        r=await self.check(i)
        if not r:return
        if not specialty_staff(i.user,r['service']):return await i.response.send_message('Only the matching specialty or leadership can claim patient care. Reception can schedule.',ephemeral=True)
        await i.response.defer(ephemeral=True)
        async with lock(('appt',i.channel.id)):
            r=appointment(i.channel.id)
            if r['status'] in ['completed','closed']:return await i.followup.send('This appointment has already ended.',ephemeral=True)
            if r['provider'] and r['provider']!=i.user.id:return await i.followup.send('Already claimed by another provider. Ask leadership to reassign it.',ephemeral=True)
            with db() as d:d.execute('UPDATE appointments SET provider=? WHERE channel=?',(i.user.id,i.channel.id))
            await i.channel.send(f'🩺 Appointment claimed by {i.user.mention}.')
            await i.followup.send('You are the assigned provider.',ephemeral=True)
    @discord.ui.button(label='Confirm',emoji='✅',custom_id='stb:appt:confirm',style=discord.ButtonStyle.success)
    async def confirm(self,i,button):
        if await self.check(i):await i.response.send_modal(ScheduleForm(i.channel.id,False))
    @discord.ui.button(label='Reschedule',emoji='📅',custom_id='stb:appt:reschedule')
    async def reschedule(self,i,button):
        if await self.check(i):await i.response.send_modal(ScheduleForm(i.channel.id,True))
    @discord.ui.button(label='Complete',emoji='🏁',custom_id='stb:appt:complete')
    async def complete(self,i,button):
        r=await self.check(i)
        if not r:return
        if not specialty_staff(i.user,r['service']):return await i.response.send_message('Matching provider or leadership required.',ephemeral=True)
        await i.response.defer(ephemeral=True)
        async with lock(('appt',i.channel.id)):
            with db() as d:d.execute('UPDATE appointments SET status="completed" WHERE channel=?',(i.channel.id,))
        await i.channel.send('✅ Visit completed. Save the patient report in your specialty forum, then Close & Archive this ticket.')
        await i.followup.send('Appointment marked completed; reminders stopped.',ephemeral=True)
class RecordForm(discord.ui.Modal):
    def __init__(self,service):
        super().__init__(title=f'{service} patient report'[:45]);self.service=service
        for label,length in [('Character name',100),('Visit date (YYYY-MM-DD)',10),('Visit reason / fictional observations',1000),('RP care provided / outcome',1000),('Follow-up plan / provider notes',1000)]:
            self.add_item(discord.ui.TextInput(label=label,max_length=length,style=discord.TextStyle.short if length<=100 else discord.TextStyle.paragraph))
    async def on_submit(self,i):
        if not specialty_staff(i.user,self.service):return await i.response.send_message('Matching specialty role required.',ephemeral=True)
        try:datetime.strptime(str(self.children[1]),'%Y-%m-%d')
        except ValueError:return await i.response.send_message('Use YYYY-MM-DD for the visit date.',ephemeral=True)
        await i.response.defer(ephemeral=True)
        forum=next((f for f in i.guild.forums if H.base_name(f.name)==SPECS[self.service][1]),None)
        if not forum:return await i.followup.send('Run /setup_hospital to create the records forums.',ephemeral=True)
        e=discord.Embed(title=f'{self.service} • Patient visit',color=0xb71c1c,timestamp=discord.utils.utcnow())
        for field in self.children:e.add_field(name=field.label,value=field.value,inline=False)
        e.add_field(name='Documented by',value=i.user.mention,inline=False)
        tag=discord.utils.get(forum.available_tags,name='Visit Report')
        created=await forum.create_thread(name=f'{self.children[0].value} • {self.children[1].value}'[:100],embed=e,applied_tags=[tag] if tag else [])
        await i.followup.send(f'Report saved: {created.thread.mention}. Only this specialty and leadership can view it.',ephemeral=True)
class RecordButton(discord.ui.View):
    def __init__(self,service):
        super().__init__(timeout=None);self.service=service
        b=discord.ui.Button(label='Create patient report',emoji='📝',custom_id=f'stb:record:{SPECS[service][1]}',style=discord.ButtonStyle.primary);b.callback=self.open;self.add_item(b)
    async def open(self,i):
        if not specialty_staff(i.user,self.service):return await i.response.send_message('Matching specialty role required.',ephemeral=True)
        await i.response.send_modal(RecordForm(self.service))
class LeaveForm(discord.ui.Modal):
    def __init__(self):
        super().__init__(title='Request leave')
        self.start=discord.ui.TextInput(label='First day off (YYYY-MM-DD)',max_length=10)
        self.end=discord.ui.TextInput(label='Last day off (YYYY-MM-DD)',max_length=10)
        self.reason=discord.ui.TextInput(label='Reason (shared only with reviewers)',max_length=700,style=discord.TextStyle.paragraph)
        for v in [self.start,self.end,self.reason]:self.add_item(v)
    async def on_submit(self,i):
        if not H.staff_member(i.user):return await i.response.send_message('Hospital staff required.',ephemeral=True)
        try:
            starts=datetime.strptime(str(self.start),'%Y-%m-%d').replace(tzinfo=ZONE)
            last=datetime.strptime(str(self.end),'%Y-%m-%d').replace(tzinfo=ZONE)
            ends=(last+timedelta(days=1)).timestamp()
            if last.date()<starts.date() or last.date()<datetime.now(ZONE).date():raise ValueError()
        except ValueError:return await i.response.send_message('Enter valid dates, YYYY-MM-DD, with the last day on or after the first and not in the past.',ephemeral=True)
        await i.response.defer(ephemeral=True)
        review=H.channel(i.guild,'leave-review')
        if not review:return await i.followup.send('Leadership must run /setup_hospital first.',ephemeral=True)
        with db() as d:
            cur=d.execute('INSERT INTO leave_requests (guild,member,starts,ends,reason) VALUES (?,?,?,?,?)',(i.guild.id,i.user.id,starts.timestamp(),ends,self.reason.value));rid=cur.lastrowid
        e=discord.Embed(title=f'🌴 Leave request #{rid}',description=f'{i.user.mention}\n{self.start.value} through {self.end.value} • America/New_York\nReason: {self.reason.value}',color=0xb71c1c);e.set_footer(text=f'STB leave:{rid}')
        await review.send(embed=e,view=LeaveReview())
        await i.followup.send(f'Leave request #{rid} submitted privately to leadership and HR.',ephemeral=True)
class LeavePanel(discord.ui.View):
    def __init__(self):super().__init__(timeout=None)
    @discord.ui.button(label='Request Leave',emoji='🌴',custom_id='stb:leave:new',style=discord.ButtonStyle.primary)
    async def request(self,i,button):
        if not H.staff_member(i.user):return await i.response.send_message('Hospital staff required.',ephemeral=True)
        await i.response.send_modal(LeaveForm())
class LeaveReview(discord.ui.View):
    def __init__(self):super().__init__(timeout=None)
    async def decide(self,i,approved):
        if not H.hours_admin(i.user):return await i.response.send_message('Leadership, EMS Chief or HR required.',ephemeral=True)
        if not i.message.embeds:return await i.response.send_message('Invalid request.',ephemeral=True)
        footer=i.message.embeds[0].footer.text or ''
        try:rid=int(footer.split(':')[-1])
        except ValueError:return await i.response.send_message('Invalid request.',ephemeral=True)
        await i.response.defer(ephemeral=True)
        async with lock(('leave',rid)):
            with db() as d:
                row=d.execute('SELECT guild,member,status FROM leave_requests WHERE id=?',(rid,)).fetchone()
                if not row or row[0]!=i.guild.id or row[2]!='pending':return await i.followup.send('Already reviewed or invalid.',ephemeral=True)
                status='approved' if approved else 'denied';d.execute('UPDATE leave_requests SET status=?,reviewer=? WHERE id=?',(status,i.user.id,rid))
            e=i.message.embeds[0];e.add_field(name='Decision',value=f'{status.upper()} by {i.user.mention}')
            await i.message.edit(embed=e,view=None)
            sent=await dm(row[1],i.guild,f'St. Bernards leave request #{rid}: {status.upper()}. Contact hospital leadership with questions.')
            await apply_leave(i.guild,time.time())
            await i.followup.send(f'Request {status}.'+(' Member DM sent.' if sent else ' Member DMs are closed; notify them privately.'),ephemeral=True)
    @discord.ui.button(label='Approve',emoji='✅',custom_id='stb:leave:approve',style=discord.ButtonStyle.success)
    async def approve(self,i,button):await self.decide(i,True)
    @discord.ui.button(label='Deny',emoji='❌',custom_id='stb:leave:deny',style=discord.ButtonStyle.danger)
    async def deny(self,i,button):await self.decide(i,False)
async def apply_leave(g,now):
    leave=H.role(g,'On Leave')
    if not leave:return
    with db() as d:rows=d.execute('SELECT id,member,starts,ends,applied FROM leave_requests WHERE guild=? AND status="approved"',(g.id,)).fetchall()
    for rid,uid,start,end,applied in rows:
        if not (start<=now<end or applied==1 and now>=end):continue
        try:member=g.get_member(uid) or await g.fetch_member(uid)
        except discord.NotFound:continue
        if start<=now<end and applied==0:
            already=leave in member.roles
            if not already:await member.add_roles(leave,reason='Approved hospital leave')
            with db() as d:d.execute('UPDATE leave_requests SET applied=? WHERE id=?',(2 if already else 1,rid))
            started=H.duty_end(g.id,uid,H.bot.user.id,'Approved leave began',now)
            if started is not None:
                clock=H.channel(g,'clock-in-out')
                if clock:await clock.send(f'🌴 <@{uid}> automatically clocked out as approved leave began. Start: <t:{int(started)}:f> • End: <t:{int(now)}:f> • Duration: {H.duration_label(now-started)}.')
        elif now>=end and applied==1:
            # Keep role until any other approved leave ends; never remove a preexisting manual leave role.
            ongoing=any(r[1]==uid and r[2]<=now<r[3] for r in rows)
            if not ongoing:
                await member.remove_roles(leave,reason='Approved hospital leave ended')
                with db() as d:d.execute('UPDATE leave_requests SET applied=3 WHERE member=? AND guild=? AND applied=1 AND ends<=?',(uid,g.id,now))
async def reminder_tick(g,now):
    with db() as d:rows=d.execute('SELECT channel FROM appointments WHERE guild=? AND status="confirmed" AND scheduled>?',(g.id,now)).fetchall()
    for (cid,) in rows:
        async with lock(('appt',cid)):
            r=appointment(cid);ch=g.get_channel(cid)
            if not r or r['status']!='confirmed':continue
            if not ch:
                with db() as d:d.execute('UPDATE appointments SET status="closed" WHERE channel=?',(cid,))
                continue
            delta=r['scheduled']-now
            field='quarter_sent' if 0<delta<=900 else 'hour_sent' if 900<delta<=3600 else None
            if not field or r[field]:continue
            minutes=15 if field=='quarter_sent' else 60
            text=f'⏰ St. Bernards appointment reminder: {r["service"]} at <t:{int(r["scheduled"])}:F> (<t:{int(r["scheduled"])}:R>). Ticket: {ch.jump_url}'
            await ch.send(text)
            await dm(r['patient'],g,text)
            if r['provider'] and r['provider']!=r['patient']:await dm(r['provider'],g,text)
            with db() as d:
                d.execute(f'UPDATE appointments SET {field}=1 WHERE channel=? AND revision=?',(cid,r['revision']))
                if field=='quarter_sent':d.execute('UPDATE appointments SET hour_sent=1 WHERE channel=?',(cid,))
async def weekly_recognition(g,now):
    current=datetime.fromtimestamp(now,ZONE)
    sunday=(current-timedelta(days=(current.weekday()+1)%7)).replace(hour=19,minute=0,second=0,microsecond=0)
    if sunday>current:sunday-=timedelta(days=7)
    start=sunday-timedelta(days=7)
    marker=f'recognition:{g.id}:{sunday.date()}'
    with db() as d:
        if d.execute('SELECT value FROM workflow_state WHERE key=?',(marker,)).fetchone():return
        rows=d.execute('SELECT member,reason FROM recognition WHERE guild=? AND created>=? AND created<? ORDER BY created',(g.id,start.timestamp(),sunday.timestamp())).fetchall()
    ch=H.channel(g,'staff-announcements')
    if not ch:return
    if rows:
        grouped={}
        for uid,reason in rows:grouped.setdefault(uid,[]).append(reason)
        descriptions=[];part=''
        for uid,reasons in grouped.items():
            line=f'🏅 <@{uid}>\n'+'\n'.join('• '+reason for reason in reasons)+'\n\n'
            # Cap each staff recap to embed length; original nominations remain in announcements/database.
            line=line[:3000]
            if len(part)+len(line)>3500:descriptions.append(part);part=''
            part+=line
        if part:descriptions.append(part)
        for num,description in enumerate(descriptions,1):
            pagekey=marker+f':page:{num}'
            with db() as d:sent=d.execute('SELECT value FROM workflow_state WHERE key=?',(pagekey,)).fetchone()
            if sent:continue
            e=discord.Embed(title=f'🏅 WEEKLY STAFF SPOTLIGHT • Week ending {sunday.date()}',description=description,color=0xffc107);e.set_footer(text='Recognized for patient RP, teamwork and supporting trainees')
            await ch.send(embed=e)
            with db() as d:d.execute('INSERT OR REPLACE INTO workflow_state VALUES (?,?)',(pagekey,'sent'))
    with db() as d:d.execute('INSERT OR REPLACE INTO workflow_state VALUES (?,?)',(marker,'complete'))
async def setup(g):
    cat=discord.utils.get(g.categories,name='🗂 PATIENT RECORDS')
    if not cat:cat=await g.create_category('🗂 PATIENT RECORDS',overwrites=H.permissions(g,H.LEAD))
    else:await cat.edit(overwrites=H.permissions(g,H.LEAD))
    for service,(rolename,name,emoji) in SPECS.items():
        p=H.permissions(g,[rolename])
        forum=next((f for f in g.forums if H.base_name(f.name)==name),None)
        if not forum:forum=await g.create_forum(f'{emoji}・{name}',category=cat,overwrites=p,available_tags=[discord.ForumTag(name=n) for n in ['Visit Report','Follow-Up','Assessment']])
        else:await forum.edit(category=cat,overwrites=p,sync_permissions=False)
        marker=f'record-panel:{g.id}:{service}'
        with db() as d:entry=d.execute('SELECT value FROM workflow_state WHERE key=?',(marker,)).fetchone()
        thread=None
        if entry:
            try:thread=await g.fetch_channel(int(entry[0]))
            except discord.NotFound:pass
        if thread:
            if thread.archived:await thread.edit(archived=False)
        else:
            e=discord.Embed(title=f'{emoji} {service} | Create patient reports',description='Click below to create a structured visit report. Each report becomes a forum post. Use fictional character information only. This forum is visible to the matching specialty and hospital leadership; server administrators always retain access. Tags organize posts inside this specialty; tags do not grant permissions.',color=0xb71c1c)
            created=await forum.create_thread(name='📌 Start here • New patient report',embed=e,view=RecordButton(service),auto_archive_duration=10080)
            with db() as d:d.execute('INSERT OR REPLACE INTO workflow_state VALUES (?,?)',(marker,str(created.thread.id)))
    admin=discord.utils.get(g.categories,name='👑 ADMINISTRATION')
    review=H.channel(g,'leave-review')
    p=H.permissions(g,H.LEAD+['EMS Chief','Human Resources'])
    if not review:review=await g.create_text_channel('🌴・leave-review',category=admin,overwrites=p)
    else:await review.edit(overwrites=p)
    leave=H.channel(g,'leave-requests')
    marker='STB leave requests v1'
    existing=[m async for m in leave.history(limit=100)]
    if not any(m.author==H.bot.user and m.embeds and m.embeds[0].footer.text==marker for m in existing):
        e=discord.Embed(title='🌴 REQUEST TIME OFF',description='Submit dates and a private reason. Leadership/HR approve or deny it. Approved leave automatically applies On Leave during those dates, then removes the bot-applied role afterward. DMs notify you when possible; /my_leave shows your decisions if DMs are closed.',color=0xb71c1c);e.set_footer(text=marker)
        await leave.send(embed=e,view=LeavePanel())
    # Private reasons belong only in the modal/review channel.
    p=H.permissions(g,['Hospital Staff']+H.DUTY_RANKS+H.training.TRAINEES)
    for who,ow in p.items():
        if who!=g.me:ow.send_messages=False
    await leave.edit(overwrites=p)
    for c in g.text_channels:
        t=(c.topic or '').split(':')
        if len(t)>=5 and t[0]=='stb-ticket' and t[2]=='open' and t[3]=='appointment' and t[4] in SPECS:
            await attach_appointment(c,int(t[1]),t[4])
    signoffs=H.channel(g,'training-sign-offs')
    marker='STB trainer signoff guide v1'
    existing=[m async for m in signoffs.history(limit=100)]
    if not any(m.author==H.bot.user and m.embeds and m.embeds[0].footer.text==marker for m in existing):
        e=discord.Embed(title='✅ TRAINER SIGN-OFFS',description='Complete supervised hands-on RP training first. Trainer uses /trainer_signoff with member, course and notes. Then use /enroll_training. A career change requires an approved application before training. Trainers must verify that approval; the bot does not decide applications. Trainees cannot sign themselves off.',color=0xb71c1c);e.set_footer(text=marker)
        await signoffs.send(embed=e)
def register_views():
    for service in SPECS:H.bot.add_view(RecordButton(service))
    H.bot.add_view(AppointmentControls());H.bot.add_view(LeavePanel());H.bot.add_view(LeaveReview())
def start():
    if not workflow_loop.is_running():workflow_loop.start()
@tasks.loop(minutes=1)
async def workflow_loop():
    g=H.bot.get_guild(H.GUILD_ID)
    if not g:return
    for task in [reminder_tick,apply_leave,weekly_recognition]:
        try:await task(g,time.time())
        except Exception:logging.exception('Workflow task failed: %s',task.__name__)
@workflow_loop.before_loop
async def before_workflows():await H.bot.wait_until_ready()
def install(h):
    global H
    H=h
    @h.bot.tree.command(name='trainer_signoff',description='Trainer: record approved hands-on training before modules and enrollment')
    @app_commands.guild_only()
    @app_commands.choices(course=h.COURSE_CHOICES)
    async def trainer_signoff(i,member:discord.Member,course:app_commands.Choice[str],notes:str):
        if not h.instructor(i.user):return await i.response.send_message('Training Instructor or hospital leadership required.',ephemeral=True)
        if member.id==i.user.id:return await i.response.send_message('A different trainer must assess and sign you off.',ephemeral=True)
        if len(notes)>700:return await i.response.send_message('Keep notes under 700 characters.',ephemeral=True)
        await i.response.defer(ephemeral=True)
        async with h.locks.setdefault(('training',member.id),asyncio.Lock()):
            with db() as d:
                entry=d.execute('SELECT started FROM enrollments WHERE guild=? AND member=? AND course=?',(i.guild.id,member.id,course.value)).fetchone()
                enrolled=entry[0] if entry else 0
                d.execute('INSERT INTO trainer_signoffs (guild,member,course,trainer,signed,notes,enrolled) VALUES (?,?,?,?,?,?,?)',(i.guild.id,member.id,course.value,i.user.id,time.time(),notes,enrolled))
            ch=h.channel(i.guild,'training-sign-offs')
            if ch:await ch.send(f'✅ {member.mention} • {h.training.COURSES[course.value][0]} • supervised training approved by {i.user.mention}\n{notes}')
            await i.followup.send('Trainer sign-off saved. '+('Existing enrollment unlocked.' if entry else 'You may now enroll this member with /enroll_training.'),ephemeral=True)
    @h.bot.tree.command(name='my_leave',description='Staff: privately view your leave requests and decisions')
    @app_commands.guild_only()
    async def my_leave(i):
        with db() as d:rows=d.execute('SELECT id,starts,ends,status FROM leave_requests WHERE guild=? AND member=? ORDER BY id DESC LIMIT 15',(i.guild.id,i.user.id)).fetchall()
        text='\n'.join(f'#{rid} • {datetime.fromtimestamp(a,ZONE).date()} to {datetime.fromtimestamp(b-1,ZONE).date()} • **{status.upper()}**' for rid,a,b,status in rows) or 'No leave requests.'
        await i.response.send_message(text,ephemeral=True)
    @h.bot.tree.command(name='recognize_staff',description='Leadership/trainer: recognize a staff member for patient RP, teamwork or helping trainees')
    @app_commands.guild_only()
    async def recognize_staff(i,member:discord.Member,reason:str):
        if not (h.hours_admin(i.user) or h.instructor(i.user)):return await i.response.send_message('Leadership, HR, EMS Chief or Training Instructor required.',ephemeral=True)
        if not h.staff_member(member):return await i.response.send_message('Choose a hospital staff member.',ephemeral=True)
        if len(reason)>500:return await i.response.send_message('Keep recognition under 500 characters.',ephemeral=True)
        await i.response.defer(ephemeral=True)
        ch=h.channel(i.guild,'staff-announcements')
        if not ch:return await i.followup.send('Run /setup_hospital first.',ephemeral=True)
        e=discord.Embed(title='🏅 STAFF SHOUTOUT',description=f'{member.mention}\n\n{reason}',color=0xffc107);e.set_footer(text=f'Recognized by {i.user.display_name}')
        await ch.send(embed=e)
        with db() as d:d.execute('INSERT INTO recognition (guild,member,actor,reason,created) VALUES (?,?,?,?,?)',(i.guild.id,member.id,i.user.id,reason,time.time()))
        await i.followup.send('Shoutout posted and included in the next weekly staff spotlight (Sunday, 7 PM New York time).',ephemeral=True)
    @h.bot.tree.command(name='reassign_appointment',description='Leadership: reassign the current appointment to a matching provider')
    @app_commands.guild_only()
    async def reassign_appointment(i,provider:discord.Member):
        r=appointment(i.channel.id)
        if not h.hours_admin(i.user) or not r:return await i.response.send_message('Use this inside an appointment ticket as leadership/HR/EMS Chief.',ephemeral=True)
        if not specialty_staff(provider,r['service']):return await i.response.send_message('Provider must have the matching specialty role.',ephemeral=True)
        if not i.channel.permissions_for(provider).view_channel:return await i.response.send_message('Provider must already be permitted to view this ticket.',ephemeral=True)
        with db() as d:d.execute('UPDATE appointments SET provider=? WHERE channel=?',(provider.id,i.channel.id))
        await i.response.send_message(f'🩺 Provider reassigned to {provider.mention}.')
