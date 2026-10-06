import os, asyncio, logging, io, json, time, random
import training
import features
import sys
import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
load_dotenv()
GUILD_ID = int(os.environ['GUILD_ID'])
LEAD = ['Hospital Director', 'Deputy Director', 'Chief of Medicine']
ROLES = LEAD + ['EMS Chief', 'Human Resources', 'Department Head', 'Attending Physician', 'Resident Physician', 'Nurse Practitioner', 'Registered Nurse', 'Paramedic', 'EMT', 'Medical Intern', 'Receptionist', 'Family Medicine', 'OB-GYN', 'Therapist', 'Pediatrician', 'Physical Therapist', 'Hospital Staff', 'On Leave', 'Patient']
SERVICES = ['Family Medicine', 'OB-GYN', 'Therapy', 'Pediatrician', 'Physical Therapy']
LAYOUT = [
 ('📌 START HERE', None, ['welcome', 'hospital-rules', 'announcements', 'about-st-bernards', 'meet-the-staff', 'patient-guide'], []),
 ('💬 PATIENT LOUNGE', None, ['waiting-room', 'hospital-moments', 'suggestions', 'patient-feedback'], ['Waiting Room']),
 ('📅 APPOINTMENT CENTER', None, ['book-an-appointment', 'hours-and-availability', 'appointment-information'], []),
 ('💼 CAREERS & APPLICATIONS', None, ['work-at-st-bernards', 'apply-here', 'hiring-faq'], []),
 ('🎫 PATIENT SUPPORT', None, ['contact-the-hospital', 'request-records'], []),
 ('🔒 STAFF HUB', ['Hospital Staff'], ['staff-announcements', 'staff-chat', 'staff-roster', 'clock-in-out', 'shift-schedule', 'leave-requests', 'shift-coverage', 'staff-resources'], []),
 ('🚑 EMS OPERATIONS', ['EMS Chief', 'Paramedic', 'EMT'], ['dispatch', 'unit-status', 'incident-reports', 'patient-handoffs', 'major-incident-briefings'], ['Dispatch', 'EMS Radio 1', 'EMS Radio 2']),
 ('🩺 MEDICAL DEPARTMENTS', ['Hospital Staff'], ['department-hub', 'clinical-protocols', 'supply-requests', 'case-discussions'], ['Consultation Room 1', 'Consultation Room 2', 'Therapy Office']),
 ('👑 ADMINISTRATION', LEAD + ['Human Resources'], ['leadership-chat', 'application-review', 'staff-management', 'disciplinary-records', 'ticket-transcripts', 'bot-logs'], ['Leadership Office']),
 ('📁 PRIVATE TICKETS', LEAD, [], [])]
READONLY = {'welcome','hospital-rules','announcements','about-st-bernards','meet-the-staff','patient-guide','book-an-appointment','hours-and-availability','appointment-information','work-at-st-bernards','apply-here','hiring-faq','contact-the-hospital','request-records','staff-announcements','staff-roster','staff-resources','clinical-protocols','training-materials','training-sign-offs','ticket-transcripts','bot-logs'}
ROLE_ICONS = {'Hospital Director':'👑','Deputy Director':'⭐','Chief of Medicine':'⚕️','EMS Chief':'🚑','Human Resources':'💼','Department Head':'📋','Attending Physician':'🩺','Resident Physician':'🥼','Nurse Practitioner':'💉','Registered Nurse':'🩹','Paramedic':'🚨','EMT':'🚑','Medical Intern':'🎓','Receptionist':'☎️','Family Medicine':'🏡','OB-GYN':'🤰','Therapist':'🧠','Pediatrician':'🧸','Physical Therapist':'🦽','Hospital Staff':'🏥','On Leave':'🌴','Patient':'❤️'}
CHANNEL_ICONS = {'welcome':'👋','hospital-rules':'📋','announcements':'📢','about-st-bernards':'🏥','meet-the-staff':'🩺','patient-guide':'❓','waiting-room':'💬','hospital-moments':'📸','suggestions':'💡','patient-feedback':'⭐','book-an-appointment':'📅','hours-and-availability':'🕒','appointment-information':'📌','work-at-st-bernards':'💼','apply-here':'📝','hiring-faq':'❓','contact-the-hospital':'🎫','request-records':'📄','staff-announcements':'📢','staff-chat':'💬','staff-roster':'📋','clock-in-out':'⏱️','shift-schedule':'📅','leave-requests':'🌴','shift-coverage':'🤝','staff-resources':'📚','dispatch':'📟','unit-status':'🚑','incident-reports':'📝','patient-handoffs':'🔄','major-incident-briefings':'🚨','department-hub':'🩺','clinical-protocols':'📋','supply-requests':'📦','case-discussions':'🔬','training-materials':'📚','training-sign-offs':'✅','practice-scenarios':'🧪','leadership-chat':'👑','application-review':'📂','staff-management':'📋','disciplinary-records':'⚠️','ticket-transcripts':'🗃️','bot-logs':'🤖'}
ROLES.extend(['Training Instructor']+training.TRAINEES)
CHANNEL_ICONS['unit-status']='🟢'
CHANNEL_ICONS['training-results']='📊'
READONLY.add('training-results')
ROLE_ICONS.update({'Training Instructor':'📚',**{n:'🎓' for n in training.TRAINEES}})
for key,c in training.COURSES.items():
    CHANNEL_ICONS.update({f'{key}-modules':'📚',f'{key}-exam':'📝'})
    READONLY.update({f'{key}-modules',f'{key}-exam'})
def base_name(name):
    return name.split('・',1)[-1].strip()
def pretty_role(name): return f'{ROLE_ICONS[name]}・{name}'
def pretty_channel(name): return f'{CHANNEL_ICONS.get(name,"🔊")}・{name}'
def role(g, name): return next((r for r in g.roles if base_name(r.name)==name),None)
def channel(g, name): return next((c for c in g.text_channels if base_name(c.name)==name),None)
def permissions(g, names=None):
    p = {g.default_role: discord.PermissionOverwrite(view_channel=names is None), g.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, read_message_history=True)}
    if names is not None:
        for n in set(names + LEAD):
            if role(g,n): p[role(g,n)] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, connect=True)
    return p
locks = {}
class HospitalBot(commands.Bot):
    async def setup_hook(self):
        features.register_views()
        self.add_view(DutyControls())
        for key,c in training.COURSES.items():
            for index in range(len(c[4])): self.add_view(ModuleView(key,index))
        self.add_view(Panel('appointment')); self.add_view(Panel('application')); self.add_view(Panel('support')); self.add_view(CloseView())
        target = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=target)
        await self.tree.sync(guild=target)
