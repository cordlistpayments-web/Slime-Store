import os, json, asyncio, io, random, re, logging
from datetime import datetime, timezone, timedelta
import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
TOKEN=os.getenv('DISCORD_TOKEN','')
GUILD_ID=int(os.getenv('GUILD_ID','0') or 0)
STAFF_ROLE_ID=int(os.getenv('STAFF_ROLE_ID','0') or 0)
WELCOME_CHANNEL_ID=int(os.getenv('WELCOME_CHANNEL_ID','0') or 0)
LOG_CHANNEL_ID=int(os.getenv('LOG_CHANNEL_ID','0') or 0)
IMAGE=os.getenv('EMBED_IMAGE_URL','')
COLOR=discord.Color.from_rgb(103,225,154)
intents=discord.Intents.default()
intents.members=True
intents.message_content=True
bot=commands.Bot(command_prefix='!', intents=intents)
state={}
store_lock=asyncio.Lock()
ready_once=False

def embed(title,description='',image=False):
    e=discord.Embed(title=title,description=description,color=COLOR,timestamp=datetime.now(timezone.utc))
    e.set_footer(text='Nothing Special Studios • Slime Store Tycoon')
    if image and IMAGE: e.set_image(url=IMAGE)
    return e

def staff(member):
    return isinstance(member,discord.Member) and (member.guild_permissions.manage_guild or (STAFF_ROLE_ID and any(r.id==STAFF_ROLE_ID for r in member.roles)))

async def db_channel(guild):
    ch=discord.utils.get(guild.text_channels,name='🔒bot-database') or discord.utils.get(guild.text_channels,name='bot-database')
    if ch: return ch
    overwrites={guild.default_role:discord.PermissionOverwrite(view_channel=False),guild.me:discord.PermissionOverwrite(view_channel=True,send_messages=True,read_message_history=True,manage_messages=True)}
    # Do not grant access to staff by default: records can contain sensitive ticket content.
    return await guild.create_text_channel('bot-database',overwrites=overwrites,topic='Private bot records — do not edit or delete messages')

async def load_state(guild):
    global state
    ch=await db_channel(guild)
    latest=None
    async for m in ch.history(limit=1000,oldest_first=False):
        if m.author.id!=bot.user.id: continue
        try:
            if m.content.startswith('NSS_DB_V1\n'):
                latest=json.loads(m.content.split('\n',1)[1]); break
            if m.content=='NSS_DB_BACKUP_V1' and m.attachments:
                raw=await m.attachments[0].read()
                latest=json.loads(raw.decode().split('\n',1)[1]); break
        except (ValueError,IndexError,discord.HTTPException): continue
    state=latest or {'tickets':{},'warnings':{},'giveaways':{},'suggestions':{},'config':{}}
    for key in ('tickets','warnings','giveaways','suggestions','config'): state.setdefault(key,{})

async def save_state(guild):
    async with store_lock:
        ch=await db_channel(guild)
        data='NSS_DB_V1\n'+json.dumps(state,separators=(',',':'),ensure_ascii=False)
        if len(data)>1900:
            # Attachments allow state to grow without exceeding Discord message limits.
            await ch.send(content='NSS_DB_BACKUP_V1',file=discord.File(io.BytesIO(data.encode()),filename='state.json'))
        else:
            await ch.send(data)
        # Keep 10 most recent snapshots for recovery.
        snapshots=[]
        async for m in ch.history(limit=100):
            if m.author.id==bot.user.id and (m.content.startswith('NSS_DB_V1\n') or m.content=='NSS_DB_BACKUP_V1'): snapshots.append(m)
        for m in snapshots[10:]:
            try: await m.delete()
            except discord.HTTPException: pass

async def log(guild,text):
    ch=guild.get_channel(LOG_CHANNEL_ID) if LOG_CHANNEL_ID else discord.utils.get(guild.text_channels,name='mod-logs')
    if ch:
        try: await ch.send(embed=embed('Studio log',text[:3900]))
        except discord.HTTPException: pass

async def ensure_ticket_category(guild):
    cat=discord.utils.get(guild.categories,name='🎫 TICKETS')
    if not cat: cat=await guild.create_category('🎫 TICKETS')
    return cat

