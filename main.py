import discord
from discord.ext import commands
import sqlite3
import uuid
import logging
from datetime import datetime, timedelta
import requests
import json
import os
import time
from discord.ui import Select, View
import asyncio
import random
import threading
from concurrent.futures import ThreadPoolExecutor

token = 'put your damn token here'
botname = 'Brian Moser'
prefix = ';'
LASTFM_API_KEY = 'get your own noob'
USER_DATA_FILE = 'lastfm.json'
ADMINS_FILE = "admins.json"
SNIPE_FILE = "snipe.json"
MY_USER_ID = 1074072238455787601  # Replace with bot owners id

# Custom check to allow only specific users
def is_me():
    async def predicate(ctx):
        
        return ctx.author.id == MY_USER_ID
        
    return commands.check(predicate)

def load_user_data():
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, 'r') as file:
            return json.load(file)
    return {}

# Save user data to JSON file
def save_user_data(data):
    with open(USER_DATA_FILE, 'w') as file:
        json.dump(data, file, indent=4)

# Check if a Last.fm username is valid
def is_valid_lastfm_user(username):
    url = f"http://ws.audioscrobbler.com/2.0/?method=user.getinfo&user={username}&api_key={LASTFM_API_KEY}&format=json"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return 'error' not in data
    return False

def get_lastfm_profile_info(username):
    url = f"http://ws.audioscrobbler.com/2.0/?method=user.getinfo&user={username}&api_key={LASTFM_API_KEY}&format=json"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        user_info = data.get('user', {})
        if user_info:
            return {
                'username': user_info.get('name', 'Unknown'),
                'playcount': user_info.get('playcount', '0'),
                'registered': user_info.get('registered', {}).get('#text', 'Unknown'),
                'profile_url': user_info.get('url', 'Unknown')
            }
    return None

# Initialize the bot
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=prefix, intents=intents)
bot.remove_command("help")
starttime = time.time()

@bot.event
async def on_ready():
    print("Ready.")

def parse_duration(duration_str):
    if duration_str.endswith('d'):
        days = int(duration_str[:-1])
        return timedelta(days=days)
    elif duration_str.endswith('m'):
        months = int(duration_str[:-1])
        return timedelta(days=months * 30)  # Approximate 30 days per month
    elif duration_str.endswith('y'):
        years = int(duration_str[:-1])
        return timedelta(days=years * 365)  # Approximate 365 days per year
    else:
        raise ValueError("Invalid duration format. Use 'd' for days, 'm' for months, 'y' for years.")

# Generate Embeds
def genembed(title, desc=None, field1=None, field2=None, field3=None,):
    embed = discord.Embed(title=title, description=desc, color=discord.Colour.dark_red())
    embed.set_author(name=botname)
    if field1:
        embed.add_field(name=field1, value=' ', inline=True)
    if field2:
        embed.add_field(name=field2, value=' ', inline=True)
    if field3:
        embed.add_field(name=field3, value=' ', inline=True)

    avatar = bot.user.avatar.url
    embed.set_thumbnail(url=avatar)
    return embed

# Database connection
conn = sqlite3.connect('licenses.db')
cursor = conn.cursor()

# Ensure tables exist
cursor.execute('''
CREATE TABLE IF NOT EXISTS licenses (
    license_key TEXT PRIMARY KEY,
    uses_left INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS redeemed_licenses (
    license_key TEXT,
    guild_id TEXT,
    redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (license_key, guild_id),
    FOREIGN KEY (license_key) REFERENCES licenses(license_key)
)
''')

# Create a table for welcome settings
cursor.execute('''
CREATE TABLE IF NOT EXISTS welcome_settings (
    guild_id TEXT PRIMARY KEY,
    channel_id TEXT,
    message TEXT,
    enabled INTEGER DEFAULT 0
)
''')
conn.commit()

# Create a table for reaction roles
cursor.execute('''
CREATE TABLE IF NOT EXISTS reaction_roles (
    message_id TEXT PRIMARY KEY,
    guild_id TEXT,
    channel_id TEXT,
    template TEXT
)
''')
conn.commit()

# Reaction Role System
reaction_templates = {
    "colors": {
        "🔴": ("Red", discord.Color.red()),
        "🔵": ("Blue", discord.Color.blue()),
        "🟢": ("Green", discord.Color.green()),
        "🟡": ("Yellow", discord.Color.gold()),
        "🟣": ("Purple", discord.Color.purple())
    },
    "os": {
        "🪟": ("Windows", None),
        "🍏": ("MacOS", None),
        "🐧": ("Linux", None),
        "📱": ("Android", None),
        "📱": ("iOS", None)
    },
    "countries": {
        "🇺🇸": ("USA", None),
        "🇬🇧": ("UK", None),
        "🇫🇷": ("France", None),
        "🇩🇪": ("Germany", None),
        "🇮🇳": ("India", None)
    }
}