intents=discord.Intents.default(); intents.members=True; intents.message_content=True
bot=HospitalBot(command_prefix=commands.when_mentioned, intents=intents, allowed_mentions=discord.AllowedMentions.none())
class TicketForm(discord.ui.Modal):
    def __init__(self, kind, service):
        super().__init__(title=service[:45]); self.kind=kind; self.service=service
        labels = ['Character name', 'Desired position', 'RP experience', 'Availability and timezone', 'Why join? How would you help a upset patient?'] if kind=='application' else ['Character name', 'Brief reason / request (fictional RP only)', 'Preferred date and time / timezone', 'Availability / additional details']
        for label in labels:
            self.add_item(discord.ui.TextInput(label=label[:45], max_length=700, style=discord.TextStyle.paragraph if 'reason' in label.lower() or 'Why' in label else discord.TextStyle.short))
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True)
        async with locks.setdefault(('ticket',i.user.id),asyncio.Lock()):
            g=i.guild
            existing=next((c for c in g.text_channels if c.topic and c.topic.startswith(f'stb-ticket:{i.user.id}:open:')),None)
            if existing: return await i.followup.send(f'You already have an open ticket: {existing.mention}',ephemeral=True)
            names=LEAD+(['Human Resources'] if self.kind=='application' else ['Receptionist'] if self.service!='Therapy' else [])
            specialty={'Therapy':'Therapist','Physical Therapy':'Physical Therapist'}.get(self.service,self.service)
            if self.kind=='appointment': names.append(specialty)
            p=permissions(g,names); p[i.user]=discord.PermissionOverwrite(view_channel=True,send_messages=True,read_message_history=True,attach_files=True)
            cat=discord.utils.get(g.categories,name='📁 PRIVATE TICKETS')
            if not cat: return await i.followup.send('An administrator must run /setup_hospital first.',ephemeral=True)
            c=await g.create_text_channel(f'{self.kind}-{i.user.id}',category=cat,overwrites=p,topic=f'stb-ticket:{i.user.id}:open:{self.kind}:{self.service}')
            embed=discord.Embed(title=self.service,color=0xb71c1c,description='St. Bernards • Chiraq Chronicles • Fictional medical RP')
            for f in self.children: embed.add_field(name=f.label,value=str(f.value),inline=False)
            await c.send(content=i.user.mention,embed=embed,view=CloseView())
            if self.kind=='appointment':await features.attach_appointment(c,i.user.id,self.service)
            await i.followup.send(f'Your private ticket is ready: {c.mention}',ephemeral=True)
class Choice(discord.ui.Select):
    def __init__(self,kind):
        self.kind=kind
        choices=SERVICES if kind=='appointment' else ['Hospital Application'] if kind=='application' else ['General Support','Appointment Change','Private Concern','Medical Records Request']
        super().__init__(placeholder='Choose your service',custom_id=f'stb:{kind}',options=[discord.SelectOption(label=x,value=x,emoji={'Family Medicine':'🏡','OB-GYN':'🤰','Therapy':'🧠','Pediatrician':'🧸','Physical Therapy':'🦽','Hospital Application':'💼','General Support':'🎫','Appointment Change':'📅','Private Concern':'🔒','Medical Records Request':'📄'}[x]) for x in choices])
    async def callback(self,i): await i.response.send_modal(TicketForm(self.kind,self.values[0]))
class Panel(discord.ui.View):
    def __init__(self,kind): super().__init__(timeout=None); self.add_item(Choice(kind))
class CloseView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label='Close & archive ticket',style=discord.ButtonStyle.danger,custom_id='stb:close')
    async def close(self,i,button):
        c=i.channel; t=(c.topic or '').split(':')
        if len(t)<5 or t[0]!='stb-ticket': return await i.response.send_message('This is not a hospital ticket.',ephemeral=True)
        permitted=i.user.guild_permissions.administrator or i.user.id==int(t[1]) or any(base_name(r.name) in LEAD+['Human Resources','Receptionist']+SERVICES+['Therapist','Physical Therapist'] for r in i.user.roles)
        if not permitted: return await i.response.send_message('You cannot close this ticket.',ephemeral=True)
        await i.response.defer(ephemeral=True)
        async with locks.setdefault(('close',c.id),asyncio.Lock()):
            log=channel(i.guild,'ticket-transcripts')
            if not log:
                return await i.followup.send('Transcript channel missing. Run /setup_hospital first. Ticket kept.',ephemeral=True)
            original_overwrites=c.overwrites
            try:
                frozen={target:discord.PermissionOverwrite.from_pair(*ow.pair()) for target,ow in original_overwrites.items()}
                frozen.setdefault(i.guild.default_role,discord.PermissionOverwrite()).send_messages=False
                for target,ow in frozen.items():
                    ow.send_messages=(target.id==i.guild.me.id)
                await c.edit(overwrites=frozen)
                messages=[m async for m in c.history(limit=None,oldest_first=True)]
                chunks=[]; text=f'ST. BERNARDS TICKET {c.id}\nService: {t[4]}\nPatient ID: {t[1]}\nClosed by: {i.user.id}\n\n'
                attachments=[]
                for m in messages:
                    line=f'[{m.created_at.isoformat()}] {m.author} ({m.author.id})\n{m.content}\n'
                    for e in m.embeds:
                        line+=json.dumps(e.to_dict(),ensure_ascii=False)+'\n'
                    for a in m.attachments:
                        line+=f'Attachment: {a.filename} ({a.size} bytes) {a.url}\n'
                        attachments.append(a)
                    text+=line+'\n'
                raw=text.encode('utf-8')
                limit=min(i.guild.filesize_limit-1024,7_000_000)
                chunks=[raw[x:x+limit] for x in range(0,len(raw),limit)]
                # Export must succeed before deletion. Download attachment bytes as well as recording links.
                for num,chunk in enumerate(chunks,1):
                    await log.send(content=f'Ticket {c.id} • {t[4]} • transcript {num}/{len(chunks)}',file=discord.File(io.BytesIO(chunk),filename=f'ticket-{c.id}-{num}.txt'))
                for a in attachments:
                    data=await a.read()
                    if len(data)>i.guild.filesize_limit:
                        raise ValueError('Attachment exceeds upload limit; ticket preserved')
                    await log.send(content=f'Ticket {c.id} • attachment copy',file=discord.File(io.BytesIO(data),filename=a.filename))
                latest=[m async for m in c.history(limit=1)]
                if latest and (not messages or latest[0].id!=messages[-1].id):
                    raise ValueError('New message arrived during export; retry')
                await log.send(f'✅ Ticket {c.id} • {t[4]} • complete archive: {len(messages)} messages, {len(attachments)} attachments. Closed by {i.user.mention}.')
            except Exception:
                logging.exception('Transcript save failed')
                await c.edit(overwrites=original_overwrites)
                return await i.followup.send('Could not save the complete transcript. The ticket was kept; fix permissions or attachment upload limits and retry.',ephemeral=True)
            await i.followup.send('Transcript saved in ticket-transcripts. Removing the ticket channel.',ephemeral=True)
            try:
                await c.delete(reason=f'Ticket {c.id} archived successfully')
                with features.db() as d:d.execute('UPDATE appointments SET status="closed" WHERE channel=?',(c.id,))
            except discord.HTTPException:
                await c.edit(overwrites=original_overwrites)
                await i.followup.send('Transcript saved, but channel deletion failed. Check Manage Channels and retry.',ephemeral=True)