class TicketPanel(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label='Open Support Ticket',emoji='🎫',style=discord.ButtonStyle.green,custom_id='nss:ticket:open')
    async def open(self,interaction:discord.Interaction,button:discord.ui.Button):
        guild=interaction.guild
        if not guild: return await interaction.response.send_message('Use this inside the server.',ephemeral=True)
        existing=next((k for k,v in state['tickets'].items() if v.get('user')==interaction.user.id and v.get('status')=='open' and guild.get_channel(int(k))),None)
        if existing: return await interaction.response.send_message(f'You already have a ticket: <#{existing}>',ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        cat=await ensure_ticket_category(guild)
        overwrites={guild.default_role:discord.PermissionOverwrite(view_channel=False),guild.me:discord.PermissionOverwrite(view_channel=True,send_messages=True,read_message_history=True,manage_channels=True),interaction.user:discord.PermissionOverwrite(view_channel=True,send_messages=True,read_message_history=True)}
        if STAFF_ROLE_ID and guild.get_role(STAFF_ROLE_ID): overwrites[guild.get_role(STAFF_ROLE_ID)]=discord.PermissionOverwrite(view_channel=True,send_messages=True,read_message_history=True)
        ch=await guild.create_text_channel(f'ticket-{interaction.user.id}',category=cat,overwrites=overwrites,topic=f'Ticket owner: {interaction.user.id}')
        state['tickets'][str(ch.id)]={'user':interaction.user.id,'status':'open','claimed':None,'created':datetime.now(timezone.utc).isoformat()}
        await save_state(guild)
        await ch.send(interaction.user.mention,embed=embed('🎫 Support ticket','Describe your issue here. A staff member will help you. Do not share passwords or payment details.'),view=TicketActions())
        await interaction.followup.send(f'Your ticket is ready: {ch.mention}',ephemeral=True)
        await log(guild,f'Ticket opened by {interaction.user.mention}: {ch.mention}')

class TicketActions(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label='Claim',emoji='🙋',style=discord.ButtonStyle.primary,custom_id='nss:ticket:claim')
    async def claim(self,interaction:discord.Interaction,button:discord.ui.Button):
        if not staff(interaction.user): return await interaction.response.send_message('Staff only.',ephemeral=True)
        record=state['tickets'].get(str(interaction.channel_id))
        if not record: return await interaction.response.send_message('Not a tracked ticket.',ephemeral=True)
        record['claimed']=interaction.user.id
        await save_state(interaction.guild)
        await interaction.response.send_message(embed=embed('Ticket claimed',f'{interaction.user.mention} is handling this ticket.'))
    @discord.ui.button(label='Close Ticket',emoji='🔒',style=discord.ButtonStyle.danger,custom_id='nss:ticket:close')
    async def close(self,interaction:discord.Interaction,button:discord.ui.Button):
        record=state['tickets'].get(str(interaction.channel_id))
        if not record: return await interaction.response.send_message('Not a tracked ticket.',ephemeral=True)
        if not (staff(interaction.user) or interaction.user.id==record['user']): return await interaction.response.send_message('Not permitted.',ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        lines=[]
        async for m in interaction.channel.history(limit=500,oldest_first=True):
            lines.append(f'[{m.created_at.isoformat()}] {m.author} ({m.author.id}): {m.clean_content}'+(' [attachments: '+', '.join(a.url for a in m.attachments)+']' if m.attachments else ''))
        text='\n'.join(lines) or '(empty)'
        archive=interaction.guild.get_channel(LOG_CHANNEL_ID) if LOG_CHANNEL_ID else discord.utils.get(interaction.guild.text_channels,name='ticket-logs')
        if archive:
            try: await archive.send(embed=embed('Ticket closed',f'Channel: {interaction.channel.name}\nClosed by: {interaction.user.mention}'),file=discord.File(io.BytesIO(text.encode()),filename=f'ticket-{interaction.channel_id}.txt'))
            except discord.HTTPException: pass
        record['status']='closed';record['closed']=datetime.now(timezone.utc).isoformat()
        await save_state(interaction.guild)
        await interaction.followup.send('Ticket closed and transcript archived (if a log channel is configured).',ephemeral=True)
        await interaction.channel.delete(reason=f'Ticket closed by {interaction.user}')

class GiveawayView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label='Enter Giveaway',emoji='🎉',style=discord.ButtonStyle.green,custom_id='nss:giveaway:enter')
    async def enter(self,interaction:discord.Interaction,button:discord.ui.Button):
        g=state['giveaways'].get(str(interaction.message.id))
        if not g or g['ended']: return await interaction.response.send_message('This giveaway has ended.',ephemeral=True)
        users=g.setdefault('users',[])
        if interaction.user.id in users: return await interaction.response.send_message('You are already entered!',ephemeral=True)
        users.append(interaction.user.id)
        await save_state(interaction.guild)
        await interaction.response.send_message('You are entered! 🎉',ephemeral=True)

@bot.event
async def on_ready():
    global ready_once
    if ready_once: return
    ready_once=True
    bot.add_view(TicketPanel());bot.add_view(TicketActions());bot.add_view(GiveawayView())
    if GUILD_ID:
        guild=bot.get_guild(GUILD_ID)
        if guild:
            await load_state(guild)
            bot.tree.copy_global_to(guild=discord.Object(id=GUILD_ID))
            await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
            logging.info('Synced commands for %s',guild.name)
    else:
        for guild in bot.guilds: await load_state(guild)
        await bot.tree.sync()
    if not giveaway_checker.is_running(): giveaway_checker.start()
    logging.info('Logged in as %s',bot.user)

@bot.event
async def on_member_join(member):
    ch=member.guild.get_channel(WELCOME_CHANNEL_ID) if WELCOME_CHANNEL_ID else discord.utils.get(member.guild.text_channels,name='welcome')
    if ch:
        try: await ch.send(member.mention,embed=embed('🌈 Welcome to Nothing Special Studios!',f'Hey {member.mention}! Welcome to our Roblox community. Check out #rules, chat in #general and explore Slime Store Tycoon!',True))
        except discord.HTTPException: pass

AUTO={
 'how do i play':'Start by making your first slime, then sell it to customers! Upgrade your shop and unlock new recipes as you progress.',
 'how to play':'Make slimes, sell them to customers, and grow your shop. Check #tips-and-tricks for more!',
 'gamepass':'Game passes are optional extras. Check the Roblox game store for current offerings and prices.',
 'refund':'For Roblox purchases, use Roblox Support and the platform’s official policies. Staff cannot promise refunds.',
 'bug report':'Please post reproduction steps in #bug-reports, or open a private ticket for account-related issues.',
 'help me':'Try #game-help for gameplay questions or open a support ticket for private assistance.'
}
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild: return
    if message.channel.name in ('game-help','general','tips-and-tricks'):
        txt=message.content.lower().strip()
        for trigger,reply in AUTO.items():
            if trigger in txt and (txt.startswith(trigger) or '?' in txt):
                try: await message.reply(embed=embed('💡 Quick help',reply),mention_author=False)
                except discord.HTTPException: pass
                break
    await bot.process_commands(message)

def allowed(interaction): return staff(interaction.user)

@bot.tree.command(name='setup',description='Create the private database and post the ticket panel')
@app_commands.default_permissions(manage_guild=True)
async def setup(interaction:discord.Interaction):
    if not allowed(interaction): return await interaction.response.send_message('Staff only.',ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    ch=await db_channel(interaction.guild)
    support=discord.utils.get(interaction.guild.text_channels,name='open-ticket')
    if not support:
        support=await interaction.guild.create_text_channel('open-ticket',topic='Open a private support ticket below')
    await support.send(embed=embed('🎫 Nothing Special Studios Support','Need help with Slime Store Tycoon, a bug, or your account? Press below to open a private ticket.',True),view=TicketPanel())
    await interaction.followup.send(f'Setup complete! Database: {ch.mention} | Tickets: {support.mention}',ephemeral=True)

@bot.tree.command(name='embed',description='Send a branded announcement embed')
@app_commands.describe(title='Embed title',message='Embed body',channel='Where to send it')
@app_commands.default_permissions(manage_messages=True)
async def send_embed(interaction:discord.Interaction,title:str,message:str,channel:discord.TextChannel):
    if not allowed(interaction): return await interaction.response.send_message('Staff only.',ephemeral=True)
    await channel.send(embed=embed(title,message,True))
    await interaction.response.send_message('Embed posted.',ephemeral=True)

@bot.tree.command(name='rules',description='Post the studio rules embed')
@app_commands.default_permissions(manage_guild=True)
async def rules(interaction:discord.Interaction,channel:discord.TextChannel):
    if not allowed(interaction): return await interaction.response.send_message('Staff only.',ephemeral=True)
    body='**1.** Be respectful.\n**2.** No harassment, hate speech or threats.\n**3.** No spam, scams or unsolicited advertising.\n**4.** Keep conversations in the right channels.\n**5.** No exploits, cheats or malicious links.\n**6.** Protect personal information.\n**7.** Follow Discord and Roblox rules.\n**8.** Follow reasonable staff instructions.'
    await channel.send(embed=embed('📜 Server Rules',body,True))
    await interaction.response.send_message('Rules posted.',ephemeral=True)

@bot.tree.command(name='warn',description='Warn a member')
@app_commands.default_permissions(moderate_members=True)
async def warn(interaction:discord.Interaction,member:discord.Member,reason:str):
    if not allowed(interaction): return await interaction.response.send_message('Staff only.',ephemeral=True)
    state['warnings'].setdefault(str(member.id),[]).append({'reason':reason[:300],'moderator':interaction.user.id,'at':datetime.now(timezone.utc).isoformat()})
    await save_state(interaction.guild)
    await log(interaction.guild,f'{member.mention} warned by {interaction.user.mention}: {reason}')
    await interaction.response.send_message(f'Warned {member.mention}.',ephemeral=True)

@bot.tree.command(name='warnings',description='Show warnings for a member')
@app_commands.default_permissions(moderate_members=True)
async def warnings(interaction:discord.Interaction,member:discord.Member):
    if not allowed(interaction): return await interaction.response.send_message('Staff only.',ephemeral=True)
    items=state['warnings'].get(str(member.id),[])
    msg='\n'.join(f'{i+1}. {x["reason"]} — <@{x["moderator"]}>' for i,x in enumerate(items[-15:])) or 'No warnings.'
    await interaction.response.send_message(embed=embed(f'Warnings for {member}',msg),ephemeral=True)

@bot.tree.command(name='timeout',description='Temporarily timeout a member')
@app_commands.default_permissions(moderate_members=True)
async def timeout(interaction:discord.Interaction,member:discord.Member,minutes:app_commands.Range[int,1,40320],reason:str):
    if not allowed(interaction): return await interaction.response.send_message('Staff only.',ephemeral=True)
    try: await member.timeout(timedelta(minutes=minutes),reason=reason)
    except discord.Forbidden: return await interaction.response.send_message('I lack permission or my role is too low.',ephemeral=True)
    await log(interaction.guild,f'{member} timed out for {minutes} minutes by {interaction.user}: {reason}')
    await interaction.response.send_message('Timeout applied.',ephemeral=True)

@bot.tree.command(name='kick',description='Kick a member')
@app_commands.default_permissions(kick_members=True)
async def kick(interaction:discord.Interaction,member:discord.Member,reason:str):
    if not (interaction.user.guild_permissions.kick_members and allowed(interaction)): return await interaction.response.send_message('Not permitted.',ephemeral=True)
    try: await member.kick(reason=reason)
    except discord.Forbidden: return await interaction.response.send_message('I lack permission or my role is too low.',ephemeral=True)
    await interaction.response.send_message('Member kicked.',ephemeral=True)
    await log(interaction.guild,f'{member} kicked by {interaction.user}: {reason}')

@bot.tree.command(name='ban',description='Ban a member')
@app_commands.default_permissions(ban_members=True)
async def ban(interaction:discord.Interaction,member:discord.Member,reason:str):
    if not (interaction.user.guild_permissions.ban_members and allowed(interaction)): return await interaction.response.send_message('Not permitted.',ephemeral=True)
    try: await member.ban(reason=reason)
    except discord.Forbidden: return await interaction.response.send_message('I lack permission or my role is too low.',ephemeral=True)
    await interaction.response.send_message('Member banned.',ephemeral=True)
    await log(interaction.guild,f'{member} banned by {interaction.user}: {reason}')

@bot.tree.command(name='suggest',description='Submit a suggestion for the studio')
async def suggest(interaction:discord.Interaction,suggestion:app_commands.Range[str,10,1500]):
    ch=discord.utils.get(interaction.guild.text_channels,name='suggestions')
    if not ch: return await interaction.response.send_message('No #suggestions channel found.',ephemeral=True)
    msg=await ch.send(embed=embed('💡 Community suggestion',f'From {interaction.user.mention}\n\n{suggestion}'))
    await msg.add_reaction('👍');await msg.add_reaction('👎')
    state['suggestions'][str(msg.id)]={'user':interaction.user.id,'status':'new'}
    await save_state(interaction.guild)
    await interaction.response.send_message('Suggestion submitted!',ephemeral=True)

@bot.tree.command(name='bug',description='Submit a structured bug report')
async def bug(interaction:discord.Interaction,summary:app_commands.Range[str,5,150],steps:app_commands.Range[str,10,1500]):
    ch=discord.utils.get(interaction.guild.text_channels,name='bug-reports')
    if not ch: return await interaction.response.send_message('No #bug-reports channel found.',ephemeral=True)
    await ch.send(embed=embed('🐛 Bug report',f'**Reported by:** {interaction.user.mention}\n**Issue:** {summary}\n**Steps to reproduce:**\n{steps}'))
    await interaction.response.send_message('Bug report sent. Thank you!',ephemeral=True)

@bot.tree.command(name='giveaway',description='Start a giveaway with a button')
@app_commands.default_permissions(manage_guild=True)
async def giveaway(interaction:discord.Interaction,prize:str,minutes:app_commands.Range[int,1,10080],channel:discord.TextChannel):
    if not allowed(interaction): return await interaction.response.send_message('Staff only.',ephemeral=True)
    end=datetime.now(timezone.utc)+timedelta(minutes=minutes)
    msg=await channel.send(embed=embed('🎉 Giveaway',f'**Prize:** {prize}\n**Ends:** <t:{int(end.timestamp())}:R>\nPress below to enter!'),view=GiveawayView())
    state['giveaways'][str(msg.id)]={'channel':channel.id,'prize':prize,'end':end.isoformat(),'users':[],'ended':False}
    await save_state(interaction.guild)
    await interaction.response.send_message('Giveaway started!',ephemeral=True)

@tasks.loop(minutes=1)
async def giveaway_checker():
    now=datetime.now(timezone.utc)
    for guild in bot.guilds:
        if GUILD_ID and guild.id!=GUILD_ID: continue
        changed=False
        for mid,g in list(state.get('giveaways',{}).items()):
            if g['ended'] or datetime.fromisoformat(g['end'])>now: continue
            g['ended']=True;changed=True
            ch=guild.get_channel(g['channel'])
            if ch:
                winner=random.choice(g['users']) if g['users'] else None
                await ch.send(embed=embed('🎉 Giveaway ended',f'**Prize:** {g["prize"]}\n'+(f'**Winner:** <@{winner}> 🏆' if winner else 'No entries this time.')))
                try:
                    msg=await ch.fetch_message(int(mid));await msg.edit(view=None)
                except discord.HTTPException: pass
        if changed: await save_state(guild)

@giveaway_checker.before_loop
async def before_giveaways(): await bot.wait_until_ready()

@bot.tree.error
async def on_app_error(interaction:discord.Interaction,error:app_commands.AppCommandError):
    logging.exception('Slash command error: %s',error)
    msg='Something went wrong. Check bot permissions and the Render logs.'
    try:
        if interaction.response.is_done(): await interaction.followup.send(msg,ephemeral=True)
        else: await interaction.response.send_message(msg,ephemeral=True)
    except discord.HTTPException: pass

if not TOKEN: raise SystemExit('Set DISCORD_TOKEN in Render environment variables or .env')
bot.run(TOKEN)