@bot.command(name="reactrole")
async def reactrole(ctx, channel: discord.TextChannel, template: str):
    guild_id = str(ctx.guild.id)

    # Check if the server has a valid, non-expired license
    cursor.execute('''
        SELECT l.license_key, l.expires_at
        FROM redeemed_licenses r
        JOIN licenses l ON r.license_key = l.license_key
        WHERE r.guild_id = ? AND l.expires_at > ?
    ''', (guild_id, datetime.now()))

    result = cursor.fetchone()

    if not result:
        await ctx.send(embed=genembed('No license', 'This server does not have a license, if you have a license, Run : ;redeemlicense <license>'))
        return
    template = template.lower()
    if template not in reaction_templates:
        await ctx.send(embed=genembed('Error', 'Invalid template. Choose from `colors`, `os`, or `countries`'))
        return
    
    embed = genembed('Reaction Roles', 'React to get a role!')
    for emoji, (role_name, _) in reaction_templates[template].items():
        embed.add_field(name=role_name, value=emoji, inline=True)
    
    message = await channel.send(embed=embed)
    for emoji in reaction_templates[template].keys():
        await message.add_reaction(emoji)
    
    cursor.execute('INSERT INTO reaction_roles (message_id, guild_id, channel_id, template) VALUES (?, ?, ?, ?)', (str(message.id), str(ctx.guild.id), str(channel.id), template))
    conn.commit()
    await ctx.send(embed=genembed('Success', 'Reaction role message set up!'))

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return
    
    cursor.execute('SELECT template FROM reaction_roles WHERE message_id=?', (str(payload.message_id),))
    result = cursor.fetchone()
    if result:
        template = result[0]
        guild = bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        role_name, role_color = reaction_templates.get(template, {}).get(payload.emoji.name, (None, None))
        if role_name:
            role = discord.utils.get(guild.roles, name=role_name)
            if not role:
                role = await guild.create_role(name=role_name, color=role_color if role_color else discord.Color.default())
            await member.add_roles(role)

@bot.event
async def on_raw_reaction_remove(payload):
    cursor.execute('SELECT template FROM reaction_roles WHERE message_id=?', (str(payload.message_id),))
    result = cursor.fetchone()
    if result:
        template = result[0]
        guild = bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        role_name, _ = reaction_templates.get(template, {}).get(payload.emoji.name, (None, None))
        if role_name:
            role = discord.utils.get(guild.roles, name=role_name)
            if role:
                await member.remove_roles(role)

# Command to enable welcome messages
@bot.command(name="welcome")
async def welcome(ctx, action: str, *, value: str = None):
    guild_id = str(ctx.guild.id)

    # Check if the server has a valid, non-expired license
    cursor.execute('''
        SELECT l.license_key, l.expires_at
        FROM redeemed_licenses r
        JOIN licenses l ON r.license_key = l.license_key
        WHERE r.guild_id = ? AND l.expires_at > ?
    ''', (guild_id, datetime.now()))

    result = cursor.fetchone()

    if not result:
        await ctx.send(embed=genembed('No license', 'This server does not have a license, if you have a license, Run : ;redeemlicense <license>'))
        return
    guild_id = str(ctx.guild.id)
    
    if action.lower() == "enable":
        cursor.execute('INSERT INTO welcome_settings (guild_id, enabled) VALUES (?, 1) ON CONFLICT(guild_id) DO UPDATE SET enabled=1', (guild_id,))
        conn.commit()
        await ctx.send(embed=genembed('Welcome System', 'Welcome messages enabled!'))
    
    elif action.lower() == "disable":
        cursor.execute('UPDATE welcome_settings SET enabled=0 WHERE guild_id=?', (guild_id,))
        conn.commit()
        await ctx.send(embed=genembed('Welcome System', 'Welcome messages disabled!'))
    
    elif action.lower() == "channel" and value:
        channel = discord.utils.get(ctx.guild.text_channels, mention=value) or discord.utils.get(ctx.guild.text_channels, name=value)
        if not channel:
            await ctx.send(embed=genembed('Error', 'Invalid channel. Mention it or provide the exact name.'))
            return
        cursor.execute('UPDATE welcome_settings SET channel_id=? WHERE guild_id=?', (str(channel.id), guild_id))
        conn.commit()
        await ctx.send(embed=genembed('Welcome System', f'Welcome channel set to {channel.mention}'))
    
    elif action.lower() == "message" and value:
        cursor.execute('UPDATE welcome_settings SET message=? WHERE guild_id=?', (value, guild_id))
        conn.commit()
        await ctx.send(embed=genembed('Welcome System', 'Welcome message updated! Use {user} to mention new members.'))
    elif action.lower() == "help":
        await ctx.send(embed=genembed('Welcome System', '`;welcome <enable|disable|channel|message> [#channel|"welcomemsg"]`'))
    else:
        await ctx.send(embed=genembed('Error', 'Invalid usage. Use `;welcome enable|disable|channel|message`'))

# Send a welcome message when a member joins
@bot.event
async def on_member_join(member):
    guild_id = str(member.guild.id)
    cursor.execute('SELECT channel_id, message, enabled FROM welcome_settings WHERE guild_id=?', (guild_id,))
    result = cursor.fetchone()
    
    if result and result[2]:  # Check if enabled
        channel = member.guild.get_channel(int(result[0])) if result[0] else None
        if channel:
            message = result[1] or "Welcome {user} to the server!"
            await channel.send(embed=genembed('Welcome!', message.replace("{user}", member.mention)))


def load_admins():
    if os.path.exists(ADMINS_FILE):
        with open(ADMINS_FILE, 'r') as file:
            return json.load(file)
    return []

# Save admins to JSON file
def save_admins(admins):
    with open(ADMINS_FILE, 'w') as file:
        json.dump(admins, file, indent=4)

# Check if a user is an admin
def is_admin(user_id):
    admins = load_admins()
    return str(user_id) in admins


@bot.command(name="addadmin", help='Makes a user an admin. [OWNER ONLY]')
@is_me()
@commands.check_any(commands.check(lambda ctx: is_admin(ctx.author.id)))
async def addadmin(ctx, user: discord.User):
    admins = load_admins()

    # Add the user if they're not already an admin
    if str(user.id) not in admins:
        admins.append(str(user.id))
        save_admins(admins)
        await ctx.send(embed=genembed('Added Admin', f'Made {user.name} an admin'))
    else:
        await ctx.send(embed=genembed('User is already an admin', f'{user.name} is already an admin'))