@bot.tree.command(name='setup_hospital',description='Create the St. Bernards hospital roles, channels and ticket panels')
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
@app_commands.checks.has_permissions(administrator=True)
async def setup(i):
    await i.response.defer(ephemeral=True,thinking=True)
    async with locks.setdefault('setup',asyncio.Lock()):
        g=i.guild
        if g.id!=GUILD_ID: return await i.followup.send('Wrong server.',ephemeral=True)
        for name in ROLES:
            existing_role=role(g,name)
            if existing_role:
                if existing_role.name!=pretty_role(name): await existing_role.edit(name=pretty_role(name))
            else: await g.create_role(name=pretty_role(name),color=discord.Color(0xb71c1c if name!='Patient' else 0x90caf9),permissions=discord.Permissions.none(),reason='Hospital setup')
        # Highest named rank first. Bot role must remain above managed roles.
        # Keep the server's existing role order; bulk moves may cross the bot hierarchy.
        for catname,names,texts,voices in LAYOUT:
            cat=discord.utils.get(g.categories,name=catname)
            if not cat: cat=await g.create_category(catname,overwrites=permissions(g,names))
            for name in texts:
                existing_channel=next((c for c in cat.channels if base_name(c.name)==name),None)
                if existing_channel:
                    if existing_channel.name!=pretty_channel(name): await existing_channel.edit(name=pretty_channel(name))
                    continue
                p=permissions(g,names)
                if name in READONLY:
                    for target,overwrite in p.items():
                        if target!=g.me: overwrite.send_messages=False
                if name=='department-hub':
                    await g.create_forum(pretty_channel(name),category=cat,overwrites=p,available_tags=[discord.ForumTag(name=s) for s in SERVICES])
                else: await g.create_text_channel(pretty_channel(name),category=cat,overwrites=p)
            for name in voices:
                existing_voice=next((c for c in cat.voice_channels if base_name(c.name)==name),None)
                if existing_voice:
                    if existing_voice.name!=pretty_channel(name): await existing_voice.edit(name=pretty_channel(name))
                else: await g.create_voice_channel(pretty_channel(name),category=cat,overwrites=permissions(g,names))
        panels=[('book-an-appointment','appointment','Book an appointment'),('apply-here','application','Work at St. Bernards'),('contact-the-hospital','support','Contact the hospital'),('request-records','support','Request fictional RP records')]
        for name,kind,title in panels:
            c=channel(g,name)
            marker=f'STB panel: {kind}'
            if not any(m.author==bot.user and m.embeds and m.embeds[0].footer.text==marker for m in [message async for message in c.history(limit=100)]):
                e=discord.Embed(title=title,description='Select below to open a private ticket. Use fictional character information only. One open ticket per person.',color=0xb71c1c); e.set_footer(text=marker)
                await c.send(embed=e,view=Panel(kind))
        starters={'welcome':'Welcome to **St. Bernards Hospital | Chiraq Chronicles EMS**! Read hospital-rules, visit patient-guide, and book your appointment. Everyone receives the Patient role.', 'hospital-rules':'Respect staff and patients. Keep all medical information fictional and in private tickets. No harassment, spam, or metagaming. Follow Chiraq Chronicles rules. This hospital is for roleplay.', 'about-st-bernards':'Care for the community: Family Medicine, OB-GYN, Therapy, Pediatrics, Physical Therapy, and emergency medical services.', 'patient-guide':'Choose a service in book-an-appointment. Submit your character name and availability. Staff will confirm your time inside the ticket. For other questions use contact-the-hospital.', 'appointment-information':'Provide your timezone. Appointment requests require staff confirmation. Need to change or cancel? Use your open ticket or contact-the-hospital.', 'work-at-st-bernards':'We are recruiting medical providers, nurses, EMS crews, interns and reception. Open an application in apply-here. HR will arrange your interview.', 'hiring-faq':'Apply with fictional character information, your desired position, RP experience, and availability. New hires receive rank, specialty, and Hospital Staff roles from leadership.'}
        for name,body in starters.items():
            c=channel(g,name)
            if not any(m.author==bot.user for m in [message async for message in c.history(limit=1)]): await c.send(body)
        await setup_training(g)
        await setup_duty(g)
        await features.setup(g)
        # Transcripts are leadership-only, including therapy records.
        await channel(g,'ticket-transcripts').edit(overwrites=permissions(g,LEAD))
        await i.followup.send('Hospital setup complete! Assign Hospital Staff plus rank and specialty to employees. Keep my bot role above Patient. Use /assign_patients for existing members. Rerunning setup fills missing items; existing permissions are not overwritten.',ephemeral=True)
@bot.tree.command(name='assign_patients',description='Give Patient to existing human members')
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
@app_commands.checks.has_permissions(administrator=True)
async def assign(i):
    await i.response.defer(ephemeral=True)
    r=role(i.guild,'Patient')
    if not r: return await i.followup.send('Run /setup_hospital first.',ephemeral=True)
    count=0
    async for m in i.guild.fetch_members(limit=None):
        if not m.bot and r not in m.roles: await m.add_roles(r); count+=1
    await i.followup.send(f'Patient assigned to {count} members.',ephemeral=True)
@bot.event
async def on_member_join(m):
    if m.guild.id!=GUILD_ID or m.bot:return
    r=role(m.guild,'Patient')
    if r: await m.add_roles(r,reason='Automatic patient role')
@bot.event
async def on_ready():
    print(f'St. Bernards bot online as {bot.user}. Run /setup_hospital.')
    if not refresh_duty.is_running():refresh_duty.start()
    features.start()
@bot.tree.error
async def error(i,e):
    logging.error('Command failed',exc_info=(type(e),e,e.__traceback__))
    msg='Action failed. Check bot permissions and role hierarchy, then retry. No channels are deleted by setup.'
    if isinstance(e,app_commands.MissingPermissions):msg='Only server administrators can use that command.'
    if i.response.is_done(): await i.followup.send(msg,ephemeral=True)
    else: await i.response.send_message(msg,ephemeral=True)
@bot.tree.command(name='archive_ticket',description='Save transcript and remove the current hospital ticket, including old closed tickets')
@app_commands.guild_only()
async def archive_ticket(i):
    await CloseView().close.callback(i)