# Command to remove an authorized user
@bot.command(name="removeadmin", help='Removes a users admin powers. [OWNER ONLY]')
@is_me()
@commands.check_any(commands.check(lambda ctx: is_admin(ctx.author.id)))
async def removeadmin(ctx, user: discord.User):
    admins = load_admins()

    # Remove the user if they're an admin
    if str(user.id) in admins:
        admins.remove(str(user.id))
        save_admins(admins)
        await ctx.send(embed=genembed('Removed Admin', f'{user.name} is no longer an admin.'))
    else:
        await ctx.send(embed=genembed('User isn\'t an admin', f'{user.name} is not an admin!'))

# Command to list authorized users
@bot.command(name="listadmins", help='List all admins. [OWNER ONLY]')
@is_me()
@commands.check_any(commands.check(lambda ctx: is_admin(ctx.author.id)))
async def listadmins(ctx):
    admins = load_admins()

    # Fetch admin usernames
    admin_list = []
    for admin_id in admins:
        user = await bot.fetch_user(admin_id)
        admin_list.append(f"{user.name} ({user.id})")

    if admin_list:
        await ctx.send(embed=genembed('Admin List', f'\n'.join(admin_list)))
    else:
        await ctx.send(embed=genembed('Admin List', f'There is no admins'))


# Generate a license
@bot.command(name="genlicense", help='Generates a license. [ADMIN ONLY]')
@commands.check(lambda ctx: is_admin(ctx.author.id))
async def genlicense(ctx, uses: int, duration: str):
    try:
        duration_timedelta = parse_duration(duration)
        expires_at = datetime.now() + duration_timedelta
    except ValueError as e:
        await ctx.send(str(e))
        return

    license_key = str(uuid.uuid4())
    cursor.execute('INSERT INTO licenses (license_key, uses_left, expires_at) VALUES (?, ?, ?)', (license_key, uses, expires_at))
    conn.commit()
    await ctx.send(embed=genembed('Generated license.', f'{license_key}', field1=f'Uses : {uses}', field2=f'Expires : {expires_at}'))

# Delete a license
@bot.command(name="dellicense", help='Deletes a license. [ADMIN ONLY]')
@commands.check(lambda ctx: is_admin(ctx.author.id))
async def dellicense(ctx, license_key: str):
    cursor.execute('DELETE FROM licenses WHERE license_key = ?', (license_key,))
    conn.commit()
    await ctx.send(embed=genembed('Deleted license', f'{license_key} has been deleted.'))

# Redeem a license
@bot.command(name="redeemlicense", help='Redeems a license.')
async def redeemlicense(ctx, license_key: str):
    guild_id = str(ctx.guild.id)

    # Check if the license exists, has uses left, and is not expired
    cursor.execute('SELECT uses_left, expires_at FROM licenses WHERE license_key = ?', (license_key,))
    result = cursor.fetchone()

    if not result:
        await ctx.send(embed=genembed('Failed to redeem', 'License not found'))
        return

    uses_left, expires_at = result
    if uses_left <= 0:
        await ctx.send(embed=genembed('Failed to redeem', 'License has no more uses'))

        return

    if datetime.now() > datetime.fromisoformat(expires_at):
        await ctx.send(embed=genembed('Failed to redeem', 'License expired'))

        return

    # Check if the license has already been redeemed in this server
    cursor.execute('SELECT 1 FROM redeemed_licenses WHERE license_key = ? AND guild_id = ?', (license_key, guild_id))
    if cursor.fetchone():
        await ctx.send(embed=genembed('Fail', 'This license has already been redeemed in this server.'))
        return

    # Redeem the license
    cursor.execute('UPDATE licenses SET uses_left = uses_left - 1 WHERE license_key = ?', (license_key,))
    cursor.execute('INSERT INTO redeemed_licenses (license_key, guild_id) VALUES (?, ?)', (license_key, guild_id))
    conn.commit()
    await ctx.send(embed=genembed('Success!', 'Successfully redeemed.'))

# Check license data
@bot.command(name="licensedata", help='Gives data about the license provided. [ADMIN ONLY]')
@commands.check(lambda ctx: is_admin(ctx.author.id))
async def licensedata(ctx, license_key: str):
    cursor.execute('SELECT uses_left, created_at, expires_at FROM licenses WHERE license_key = ?', (license_key,))
    result = cursor.fetchone()

    if not result:
        await ctx.send("License not found.")
        return

    uses_left, created_at, expires_at = result
    await ctx.send(embed=genembed('License Data', license_key, field1=f'Uses left: {uses_left}', field2=f'Created at: {created_at}', field3=f'Expiry: {expires_at}')) # f"License `{license_key}`:\nUses Left: {uses_left}\nCreated At: {created_at}\nExpires At: {expires_at}"

@bot.command(name="licensecheck", help='Checks if the servers license is valid and when it expires.')
async def licensecheck(ctx):
    guild_id = str(ctx.guild.id)

    # Check if the server has a valid, non-expired license
    cursor.execute('''
        SELECT l.license_key, l.expires_at
        FROM redeemed_licenses r
        JOIN licenses l ON r.license_key = l.license_key
        WHERE r.guild_id = ? AND l.expires_at > ?
    ''', (guild_id, datetime.now()))

    result = cursor.fetchone()

    if not result:
        await ctx.send(embed=genembed('No license', 'This server does not have a license, if you have a license, Run : ;redeemlicense <license>'))
        return

    license_key, expires_at = result
    embed = genembed('Valid license', f'This server has a valid license expiring on {expires_at}.')
    embed.set_footer(text=license_key)
    await ctx.send(embed=embed)

@bot.command(name='login', help='Lets you link your last.fm account to the bot.')
async def login(ctx, lastfm_username):

    guild_id = str(ctx.guild.id)

    # Check if the server has a valid, non-expired license
    cursor.execute('''
        SELECT l.license_key, l.expires_at
        FROM redeemed_licenses r
        JOIN licenses l ON r.license_key = l.license_key
        WHERE r.guild_id = ? AND l.expires_at > ?
    ''', (guild_id, datetime.now()))

    result = cursor.fetchone()

    if not result:
        await ctx.send(embed=genembed('No license', 'This server does not have a license, if you have a license, Run : ;redeemlicense <license>'))
        return


    # Check if the Last.fm username is valid
    if not is_valid_lastfm_user(lastfm_username):
        await ctx.send(embed=genembed('Failed', f'Incorrect username : {lastfm_username}'))
        return

    # Load existing user data
    user_data = load_user_data()

    # Map the Discord user ID to the Last.fm username
    discord_user_id = str(ctx.author.id)
    user_data[discord_user_id] = lastfm_username

    # Save the updated user data
    save_user_data(user_data)

    await ctx.send(embed=genembed('Successfully linked your account', f'You have linked your last.fm account ({lastfm_username}) successfully.'))

@bot.command(name='np', help='Uses last.fm to see whats currently playing or was last playing.')
async def now_playing(ctx):

    guild_id = str(ctx.guild.id)

    # Check if the server has a valid, non-expired license
    cursor.execute('''
        SELECT l.license_key, l.expires_at
        FROM redeemed_licenses r
        JOIN licenses l ON r.license_key = l.license_key
        WHERE r.guild_id = ? AND l.expires_at > ?
    ''', (guild_id, datetime.now()))

    result = cursor.fetchone()

    if not result:
        await ctx.send(embed=genembed('No license', 'This server does not have a license, if you have a license, Run : ;redeemlicense <license>'))
        return

    # Load user data
    user_data = load_user_data()

    # Get the Discord user ID
    discord_user_id = str(ctx.author.id)

    # Check if the user has linked their Last.fm account
    if discord_user_id not in user_data:
        await ctx.send(embed=genembed(f'You haven\'t linked your account', 'You have to link your account, Run : ;login <username>'))
        return

    # Fetch the Last.fm username
    lastfm_username = user_data[discord_user_id]

    # Get the currently playing or last played track
    info = get_lastfm_user_info(lastfm_username)
    if info:
        if info['now_playing']:
            await ctx.send(embed=genembed(f'🎵 Now playing : {info["name"]}', field1=f'Artist : {info["artist"]}', field2=f'Album : {info["album"]}'))
        else:
            await ctx.send(embed=genembed(f'🎵 Last listening to : {info["name"]}', field1=f'Artist : {info["artist"]}', field2=f'Album : {info["album"]}'))
    else:
        await ctx.send(embed=genembed(f'Couldn\'t fetch info.', 'We failed to fetch info.'))

# Helper function to fetch Last.fm user info
def get_lastfm_user_info(username):
    url = f"http://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user={username}&api_key={LASTFM_API_KEY}&format=json&limit=1"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        tracks = data.get('recenttracks', {}).get('track', [])
        if tracks:
            track = tracks[0]
            artist = track.get('artist', {}).get('#text', 'Unknown Artist')
            name = track.get('name', 'Unknown Track')
            album = track.get('album', {}).get('#text', 'Unknown Album')
            now_playing = '@attr' in track and 'nowplaying' in track['@attr'] and track['@attr']['nowplaying'] == 'true'
            return {
                'artist': artist,
                'name': name,
                'album': album,
                'now_playing': now_playing
            }
    return None



@bot.command(name='profile', help='Gives information about your last.fm profile')
async def profile(ctx):

    guild_id = str(ctx.guild.id)

    # Check if the server has a valid, non-expired license
    cursor.execute('''
        SELECT l.license_key, l.expires_at
        FROM redeemed_licenses r
        JOIN licenses l ON r.license_key = l.license_key
        WHERE r.guild_id = ? AND l.expires_at > ?
    ''', (guild_id, datetime.now()))

    result = cursor.fetchone()

    if not result:
        await ctx.send(embed=genembed('No license', 'This server does not have a license, if you have a license, Run : ;redeemlicense <license>'))
        return

    # Load user data
    user_data = load_user_data()

    # Get the Discord user ID
    discord_user_id = str(ctx.author.id)

    # Check if the user has linked their Last.fm account
    if discord_user_id not in user_data:
        await ctx.send(embed=genembed(f'You haven\'t linked your account', 'You have to link your account, Run : ;login <username>'))
        return

    # Fetch the Last.fm username
    lastfm_username = user_data[discord_user_id]

    # Get the Last.fm profile information
    profile_info = get_lastfm_profile_info(lastfm_username)
    if profile_info:
        await ctx.send(embed=genembed(f'🎵 Last.fm profile : {profile_info["username"]}', f'[View Profile]({profile_info["profile_url"]})', f'Playcount: {profile_info["playcount"]}', f'Registered: {profile_info["registered"]}'))
    else:
        await ctx.send(embed=genembed('Failed', 'Failed to get information'))