# Training commands and private tests
active_exams={}
def instructor(member):
    return member.guild_permissions.administrator or any(base_name(r.name) in LEAD+['Training Instructor'] for r in member.roles)
def ack_db():
    db=training.connect()
    db.execute('CREATE TABLE IF NOT EXISTS modules (guild INTEGER, member INTEGER, course TEXT, module INTEGER, PRIMARY KEY(guild,member,course,module))')
    return db
class ModuleView(discord.ui.View):
    def __init__(self,key,index):
        super().__init__(timeout=None)
        self.key=key;self.index=index
        button=discord.ui.Button(label='Mark module completed',emoji='✅',custom_id=f'stb:module:{key}:{index}')
        button.callback=self.complete;self.add_item(button)
    async def complete(self,i):
        entry=training.enrollment(i.guild.id,i.user.id)
        if not entry or entry[0]!=self.key or role(i.guild,training.COURSES[self.key][0]) not in i.user.roles:
            return await i.response.send_message('You must be enrolled in this course.',ephemeral=True)
        with ack_db() as db:db.execute('INSERT OR IGNORE INTO modules VALUES (?,?,?,?)',(i.guild.id,i.user.id,self.key,self.index))
        await i.response.send_message(f'Module {self.index+1} completed. Finish all three, then use /take_exam.',ephemeral=True)
async def setup_training(g):
    cat=discord.utils.get(g.categories,name='🎓 HOSPITAL ACADEMY')
    if not cat:cat=await g.create_category('🎓 HOSPITAL ACADEMY',overwrites=permissions(g,['Training Instructor']))
    else:await cat.edit(overwrites=permissions(g,['Training Instructor']))
    async def ensure_academy_channel(name,names,voice=False,readonly=True):
        p=permissions(g,names)
        if readonly:
            for who,ow in p.items():
                if who!=g.me:ow.send_messages=False
        candidates=g.voice_channels if voice else g.text_channels
        ch=next((c for c in candidates if base_name(c.name)==name),None)
        if ch:await ch.edit(name=pretty_channel(name),category=cat,overwrites=p,sync_permissions=False)
        elif voice:ch=await g.create_voice_channel(pretty_channel(name),category=cat,overwrites=p)
        else:ch=await g.create_text_channel(pretty_channel(name),category=cat,overwrites=p)
        return ch
    await ensure_academy_channel('training-results',['Training Instructor'])
    for name in ['training-materials','training-sign-offs','practice-scenarios']:
        await ensure_academy_channel(name,['Hospital Staff','Training Instructor'],readonly=name in READONLY)
    await ensure_academy_channel('Training Room',['Hospital Staff','Training Instructor'],voice=True,readonly=False)
    for key,c in training.COURSES.items():
        p=permissions(g,[c[0],'Training Instructor'])
        for who,ow in p.items():
            if who!=g.me:ow.send_messages=False
        ch=await ensure_academy_channel(f'{key}-modules',[c[0],'Training Instructor'])
        await ensure_academy_channel(f'{key}-exam',[c[0],'Training Instructor'])
        existing=[m async for m in ch.history(limit=100)]
        for index,(title,body) in enumerate(c[4]):
            marker=f'STB module: {key}:{index}:v1'
            if any(m.author==bot.user and m.embeds and m.embeds[0].footer.text==marker for m in existing):continue
            e=discord.Embed(title=f'📚 Module {index+1} • {title}',description=body,color=0xb71c1c)
            e.set_footer(text=marker)
            await ch.send(embed=e,view=ModuleView(key,index))
        ch=channel(g,f'{key}-exam')
        if not any(m.author==bot.user for m in [m async for m in ch.history(limit=1)]):
            await ch.send(f'📝 **{c[3]} track → {c[1]}**\nRead and mark all 3 modules completed, then use `/take_exam`. Pass with 80% (4 of 5). Failed tests can be retried after 1 hour. A pass replaces your clinical rank with {c[1]} and removes the trainee role. This is fictional RP training only. Leadership promotions are never awarded by tests.')
    # Remove only empty legacy training categories after successful moves.
    legacy={'🎓 TRAINING & DEVELOPMENT','📊 TRAINING ADMIN'}|{f'🎓 {c[0].upper()}' for c in training.COURSES.values()}
    for old in list(g.categories):
        if old.name in legacy and not old.channels:await old.delete(reason='Training consolidated into Hospital Academy')

def valid_learner(member,key):
    entry=training.enrollment(member.guild.id,member.id)
    return entry and entry[0]==key and role(member.guild,training.COURSES[key][0]) in member.roles
async def promote(g,member,key):
    c=training.COURSES[key]
    target=role(g,c[1]);trainee=role(g,c[0]);staff=role(g,'Hospital Staff')
    if not target or not trainee or not staff:raise ValueError('Run setup first')
    if any(base_name(r.name) in LEAD+['EMS Chief','Department Head']+(['Attending Physician'] if c[1]!='Attending Physician' else []) for r in member.roles):
        raise ValueError('Leadership or attending members cannot use trainee promotions')
    await member.add_roles(target,staff,reason='Passed hospital RP training')
    remove=[r for r in member.roles if base_name(r.name) in training.TRAINEES+training.CLINICAL and r!=target]
    if remove:await member.remove_roles(*remove,reason='Completed hospital RP career transition')
    training.clear(g.id,member.id)

class AnswerChoice(discord.ui.Select):
    def __init__(self,exam):
        self.exam=exam
        q=exam.questions[exam.index]
        order=list(range(len(q[1])));random.shuffle(order)
        super().__init__(placeholder='Choose your answer',options=[discord.SelectOption(label=q[1][n][:100],value=str(n)) for n in order])
    async def callback(self,i):
        e=self.exam
        if i.user.id!=e.member_id:return await i.response.send_message('This test belongs to another trainee.',ephemeral=True)
        async with locks.setdefault(('training',e.member_id),asyncio.Lock()):
            if e.finished or e.index!=self.exam_index:return await i.response.send_message('This question has already been answered.',ephemeral=True)
            await i.response.defer()
            member=await i.guild.fetch_member(e.member_id)
            if not valid_learner(member,e.key):
                e.finished=True;active_exams.pop(e.member_id,None)
                return await i.edit_original_response(content='Enrollment ended; this test has been canceled.',view=None)
            e.score+=int(int(self.values[0])==e.questions[e.index][2]);e.index+=1
            if e.index<len(e.questions):
                e.clear_items();choice=AnswerChoice(e);choice.exam_index=e.index;e.add_item(choice)
                return await i.edit_original_response(content=e.prompt(),view=e)
            e.finished=True;active_exams.pop(e.member_id,None);e.stop()
            score=round(100*e.score/len(e.questions));passed=score>=training.PASS_PERCENT
            training.attempt(i.guild.id,e.member_id,e.key,score,passed,time.time())
            result=f'Your score: **{score}%**. '
            if passed:
                try:
                    await promote(i.guild,member,e.key)
                    result+=f'🎉 You advanced to **{training.COURSES[e.key][1]}**! Your training access has been removed.'
                except Exception:
                    logging.exception('Promotion failed')
                    result+='Passed, but role assignment failed. Ask an instructor to use /complete_training after fixing bot role permissions.'
            else:result+='Keep studying. You can retry after 1 hour.'
            log=channel(i.guild,'training-results')
            if log:
                try: await log.send(f'{member.mention} • {e.key} • {score}% • {"PASS" if passed else "RETRY"}')
                except discord.HTTPException: logging.exception('Training audit message failed')
            await i.edit_original_response(content=result,view=None)