# Helper function to fetch Last.fm user info
def get_lastfm_user_info(username):
    url = f"http://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user={username}&api_key={LASTFM_API_KEY}&format=json&limit=1"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        tracks = data.get('recenttracks', {}).get('track', [])
        if tracks:
            track = tracks[0]
            artist = track.get('artist', {}).get('#text', 'Unknown Artist')
            name = track.get('name', 'Unknown Track')
            album = track.get('album', {}).get('#text', 'Unknown Album')
            now_playing = '@attr' in track and 'nowplaying' in track['@attr'] and track['@attr']['nowplaying'] == 'true'
            return {
                'artist': artist,
                'name': name,
                'album': album,
                'now_playing': now_playing
            }
    return None


@bot.command(name='membercount', help='Gives a member count of your server.')
async def membercount(ctx):

    guild_id = str(ctx.guild.id)

    # Check if the server has a valid, non-expired license
    cursor.execute('''
        SELECT l.license_key, l.expires_at
        FROM redeemed_licenses r
        JOIN licenses l ON r.license_key = l.license_key
        WHERE r.guild_id = ? AND l.expires_at > ?
    ''', (guild_id, datetime.now()))

    result = cursor.fetchone()

    if not result:
        await ctx.send(embed=genembed('No license', 'This server does not have a license, if you have a license, Run : ;redeemlicense <license>'))
        return
    
    membercount = len(ctx.guild.members)
    await ctx.send(embed=genembed('👥 Member Stats', f'**{membercount}** members in **{ctx.guild.name}**'))

@bot.command(name='botinfo', help='Displays information about the bot')
async def botinfo(ctx):

    guild_id = str(ctx.guild.id)

    # Check if the server has a valid, non-expired license
    cursor.execute('''
        SELECT l.license_key, l.expires_at
        FROM redeemed_licenses r
        JOIN licenses l ON r.license_key = l.license_key
        WHERE r.guild_id = ? AND l.expires_at > ?
    ''', (guild_id, datetime.now()))

    result = cursor.fetchone()

    if not result:
        await ctx.send(embed=genembed('No license', 'This server does not have a license, if you have a license, Run : ;redeemlicense <license>'))
        return

    current_time = time.time()
    uptime_seconds = int(current_time - starttime)

    # Convert uptime to days, hours, minutes, and seconds
    uptime_days = uptime_seconds // 86400  # 86400 seconds in a day
    uptime_seconds %= 86400
    uptime_hours = uptime_seconds // 3600  # 3600 seconds in an hour
    uptime_seconds %= 3600
    uptime_minutes = uptime_seconds // 60  # 60 seconds in a minute
    uptime_seconds %= 60

    totalmembers = 0
    for guild in bot.guilds:
        for member in guild.members:
            totalmembers += 1
    current_file = __file__
    try:
        with open(current_file, 'r', encoding='utf-8') as file:
            global line_count
            line_count = sum(1 for line in file)
    except Exception as e:
        await ctx.send(f"Could not count lines of code: {e}")

    e = genembed(f'{botname} Info', f'Statistics and info about {botname}')
    e.add_field(name='Uptime', value=f'{uptime_days}d, {uptime_hours}h, {uptime_minutes}m, {uptime_seconds}s')
    e.add_field(name='Prefix', value=prefix)
    e.add_field(name='Servers', value=len(bot.guilds))
    e.add_field(name='Members', value=totalmembers)
    e.add_field(name='Commands', value=len(bot.all_commands))
    e.add_field(name='Lines', value=line_count)
    await ctx.send(embed=e)

@bot.command(name='serverinfo', help='Displays information about the server')
async def si(ctx: commands.Context):
    guild_id = str(ctx.guild.id)

    # Check if the server has a valid, non-expired license
    cursor.execute('''
        SELECT l.license_key, l.expires_at
        FROM redeemed_licenses r
        JOIN licenses l ON r.license_key = l.license_key
        WHERE r.guild_id = ? AND l.expires_at > ?
    ''', (guild_id, datetime.now()))

    result = cursor.fetchone()

    if not result:
        await ctx.send(embed=genembed('No license', 'This server does not have a license, if you have a license, Run : ;redeemlicense <license>'))
        return
    guild = ctx.guild
    text_channels = len(guild.text_channels)
    voice_channels = len(guild.voice_channels)
    total_channels = text_channels + voice_channels
    # Count roles
    roles = len(guild.roles)

    # Count emojis
    emojis = len(guild.emojis)
    animated_emojis = sum(1 for emoji in guild.emojis if emoji.animated)
    embed = genembed('Server information', f'**Server information on {guild.name}**')
    embed.add_field(name='ID', value=f'{guild.id}', inline=True)
    embed.add_field(name='Owner', value=f'{ctx.guild.owner.mention}', inline=True)
    embed.add_field(name='Created on', value=f'{guild.created_at.strftime("%B %d, %Y")}', inline=True)
    embed.add_field(name='Boost Tier', value=f"Level {guild.premium_tier}", inline=True)
    embed.add_field(name='Boosts', value=f'{guild.premium_subscription_count}', inline=True)
    embed.add_field(name='Members', value=f'{guild.member_count}', inline=True)
    embed.add_field(name='Channels', value=f'Total: {total_channels}\nText: {text_channels}\nVoice: {voice_channels}', inline=True)
    embed.add_field(name='Roles', value=f'{roles}', inline=True)
    embed.add_field(name='Emojis', value=f'{emojis} ({animated_emojis} animated)', inline=True)
    if guild.icon:
        embed.set_image(url=guild.icon.url)

    await ctx.send(embed=embed)

@bot.command(name='av', help='Gets a users avatar.')
async def avatar(ctx, user: discord.User=None):
    guild_id = str(ctx.guild.id)

    # Check if the server has a valid, non-expired license
    cursor.execute('''
        SELECT l.license_key, l.expires_at
        FROM redeemed_licenses r
        JOIN licenses l ON r.license_key = l.license_key
        WHERE r.guild_id = ? AND l.expires_at > ?
    ''', (guild_id, datetime.now()))

    result = cursor.fetchone()

    if not result:
        await ctx.send(embed=genembed('No license', 'This server does not have a license, if you have a license, Run : ;redeemlicense <license>'))
        return
    if user:
        image = user.display_avatar
        imageurl = image.url

        embed = genembed(f'{user.name}s avatar')
        embed.set_image(url=imageurl)
    else:
        image = ctx.author.display_avatar

        imageurl = image.url

        embed = genembed(f'{ctx.author.name}s avatar')
        embed.set_image(url=imageurl)

    await ctx.send(embed=embed)

@bot.command(name="ping", help='Gets the bots latency')
async def ping(ctx):
    lbefore = time.monotonic()
    guild_id = str(ctx.guild.id)

    # Check if the server has a valid, non-expired license
    cursor.execute('''
        SELECT l.license_key, l.expires_at
        FROM redeemed_licenses r
        JOIN licenses l ON r.license_key = l.license_key
        WHERE r.guild_id = ? AND l.expires_at > ?
    ''', (guild_id, datetime.now()))

    result = cursor.fetchone()

    if not result:
        await ctx.send(embed=genembed('No license', 'This server does not have a license, if you have a license, Run : ;redeemlicense <license>'))
        return
    lafter = time.monotonic()
    licensecheck = round((lafter - lbefore) * 1000)  # Convert to milliseconds
    # Calculate WebSocket latency
    ws_latency = round(bot.latency * 1000)  # Convert to milliseconds

    # Calculate API latency
    before = time.monotonic()
    message = await ctx.send("Calculating ping...")
    after = time.monotonic()
    api_latency = round((after - before) * 1000)  # Convert to milliseconds

    # Create an embed to display the ping
    embed = genembed(title="🏓 Pong!")
    embed.add_field(name="WebSocket Latency", value=f"{ws_latency}ms", inline=True)
    embed.add_field(name="API Latency", value=f"{api_latency}ms", inline=True)
    embed.add_field(name="License Checking", value=f"{licensecheck}ms", inline=True)


    await message.edit(content=None, embed=embed)

@bot.command(name="userinfo", help="Gets information about a user.")
async def userinfo(ctx, member: discord.Member = None):

    guild_id = str(ctx.guild.id)

    # Check if the server has a valid, non-expired license
    cursor.execute('''
        SELECT l.license_key, l.expires_at
        FROM redeemed_licenses r
        JOIN licenses l ON r.license_key = l.license_key
        WHERE r.guild_id = ? AND l.expires_at > ?
    ''', (guild_id, datetime.now()))

    result = cursor.fetchone()

    if not result:
        await ctx.send(embed=genembed('No license', 'This server does not have a license, if you have a license, Run : ;redeemlicense <license>'))
        return

    # If no member is mentioned, use the command author
    if not member:
        member = ctx.author

    # Get user information
    username = member.name
    discriminator = member.discriminator
    user_id = member.id
    avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
    created_at = member.created_at.strftime("%B %d, %Y")
    joined_at = member.joined_at.strftime("%B %d, %Y") if member.joined_at else "Unknown"
    status = str(member.status).capitalize()
    roles = [role.mention for role in member.roles if role.name != "@everyone"]
    roles_str = ", ".join(roles) if roles else "No roles"

    # Create the embed using your genembed function
    embed = genembed(
        title=f"User Information: {username}#{discriminator}",
        desc=f"Here's the information for {member.mention}."
    )
    embed.set_thumbnail(url=avatar_url)
    embed.add_field(name="ID", value=user_id, inline=True)
    embed.add_field(name="Status", value=status, inline=True)
    embed.add_field(name="Account Created", value=created_at, inline=False)
    embed.add_field(name="Joined Server", value=joined_at, inline=False)
    embed.add_field(name="Roles", value=roles_str, inline=False)

    await ctx.send(embed=embed)

@bot.command(name='pin', help='Reply to a message with this command to pin it!')
async def pinmsg(ctx):

    guild_id = str(ctx.guild.id)

    # Check if the server has a valid, non-expired license
    cursor.execute('''
        SELECT l.license_key, l.expires_at
        FROM redeemed_licenses r
        JOIN licenses l ON r.license_key = l.license_key
        WHERE r.guild_id = ? AND l.expires_at > ?
    ''', (guild_id, datetime.now()))

    result = cursor.fetchone()

    if not result:
        await ctx.send(embed=genembed('No license', 'This server does not have a license, if you have a license, Run : ;redeemlicense <license>'))
        return

    # Check if the message is a reply
    if not ctx.message.reference:
        await ctx.send(embed=genembed("Error", "You must reply to a message to pin it."))
        return

    # Fetch the replied-to message
    replied_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)

    # Check if the message is already pinned
    if replied_message.pinned:
        await ctx.send(embed=genembed("Error", "The message is already pinned."))
        return

    # Pin the message
    try:
        await replied_message.pin()
        await ctx.send(embed=genembed("Success", f"Message pinned by {ctx.author.mention}."))
    except discord.Forbidden:
        await ctx.send(embed=genembed("Error", "I don't have permission to pin messages in this channel."))
    except discord.HTTPException as e:
        await ctx.send(embed=genembed("Error", f"Failed to pin the message: {e}"))

# // MODERATOR