class Exam(discord.ui.View):
    def __init__(self,member,key):
        super().__init__(timeout=900)
        self.member_id=member.id;self.key=key;self.index=0;self.score=0;self.finished=False
        self.questions=list(training.COURSES[key][5]);random.shuffle(self.questions)
        choice=AnswerChoice(self);choice.exam_index=0;self.add_item(choice)
    def prompt(self):return f'📝 **{training.COURSES[self.key][1]} exam** • Question {self.index+1}/{len(self.questions)}\n{self.questions[self.index][0]}'
    async def on_timeout(self):
        self.finished=True
        if active_exams.get(self.member_id) is self:active_exams.pop(self.member_id,None)
        self.stop()

COURSE_CHOICES=[app_commands.Choice(name=f'{c[3]}: {c[0]} → {c[1]}',value=k) for k,c in training.COURSES.items()]
@bot.tree.command(name='enroll_training',description='Instructor: enroll a staff member in a private advancement course')
@app_commands.guild_only()
@app_commands.choices(course=COURSE_CHOICES)
async def enroll_training(i,member:discord.Member,course:app_commands.Choice[str]):
    if not instructor(i.user):return await i.response.send_message('Hospital leadership or Training Instructor required.',ephemeral=True)
    await i.response.defer(ephemeral=True)
    async with locks.setdefault(('training',member.id),asyncio.Lock()):
        c=training.COURSES[course.value];names={base_name(r.name) for r in member.roles}
        if member.bot or names.intersection(LEAD+['EMS Chief','Department Head','Attending Physician']):return await i.followup.send('Use training for clinical staff below attending, not leadership.',ephemeral=True)
        if course.value=='nurse' and 'Nurse Practitioner' in names:return await i.followup.send('They already hold an advanced nursing rank.',ephemeral=True)
        if c[1] in names:return await i.followup.send('They already hold the target rank.',ephemeral=True)
        if c[2] and not names.intersection(c[2]):return await i.followup.send('Required current rank: '+', '.join(c[2]),ephemeral=True)
        if course.value=='emt' and names.intersection(training.CLINICAL[2:]):return await i.followup.send('They already hold an advanced rank. Use a suitable next course.',ephemeral=True)
        signoff=features.unused_signoff(i.guild.id,member.id,course.value)
        if not signoff:return await i.followup.send('Complete supervised training first, then have a trainer use /trainer_signoff for this course.',ephemeral=True)
        tr=role(i.guild,c[0]);staff=role(i.guild,'Hospital Staff')
        if not tr or not staff:return await i.followup.send('Run /setup_hospital first.',ephemeral=True)
        await member.add_roles(tr,staff,reason='Enrolled in hospital RP training')
        old=[r for r in member.roles if base_name(r.name) in training.TRAINEES and r!=tr]
        if old:await member.remove_roles(*old)
        training.enroll(i.guild.id,member.id,course.value)
        features.consume_signoff(i.guild.id,member.id,course.value,signoff[0])
        with ack_db() as db:db.execute('DELETE FROM modules WHERE guild=? AND member=?',(i.guild.id,member.id))
        previous=active_exams.pop(member.id,None)
        if previous:previous.finished=True;previous.stop()
        await i.followup.send(f'{member.mention} enrolled as **{c[0]}**. Modules: {channel(i.guild,course.value+"-modules").mention}. Current rank stays until they pass.',ephemeral=True)
@bot.tree.command(name='take_exam',description='Trainee: take your enrolled course test privately')
@app_commands.guild_only()
async def take_exam(i):
    async with locks.setdefault(('training',i.user.id),asyncio.Lock()):
        entry=training.enrollment(i.guild.id,i.user.id)
        if not entry or not valid_learner(i.user,entry[0]):return await i.response.send_message('Ask an instructor to enroll you first.',ephemeral=True)
        if not features.enrollment_signed(i.guild.id,i.user.id,entry[0]):return await i.response.send_message('Your trainer must record hands-on training with /trainer_signoff before you take the test.',ephemeral=True)
        if i.user.id in active_exams:return await i.response.send_message('Finish your current exam. It expires after 15 minutes without activity.',ephemeral=True)
        wait=training.RETRY_SECONDS-(time.time()-entry[1])
        if wait>0:return await i.response.send_message(f'Retry in {int(wait//60)+1} minutes.',ephemeral=True)
        with ack_db() as db:count=db.execute('SELECT COUNT(*) FROM modules WHERE guild=? AND member=? AND course=?',(i.guild.id,i.user.id,entry[0])).fetchone()[0]
        if count<len(training.COURSES[entry[0]][4]):return await i.response.send_message('Read and mark all 3 modules completed first.',ephemeral=True)
        exam=Exam(i.user,entry[0]);active_exams[i.user.id]=exam
        await i.response.send_message(exam.prompt(),view=exam,ephemeral=True)
@bot.tree.command(name='complete_training',description='Instructor: finish a passed test whose automatic role update failed')
@app_commands.guild_only()
async def complete_training(i,member:discord.Member):
    if not instructor(i.user):return await i.response.send_message('Instructor or leadership required.',ephemeral=True)
    await i.response.defer(ephemeral=True)
    async with locks.setdefault(('training',member.id),asyncio.Lock()):
        entry=training.enrollment(i.guild.id,member.id)
        if not entry:return await i.followup.send('No active enrollment.',ephemeral=True)
        if not features.enrollment_signed(i.guild.id,member.id,entry[0]):return await i.followup.send('Trainer sign-off is required before completing this course.',ephemeral=True)
        with training.connect() as db:passed=db.execute('SELECT passed FROM attempts WHERE guild=? AND member=? AND course=? AND time >= (SELECT started FROM enrollments WHERE guild=? AND member=?) ORDER BY time DESC LIMIT 1',(i.guild.id,member.id,entry[0],i.guild.id,member.id)).fetchone()
        if not passed or not passed[0]:return await i.followup.send('No passed exam for this enrollment.',ephemeral=True)
        await promote(i.guild,member,entry[0]);await i.followup.send('Promotion completed.',ephemeral=True)