@bot.command(name='b', help='Bans a user')
@commands.has_permissions(ban_members=True)
async def ban(ctx: commands.Context, user: discord.User, *, reason: str=None):
    guild_id = str(ctx.guild.id)

    # Check if the server has a valid, non-expired license
    cursor.execute('''
        SELECT l.license_key, l.expires_at
        FROM redeemed_licenses r
        JOIN licenses l ON r.license_key = l.license_key
        WHERE r.guild_id = ? AND l.expires_at > ?
    ''', (guild_id, datetime.now()))

    result = cursor.fetchone()

    if not result:
        await ctx.send(embed=genembed('No license', 'This server does not have a license, if you have a license, Run : ;redeemlicense <license>'))
        return
    
    await ctx.guild.ban(user=user, reason=reason)
    await ctx.send(embed=genembed('Banned', f'The ban hammer has struck {user.name}!'))

@bot.command(name='purge', help='Deletes a specified amount of messages')
@commands.has_permissions(manage_messages=True)
async def purge(ctx: commands.Context, amount: int):
    guild_id = str(ctx.guild.id)

    # Check if the server has a valid, non-expired license
    cursor.execute('''
        SELECT l.license_key, l.expires_at
        FROM redeemed_licenses r
        JOIN licenses l ON r.license_key = l.license_key
        WHERE r.guild_id = ? AND l.expires_at > ?
    ''', (guild_id, datetime.now()))

    result = cursor.fetchone()

    if not result:
        await ctx.send(embed=genembed('No license', 'This server does not have a license, if you have a license, Run : ;redeemlicense <license>'))
        return
    
    await ctx.channel.purge(limit=amount+1)
    await ctx.send(embed=genembed(f'Purged {amount} messages', f'Deleted {amount} messages.'))

@bot.command(name="lock", help='Locks a channel')
@commands.has_permissions(manage_channels=True)  # Check if the author has manage_channels permissions
async def lock(ctx):
    guild_id = str(ctx.guild.id)

    # Check if the server has a valid, non-expired license
    cursor.execute('''
        SELECT l.license_key, l.expires_at
        FROM redeemed_licenses r
        JOIN licenses l ON r.license_key = l.license_key
        WHERE r.guild_id = ? AND l.expires_at > ?
    ''', (guild_id, datetime.now()))

    result = cursor.fetchone()

    # Check if the bot has permission to manage channels
    if not ctx.guild.me.guild_permissions.manage_channels:
        await ctx.send(embed=genembed("Error", "I don't have permission to manage channels."))
        return

    # Get the @everyone role
    try:
        everyone_role = discord.utils.get(ctx.guild.roles, name='Member')

        # Lock the channel by denying send_messages permission
        try:
            await ctx.channel.set_permissions(everyone_role, send_messages=False)
            await ctx.send(embed=genembed("Success", f"{ctx.channel.mention} has been locked by {ctx.author.mention}."))
        except discord.Forbidden:
            await ctx.send(embed=genembed("Error", "I don't have permission to lock this channel."))
        except discord.HTTPException as e:
            await ctx.send(embed=genembed("Error", f"Failed to lock the channel: {e}"))
    except:
        await ctx.send(embed=genembed("Error", f"Your member role needs to be called 'Member' for this command to work."))

@bot.command(name="unlock", help='Unlocks a channel')
@commands.has_permissions(manage_channels=True)  # Check if the author has manage_channels permissions
async def unlock(ctx):
    guild_id = str(ctx.guild.id)

    # Check if the server has a valid, non-expired license
    cursor.execute('''
        SELECT l.license_key, l.expires_at
        FROM redeemed_licenses r
        JOIN licenses l ON r.license_key = l.license_key
        WHERE r.guild_id = ? AND l.expires_at > ?
    ''', (guild_id, datetime.now()))

    result = cursor.fetchone()
    # Check if the bot has permission to manage channels
    if not ctx.guild.me.guild_permissions.manage_channels:
        await ctx.send(embed=genembed("Error", "I don't have permission to manage channels."))
        return

    try:
        everyone_role = discord.utils.get(ctx.guild.roles, name='Member')

        # Lock the channel by denying send_messages permission
        try:
            await ctx.channel.set_permissions(everyone_role, send_messages=True)
            await ctx.send(embed=genembed("Success", f"{ctx.channel.mention} has been unlocked by {ctx.author.mention}."))
        except discord.Forbidden:
            await ctx.send(embed=genembed("Error", "I don't have permission to unlock this channel."))
        except discord.HTTPException as e:
            await ctx.send(embed=genembed("Error", f"Failed to unlock the channel: {e}"))
    except:
        await ctx.send(embed=genembed("Error", f"Your member role needs to be called 'Member' for this command to work."))

# Error handler for missing permissions
@lock.error
@unlock.error
async def lock_unlock_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(embed=genembed("Error", "You do not have permission to manage channels."))















































@bot.command(name='help', help='Shows this command.')
async def help_command(ctx, command_name: str = None):

    if command_name:
        # Handle command-specific help
        command = bot.get_command(command_name.lower())
        if command:
            embed = genembed(
                title=f"Command: {command.name}",
                desc=command.help or "No description available."
            )
            embed.add_field(name="Usage: [optional] <required>", value=f"`{prefix}{command.name} {command.signature}`", inline=False)
            await ctx.send(embed=embed)
        else:
            await ctx.send(embed=genembed("Error", f"Command `{command_name}` not found."))
        return



    select = Select(
        placeholder="Choose a category...",
        options=[
            discord.SelectOption(label="🎶 Last.fm Commands", description="Commands related to Last.fm", value="lastfm"),
            discord.SelectOption(label="🔨 Utility Commands", description="General utility commands", value="utility"),
            discord.SelectOption(label="👋 Welcome Setup", description="Setup the welcome feature", value="welc"),
            discord.SelectOption(label="🔮 Reaction Roles Setup", description="Setup reaction roles", value="react"),
            discord.SelectOption(label="🚨 Moderator Commands", description="Moderator commands", value="mod"),
            discord.SelectOption(label="✔  License Commands", description="License related commands", value="license"),
            discord.SelectOption(label="👮‍♂️ Bot Admin Commands", description="Bot Administrator commands", value="admin")
        ]
    )

    # Define the callback for the dropdown
    async def select_callback(interaction):
        if select.values[0] == "lastfm":
            embed = genembed(title="🎶 Last.fm Commands", desc="Commands related to Last.fm integration. [optional] <required>")
            embed.add_field(name="`;login <username>`", value="Link your Last.fm account.", inline=False)
            embed.add_field(name="`;np`", value="Show your currently playing or last played track.", inline=False)
            embed.add_field(name="`;profile`", value="Display your Last.fm profile information.", inline=False)
        elif select.values[0] == "utility":
            embed = genembed(title="🔨 Utility Commands", desc="General utility commands. [optional] <required>")
            embed.add_field(name="`;membercount`", value="Gets the servers member count", inline=False)
            embed.add_field(name="`;botinfo`", value="Gives the bots stats/info such as uptime, commands, etc.", inline=False)
            embed.add_field(name="`;help [command]`", value="Shows this menu.", inline=False)
            embed.add_field(name="`;serverinfo`", value="Displays server info", inline=False)
            embed.add_field(name="`;av [@user]`", value="Displays users avatar", inline=False)
            embed.add_field(name="`;ping`", value="Gets the bots latency", inline=False)
            embed.add_field(name="`;userinfo [@user]`", value="Gets information about a user", inline=False)
            embed.add_field(name="`;pin`", value="Reply to a message with this command to pin it!", inline=False)
        elif select.values[0] == "license":
            embed = genembed(title="✔ License Commands", desc="License related commands. [optional] <required>")
            embed.add_field(name="`;redeemlicense <license>`", value="Redeems a license to the server the command in ran in.", inline=False)
            embed.add_field(name="`;licensecheck`", value="Checks if the license on the server ran is valid.", inline=False)
        elif select.values[0] == "admin":
            absadasd = is_admin(ctx.author.id)
            if absadasd == False:
                embed = genembed(title="You do not have access.", desc="Access denied.")
            else:
                embed = genembed(title="👮‍♂️ Admin Commands", desc="Admin Commands. [optional] <required>")
                embed.add_field(name="`;genlicense <uses> <length>`", value="Generates a license. Length usage : <amount>d/m/y", inline=False)
                embed.add_field(name="`;dellicense <license>`", value="Deletes a license", inline=False)
                embed.add_field(name="`;licensedata <license>`", value="Lists all data of a license.", inline=False)
                embed.add_field(name="`;listadmins <user>`", value="Lists all admins IDS.", inline=False)
                embed.add_field(name="`;addadmin <user>`", value="Makes a user admin of the bot. [OWNER ONLY]", inline=False)
                embed.add_field(name="`;removeadmin <user>`", value="Removes a users admin powers with the bot. [OWNER ONLY]", inline=False)
        elif select.values[0] == "mod":
            embed = genembed(title="🚨 Moderator Commands", desc="Moderator Commands. [optional] <required>")
            embed.add_field(name="`;b <@user>`", value="Bans a user.", inline=False)
            embed.add_field(name="`;purge <amount>`", value="Deletes a specified amount of messages", inline=False)
            embed.add_field(name="`;lock`", value="Locks a channel", inline=False)
            embed.add_field(name="`;unlock`", value="Unlocks a channel", inline=False)
        elif select.values[0] == "welc":
            embed = genembed(title="👋 Welcome Setup", desc="Use this command to edit, setup, enable, disable the welcome feature. [optional] <required>")
            embed.add_field(name="`;welcome <action> [value]`", value="Run ;welcome help to see usage.", inline=False)
        elif select.values[0] == "react":
            embed = genembed(title="🔮 Reaction Roles Setup", desc="Use this command to setup reaction roles. [optional] <required>")
            embed.add_field(name="`;reactrole <#channel> <template>`", value="Templates : colors, os, countries", inline=False)

        await interaction.response.edit_message(embed=embed)

    # Attach the callback to the dropdown
    select.callback = select_callback

    # Create a view and add the dropdown to it
    view = View()
    view.add_item(select)

    # Send the initial message with the dropdown
    await ctx.send(embed=genembed(f'{botname} Help Menu', f'Choose a category below to see the commands from it.\n\n**Prefix: `{prefix}`**\n**Commands: `{len(bot.all_commands)}`**'), view=view)















bot.run(token, log_level=logging.ERROR)

"""
Add this to start of every command


    guild_id = str(ctx.guild.id)

    # Check if the server has a valid, non-expired license
    cursor.execute('''
        SELECT l.license_key, l.expires_at
        FROM redeemed_licenses r
        JOIN licenses l ON r.license_key = l.license_key
        WHERE r.guild_id = ? AND l.expires_at > ?
    ''', (guild_id, datetime.now()))

    result = cursor.fetchone()

    if not result:
        await ctx.send(embed=genembed('No license', 'This server does not have a license, if you have a license, Run : ;redeemlicense <license>'))
        return

NOTES:
Create Verification System
AutoRole system
Reaction Roles

"""