@bot.tree.command(name='cancel_training',description='Instructor: end enrollment and remove trainee access')
@app_commands.guild_only()
async def cancel_training(i,member:discord.Member):
    if not instructor(i.user):return await i.response.send_message('Instructor or leadership required.',ephemeral=True)
    await i.response.defer(ephemeral=True)
    async with locks.setdefault(('training',member.id),asyncio.Lock()):
        remove=[r for r in member.roles if base_name(r.name) in training.TRAINEES]
        if remove:await member.remove_roles(*remove)
        training.clear(i.guild.id,member.id)
        e=active_exams.pop(member.id,None)
        if e:e.finished=True;e.stop()
        await i.followup.send('Training ended. Existing qualified rank remains.',ephemeral=True)
@bot.tree.command(name='training_status',description='See your active course and module completion')
@app_commands.guild_only()
async def training_status(i):
    entry=training.enrollment(i.guild.id,i.user.id)
    if not entry:return await i.response.send_message('No active training course.',ephemeral=True)
    with ack_db() as db:count=db.execute('SELECT COUNT(*) FROM modules WHERE guild=? AND member=? AND course=?',(i.guild.id,i.user.id,entry[0])).fetchone()[0]
    await i.response.send_message(f'Course: {training.COURSES[entry[0]][0]} • Modules: {count}/3 • Pass mark: 80%.',ephemeral=True)

# Persistent duty clock and public board
DUTY_RANKS=LEAD+['EMS Chief','Department Head','Attending Physician','Resident Physician','Nurse Practitioner','Registered Nurse','Paramedic','EMT','Medical Intern','Human Resources','Receptionist']
SPECIALTIES=['Family Medicine','OB-GYN','Therapist','Pediatrician','Physical Therapist']
def duty_db():
    db=training.connect()
    db.execute('CREATE TABLE IF NOT EXISTS duty_active (guild INTEGER, member INTEGER, started REAL, PRIMARY KEY(guild,member))')
    db.execute('CREATE TABLE IF NOT EXISTS duty_shifts (guild INTEGER, member INTEGER, started REAL, ended REAL, actor INTEGER, reason TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS duty_posts (guild INTEGER, channel INTEGER, page INTEGER, message INTEGER, PRIMARY KEY(guild,page))')
    return db

def duty_start(gid,uid,now):
    with duty_db() as db:
        result=db.execute('INSERT OR IGNORE INTO duty_active VALUES (?,?,?)',(gid,uid,now))
        return result.rowcount==1

def duty_end(gid,uid,actor,reason,now):
    with duty_db() as db:
        row=db.execute('SELECT started FROM duty_active WHERE guild=? AND member=?',(gid,uid)).fetchone()
        if not row:return None
        db.execute('INSERT INTO duty_shifts VALUES (?,?,?,?,?,?)',(gid,uid,row[0],now,actor,reason))
        db.execute('DELETE FROM duty_active WHERE guild=? AND member=?',(gid,uid))
        return row[0]

def staff_member(member):
    return any(base_name(r.name) in ['Hospital Staff']+DUTY_RANKS+training.TRAINEES for r in member.roles)
def staff_label(member):
    names={base_name(r.name) for r in member.roles}
    rank=next((n for n in DUTY_RANKS if n in names),'Hospital Staff')
    trainees=[n for n in training.TRAINEES if n in names]
    extras=[n for n in SPECIALTIES if n in names]+trainees
    return rank,extras
async def duty_pages(g):
    with duty_db() as db:rows=db.execute('SELECT member,started FROM duty_active WHERE guild=? ORDER BY started',(g.id,)).fetchall()
    lines=[]
    for uid,started in rows:
        member=g.get_member(uid)
        if not member:
            try:member=await g.fetch_member(uid)
            except discord.NotFound:
                duty_end(g.id,uid,bot.user.id,'Member left server',time.time());continue
        if not staff_member(member):
            duty_end(g.id,uid,bot.user.id,'Hospital staff access removed',time.time());continue
        rank,extras=staff_label(member)
        details=' • '+', '.join(extras) if extras else ''
        lines.append(f'🟢 {member.mention} — **{rank}**{details}\nClocked in <t:{int(started)}:R>')
    descriptions=[];current=''
    for line in lines:
        if len(current)+len(line)+2>3500:
            descriptions.append(current);current=''
        current+=line+'\n\n'
    if current:descriptions.append(current)
    if not descriptions:descriptions=['🌙 No hospital staff are currently clocked in.']
    pages=[]
    for idx,body in enumerate(descriptions):
        e=discord.Embed(title=f'🏥 ST. BERNARDS | ON DUTY ({len(lines)})',description=body,color=0x2e7d32,timestamp=discord.utils.utcnow())
        e.set_footer(text=f'STB duty board • {idx+1}/{len(descriptions)} • Staff-reported Discord status')
        pages.append(e)
    return pages
async def update_duty_board(g):
    ch=channel(g,'unit-status')
    if not ch:return False
    async with locks.setdefault(('duty-board',g.id),asyncio.Lock()):
        pages=await duty_pages(g)
        with duty_db() as db:old={r[0]:(r[1],r[2]) for r in db.execute('SELECT page,channel,message FROM duty_posts WHERE guild=?',(g.id,))}
        for idx,embed in enumerate(pages):
            msg=None
            if idx in old and old[idx][0]==ch.id:
                try:msg=await ch.fetch_message(old[idx][1])
                except discord.NotFound:pass
            if msg:await msg.edit(embed=embed)
            else:msg=await ch.send(embed=embed)
            with duty_db() as db:db.execute('INSERT OR REPLACE INTO duty_posts VALUES (?,?,?,?)',(g.id,ch.id,idx,msg.id))
        for idx,(cid,mid) in old.items():
            if idx>=len(pages):
                old_ch=g.get_channel(cid)
                if old_ch:
                    try:await (await old_ch.fetch_message(mid)).delete()
                    except discord.NotFound:pass
                with duty_db() as db:db.execute('DELETE FROM duty_posts WHERE guild=? AND page=?',(g.id,idx))
    return True
async def setup_duty(g):
    ch=channel(g,'unit-status')
    if not ch:
        cat=discord.utils.get(g.categories,name='🚑 EMS OPERATIONS')
        ch=await g.create_text_channel(pretty_channel('unit-status'),category=cat,overwrites=permissions(g))
    public=permissions(g)
    public[g.default_role].send_messages=False
    await ch.edit(overwrites=public,topic='Live hospital duty roster. Updated by staff clock-in/out; not connected to FiveM duty status.')
    clock=channel(g,'clock-in-out')
    p=permissions(g,['Hospital Staff']+DUTY_RANKS+training.TRAINEES)
    for who,ow in p.items():
        if who!=g.me:ow.send_messages=False
    await clock.edit(overwrites=p)
    marker='STB duty controls v1'
    existing=[m async for m in clock.history(limit=100)]
    if not any(m.author==bot.user and m.embeds and m.embeds[0].footer.text==marker for m in existing):
        e=discord.Embed(title='⏱️ HOSPITAL TIME CLOCK',description='Clock in when you begin your hospital shift. Clock out when you finish. Your name, current rank, specialty and clock-in time will appear in the public unit-status channel. You can also use /clock_in and /clock_out.',color=0xb71c1c)
        e.set_footer(text=marker);await clock.send(embed=e,view=DutyControls())
    await update_duty_board(g)
async def change_duty(i,clock_in):
    await i.response.defer(ephemeral=True)
    async with locks.setdefault(('duty',i.user.id),asyncio.Lock()):
        now=time.time()
        if clock_in:
            if not staff_member(i.user):return await i.followup.send('Only hospital staff can clock in.',ephemeral=True)
            if role(i.guild,'On Leave') in i.user.roles:return await i.followup.send('You are marked On Leave. Ask leadership to remove that role before clocking in.',ephemeral=True)
            changed=duty_start(i.guild.id,i.user.id,now)
            if not changed:return await i.followup.send('You are already clocked in.',ephemeral=True)
            result='🟢 Clocked in! You are now listed on the public duty board.'
            logline=f'🟢 {i.user.mention} clocked in • {staff_label(i.user)[0]} • <t:{int(now)}:f>'
        else:
            started=duty_end(i.guild.id,i.user.id,i.user.id,'Clocked out',now)
            if started is None:return await i.followup.send('You are not currently clocked in.',ephemeral=True)
            minutes=max(0,int((now-started)//60));result=f'🔴 Clocked out. Shift duration: {minutes//60}h {minutes%60}m.'
            logline=f'🔴 {i.user.mention} clocked out • Start: <t:{int(started)}:f> • End: <t:{int(now)}:f> • Duration: {minutes//60}h {minutes%60}m'
        try:
            log=channel(i.guild,'clock-in-out')
            if log:await log.send(logline)
            visible=await update_duty_board(i.guild)
            if not visible:result+=' Run /setup_hospital to create the duty board.'
        except discord.HTTPException:
            logging.exception('Duty board update failed')
            result+=' Your shift was saved, but the board could not refresh. Ask leadership to check channel permissions.'
        await i.followup.send(result,ephemeral=True)
class DutyControls(discord.ui.View):
    def __init__(self):super().__init__(timeout=None)
    @discord.ui.button(label='Clock In',emoji='🟢',style=discord.ButtonStyle.success,custom_id='stb:duty:in')
    async def start(self,i,button):await change_duty(i,True)
    @discord.ui.button(label='Clock Out',emoji='🔴',style=discord.ButtonStyle.danger,custom_id='stb:duty:out')
    async def end(self,i,button):await change_duty(i,False)
@bot.tree.command(name='clock_in',description='Begin your hospital shift and appear on the public duty board')
@app_commands.guild_only()
async def clock_in(i):await change_duty(i,True)
@bot.tree.command(name='clock_out',description='End your hospital shift and leave the public duty board')
@app_commands.guild_only()
async def clock_out(i):await change_duty(i,False)
@bot.tree.command(name='who_on_duty',description='View current hospital staff on duty with rank and specialty')
@app_commands.guild_only()
async def who_on_duty(i):
    await i.response.defer(ephemeral=True)
    for page in await duty_pages(i.guild):await i.followup.send(embed=page,ephemeral=True)
@bot.tree.command(name='force_clock_out',description='Leadership: clock out a staff member who forgot')
@app_commands.guild_only()
async def force_clock_out(i,member:discord.Member):
    if not (i.user.guild_permissions.administrator or any(base_name(r.name) in LEAD+['EMS Chief','Human Resources'] for r in i.user.roles)):
        return await i.response.send_message('Hospital leadership, EMS Chief or HR required.',ephemeral=True)
    await i.response.defer(ephemeral=True)
    async with locks.setdefault(('duty',member.id),asyncio.Lock()):
        now=time.time()
        started=duty_end(i.guild.id,member.id,i.user.id,'Leadership clock-out',now)
        if started is None:return await i.followup.send('That member is not clocked in.',ephemeral=True)
        await update_duty_board(i.guild)
        log=channel(i.guild,'clock-in-out')
        if log:await log.send(f'🔴 {member.mention} clocked out by {i.user.mention} • Start: <t:{int(started)}:f> • End: <t:{int(now)}:f> • Duration: {duration_label(now-started)}.')
        await i.followup.send('Member clocked out.',ephemeral=True)
@tasks.loop(minutes=1)
async def refresh_duty():
    g=bot.get_guild(GUILD_ID)
    if g:
        try:await update_duty_board(g)
        except Exception:logging.exception('Duty refresh failed')
@refresh_duty.before_loop
async def before_duty():await bot.wait_until_ready()
@bot.event
async def on_member_remove(member):
    if member.guild.id==GUILD_ID:
        duty_end(member.guild.id,member.id,bot.user.id,'Member left server',time.time())
        await update_duty_board(member.guild)

# Hours reports and non-destructive resets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import csv
REPORT_ZONE=ZoneInfo('America/New_York')
def hours_admin(member):
    return member.guild_permissions.administrator or any(base_name(r.name) in LEAD+['EMS Chief','Human Resources'] for r in member.roles)
def hours_db():
    db=duty_db()
    db.execute('CREATE TABLE IF NOT EXISTS duty_resets (guild INTEGER, member INTEGER, cutoff REAL, PRIMARY KEY(guild,member))')
    db.execute('CREATE TABLE IF NOT EXISTS duty_reset_audit (guild INTEGER, member INTEGER, cutoff REAL, actor INTEGER, reason TEXT)')
    return db
def reset_hours_data(gid,uid,actor,reason,now):
    # uid 0 is the guild-wide baseline. Never deletes a shift.
    with hours_db() as db:
        db.execute('INSERT OR REPLACE INTO duty_resets VALUES (?,?,?)',(gid,uid,now))
        db.execute('INSERT INTO duty_reset_audit VALUES (?,?,?,?,?)',(gid,uid,now,actor,reason))
def period_start(period,now):
    d=datetime.fromtimestamp(now,REPORT_ZONE)
    if period=='week':d=(d-timedelta(days=d.weekday())).replace(hour=0,minute=0,second=0,microsecond=0)
    elif period=='month':d=d.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    else:return 0
    return d.timestamp()
def duration_label(seconds):
    seconds=max(0,int(seconds));return f'{seconds//3600}h {(seconds%3600)//60}m'
def hours_report(gid,uid,period,include_previous,now):
    with hours_db() as db:
        shifts=db.execute('SELECT member,started,ended,actor,reason FROM duty_shifts WHERE guild=?',(gid,)).fetchall()
        active=db.execute('SELECT member,started FROM duty_active WHERE guild=?',(gid,)).fetchall()
        resets=dict(db.execute('SELECT member,cutoff FROM duty_resets WHERE guild=?',(gid,)))
    totals={};ledger=[]
    for member,started,ended,actor,reason,status in [(*r,'COMPLETED') for r in shifts]+[(r[0],r[1],now,r[0],'Currently on duty','ACTIVE') for r in active]:
        if uid is not None and member!=uid:continue
        cutoff=period_start(period,now)
        if not include_previous:cutoff=max(cutoff,resets.get(0,0),resets.get(member,0))
        a=max(started,cutoff);b=min(ended,now)
        if b<=a:continue
        row=totals.setdefault(member,{'completed':0,'active':0,'shifts':0})
        row['completed' if status=='COMPLETED' else 'active']+=b-a
        row['shifts']+=int(status=='COMPLETED')
        ledger.append((member,started,ended,a,b,b-a,status,actor,reason))
    if uid is not None:totals.setdefault(uid,{'completed':0,'active':0,'shifts':0})
    return totals,ledger
PERIODS=[app_commands.Choice(name='This week (Monday start)',value='week'),app_commands.Choice(name='This month',value='month'),app_commands.Choice(name='All time',value='all')]
@bot.tree.command(name='staff_hours',description='Leadership: hours totals and downloadable shift history for one or all staff')
@app_commands.guild_only()
@app_commands.choices(period=PERIODS)
async def staff_hours(i,member:discord.Member=None,period:app_commands.Choice[str]=None,include_previous:bool=False):
    if not hours_admin(i.user):return await i.response.send_message('Hospital leadership, EMS Chief or HR required.',ephemeral=True)
    await i.response.defer(ephemeral=True)
    period_key=period.value if period else 'all';now=time.time()
    totals,ledger=hours_report(i.guild.id,member.id if member else None,period_key,include_previous,now)
    sorted_rows=sorted(totals.items(),key=lambda pair:pair[1]['completed']+pair[1]['active'],reverse=True)
    lines=[f'<@{uid}> • **{duration_label(row["completed"]+row["active"])}** total\nCompleted: {duration_label(row["completed"])} • Current shift: {duration_label(row["active"])} • {row["shifts"]} completed shifts' for uid,row in sorted_rows]
    mode='Includes time before resets' if include_previous else 'Counts time after the latest applicable reset'
    if not lines:lines=['No recorded hours in this reporting period.']
    page=''
    for line in lines:
        if len(page)+len(line)>3500:
            await i.followup.send(embed=discord.Embed(title='⏱️ STAFF HOURS',description=page,color=0xb71c1c),ephemeral=True);page=''
        page+=line+'\n\n'
    e=discord.Embed(title=f'⏱️ STAFF HOURS • {period_key.upper()}',description=page,color=0xb71c1c)
    e.set_footer(text=f'{mode} • America/New_York • Ongoing time is provisional')
    await i.followup.send(embed=e,ephemeral=True)
    # CSV uses numeric identifiers/UTC timestamps and quotes formulas in free text.
    def safe(value):
        s=str(value)
        return "'"+s if s.startswith(('=','+','-','@','\t','\r')) else s
    stream=io.StringIO();writer=csv.writer(stream)
    writer.writerow(['member_id','shift_start_utc','shift_end_or_snapshot_utc','counted_start_utc','counted_end_utc','counted_seconds','hours','status','closed_by_id','reason'])
    for uid,start,end,a,b,seconds,status,actor,reason in ledger:
        iso=lambda n:datetime.fromtimestamp(n,ZoneInfo('UTC')).isoformat()
        writer.writerow([uid,iso(start),iso(end),iso(a),iso(b),round(seconds,2),round(seconds/3600,4),status,actor,safe(reason)])
    raw=stream.getvalue().encode('utf-8-sig')
    if len(raw)<=i.guild.filesize_limit:
        await i.followup.send(content='Shift details for this report:',file=discord.File(io.BytesIO(raw),filename=f'staff-hours-{period_key}-{int(now)}.csv'),ephemeral=True)
    else:await i.followup.send('Shift export is too large for Discord. Choose a member or a shorter period.',ephemeral=True)
class ResetHoursConfirm(discord.ui.View):
    def __init__(self,actor,uid,reason):
        super().__init__(timeout=90);self.actor=actor;self.uid=uid;self.reason=reason;self.used=False
    @discord.ui.button(label='Confirm reset',style=discord.ButtonStyle.danger)
    async def confirm(self,i,button):
        if i.user.id!=self.actor or not hours_admin(i.user):return await i.response.send_message('Only the authorized requester can confirm.',ephemeral=True)
        if self.used:return await i.response.send_message('This reset has already been handled.',ephemeral=True)
        self.used=True;self.stop()
        reset_hours_data(i.guild.id,self.uid,i.user.id,self.reason,time.time())
        await i.response.edit_message(content='✅ Hours counter reset. Original shift history is retained. Staff on duty remain clocked in; their counted time now starts from this reset.',view=None)
        log=channel(i.guild,'bot-logs')
        if log:
            target=f'<@{self.uid}>' if self.uid else 'all staff'
            await log.send(f'⏱️ Hours reset for {target} by {i.user.mention}. Reason: {self.reason}')
    @discord.ui.button(label='Cancel',style=discord.ButtonStyle.secondary)
    async def cancel(self,i,button):
        if i.user.id!=self.actor:return await i.response.send_message('Only the requester can cancel.',ephemeral=True)
        self.used=True;self.stop();await i.response.edit_message(content='Reset canceled. No hours changed.',view=None)
@bot.tree.command(name='reset_hours',description='Leadership: reset one member or everyone’s hours counter; retain all original shift records')
@app_commands.guild_only()
async def reset_hours(i,member:discord.Member=None,reason:str='New reporting period'):
    if not hours_admin(i.user):return await i.response.send_message('Hospital leadership, EMS Chief or HR required.',ephemeral=True)
    if len(reason)>500:return await i.response.send_message('Use a reason under 500 characters.',ephemeral=True)
    target=member.mention if member else '**ALL STAFF**'
    await i.response.send_message(f'Reset the hours counter for {target}?\nNew totals start from the time you confirm. Existing shift records remain available using `/staff_hours include_previous:True`. Active staff stay clocked in.\nReason: {reason}',view=ResetHoursConfirm(i.user.id,member.id if member else 0,reason),ephemeral=True)

features.install(sys.modules[__name__])

if __name__=='__main__': bot.run(os.environ['DISCORD_TOKEN'])
