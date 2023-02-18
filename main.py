import discord
from discord.ext import commands
import yt_dlp
from urllib.parse import urlparse
import asyncio
import os
import shutil
import sys
from dotenv import load_dotenv
from time import time
import json
from random import shuffle
from track import *
import logging

logger = logging.Logger("skrunkl")

load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
COOLDOWN = int(os.getenv('COOLDOWN', '5'))

PREFIX = 's!'
COLOR = 0xff0000

bot = commands.Bot(
    command_prefix=PREFIX,
    intents=discord.Intents(
        voice_states=True,
        guilds=True,
        guild_messages=True,
        message_content=True
    )
)

# {server_id: [(vid_file, info), ...]}
queues: dict[int, list[Track]] = {}

# {server_id: next_available_time}
cooldowns: dict[int, float] = {}

# {server_id_as_str: {list_name: [search_queries...]}}
saved_playlists: dict[str, dict[str, list[str]]] = {}


def save_to_file():
    # noinspection PyBroadException
    try:
        with open(f"saved.json", 'w') as f:
            json.dump(saved_playlists, f)
            logger.debug("successfully wrote to saved.json")
    except Exception:
        logger.error("failed to write to saved.json")


def load_from_file():
    global saved_playlists
    # noinspection PyBroadException
    try:
        with open("saved.json") as f:
            saved_playlists = json.load(f)
            logger.info("loaded saved.json successfully")
    except Exception:
        logger.error("fail reading saved.json")
        saved_playlists = {}


def main():
    if TOKEN is None:
        return ("No token provided. Please create a .env file containing the token.\n" +
                "For more information view the README.md")
    try:
        load_from_file()
        bot.run(TOKEN)
    except discord.PrivilegedIntentsRequired as err:
        return err


def keep_playing(error: Any, connection=None, server_id: int = None):

    if server_id is None or connection is None:
        return

    queue = queues[server_id]

    if error is not None:
        logger.error(f"{error}")

    try:
        path = queues[server_id][0].file_path
    except KeyError:
        logger.debug("got dc'd before finishing a song")
        return

    queues[server_id].pop(0)

    if path not in [i.file_path for i in queues[server_id]]:
        # if the song isn't queued up after this, delete from dl folder
        try:
            os.remove(path)
            logger.debug(f"successfully removed file {path}")
        except FileNotFoundError:
            logger.error(f"couldn't delete {path}")

    if len(queues):
        connection.play(
            discord.FFmpegOpusAudio(queues[server_id][0].file_path),
            after=keep_playing
        )
        logger.debug(f"started playing {queues[server_id][0].title}")
    else:
        # directory will be deleted on disconnect
        queues.pop(server_id)
        asyncio.run_coroutine_threadsafe(safe_disconnect(connection), bot.loop).result()
        logger.debug("left vc because nothing in queue")


@bot.command(name="addlist", aliases=["al"])
async def add_to_list(ctx: commands.Context, *args):
    server_id = ctx.guild.id

    if str(server_id) not in saved_playlists:
        saved_playlists[str(server_id)] = {}

    save = saved_playlists[str(server_id)]
    if not (len(args) > 1):
        await ctx.send(f"you are using incorrectly")
        return

    lname = args[0]
    quer = ' '.join(args[1:])

    if lname not in save:
        await ctx.send(f"created new list {lname}")
        save[lname] = []

    save[lname].append(quer)
    await ctx.send(f"added {quer} to list")
    save_to_file()


@bot.command(name="dellist", aliases=["dl"])
async def delete_list(ctx: commands.Context, *args):
    server_id = ctx.guild.id

    if str(server_id) not in saved_playlists:
        saved_playlists[str(server_id)] = {}

    quer = ' '.join(args)

    if quer in saved_playlists[str(server_id)]:
        saved_playlists[str(server_id)].pop(quer)
        await ctx.send("deleted list")
        return
    await ctx.send("you are a fucking buffoon")


@bot.command(name="playlist", aliases=['pl'])
async def play_list(ctx: commands.Context, *args):
    server_id = ctx.guild.id

    if str(server_id) not in saved_playlists:
        saved_playlists[str(server_id)] = {}

    save = saved_playlists[str(server_id)]
    quer = ' '.join(args)

    if quer not in save:
        await ctx.send(f"{ctx.message.author.mention} this list no exist")
        return

    if server_id not in cooldowns:
        cooldowns[server_id] = 0
    if cooldowns[server_id] > time():
        await ctx.send(f"{ctx.message.author.mention} stop spamming (there is a cooldown)")
        return
    else:
        cooldowns[server_id] = time()+COOLDOWN

    test = save[quer]
    shuffle(test)

    for _ in test:

        logger.debug(f"downloading {_}")

        query = _
        voice_state = ctx.author.voice
        if not await sense_checks(ctx, voice_state=voice_state):
            return

        # this is how it's determined if the url is valid (i.e. whether to search or not) under the hood of yt-dlp
        will_need_search = not urlparse(query).scheme

        # source address as 0.0.0.0 to force ipv4 because ipv6 breaks it for some reason
        # this is equivalent to --force-ipv4 (line 312 of https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/options.py
        await ctx.send(f'looking for `{query}`...')
        with yt_dlp.YoutubeDL({'format': 'worstaudio',
                               'source_address': '0.0.0.0',
                               'default_search': 'ytsearch',
                               'outtmpl': '%(id)s.%(ext)s',
                               'noplaylist': True,
                               'allow_playlist_files': False,
                               'paths': {'home': f'./dl/{server_id}'}}) as ydl:

            info = ydl.extract_info(query, download=False)

            # make sure only one song
            if 'entries' in info:
                info = info['entries'][0]

            # do not show links because chat clutter
            await ctx.send(f'downloading `{info["title"]}`')

            ydl.download([query])

        path = f'./dl/{server_id}/{info["id"]}.{info["ext"]}'

        # add a YoutubeTrack to the queue
        if server_id not in queues:
            queues[server_id] = []
        queues[server_id].append(YoutubeTrack(path, info))

        try:
            conn = await voice_state.channel.connect()
        except discord.ClientException:
            conn = get_voice_client_from_channel_id(voice_state.channel.id)

        await ctx.send(f"playing `{info['title']}`")

        conn.play(
            discord.FFmpegOpusAudio(path),
            after=keep_playing
        )


@bot.command(name='queue', aliases=['q'])
async def show_queue(ctx: commands.Context, *args):
    try:
        queue = queues[ctx.guild.id]
    except KeyError:
        queue = None

    if not await sense_checks(ctx):
        return

    if queue is None:
        await ctx.send(f'{ctx.message.author.mention} the bot isn\'t playing anything')
    else:
        def title_str(val):
            return '‣ %s\n\n' % val[1] if val[0] == 0 else '**%2d:** %s\n' % val

        queue_str = ''.join(map(title_str, enumerate([track.title for track in queue])))
        embed_ = discord.Embed(color=COLOR)
        embed_.add_field(name='currently playing:', value=queue_str)
        await ctx.send(embed=embed_)


@bot.command(name='skip', aliases=['s'])
async def skip(ctx: commands.Context, *args):
    try:
        queue_length = len(queues[ctx.guild.id])
    except KeyError:
        queue_length = 0

    if queue_length == 0:
        await ctx.send(f'{ctx.message.author.mention} the bot isn\'t playing anything')
        return

    if not await sense_checks(ctx):
        return

    try:
        n_skips = int(args[0])
    except IndexError:
        n_skips = 1
    except ValueError:
        if args[0] == 'all':
            n_skips = queue_length
        else:
            n_skips = 1

    if n_skips == 1:
        message = f'{ctx.message.author.mention} skipping track'
    elif n_skips < queue_length:
        message = f'{ctx.message.author.mention} skipping `{n_skips}` of `{queue_length}` tracks'
    else:
        message = f'{ctx.message.author.mention} skipping all tracks'
        n_skips = queue_length

    await ctx.send(message)

    voice_client: discord.VoiceClient = get_voice_client_from_channel_id(ctx.author.voice.channel.id)
    for _ in range(n_skips - 1):
        queues[ctx.guild.id].pop(0)
    voice_client.stop()


@bot.command(name='disconnect', aliases=['dc'])
async def disconnect_from_vc(ctx: commands.Context, *args):
    voice_state = ctx.author.voice
    try:
        conn = await voice_state.channel.connect()
    except discord.ClientException:
        conn = get_voice_client_from_channel_id(voice_state.channel.id)
    await ctx.send(f"{ctx.message.author.mention} disconnecting from vc")
    conn.stop()
    await safe_disconnect(conn)
    queues.pop(ctx.guild.id)


@bot.command(name="unplay", aliases=["fuck", "up"])
async def i_messed_up(ctx: commands.Context, *args):
    voice_state = ctx.author.voice
    server_id = ctx.guild.id
    if not await sense_checks(ctx, voice_state=voice_state):
        return

    if not len(queues[server_id]):
        await ctx.send("there is nothing playing, idiot")
        return
    if len(queues[server_id]) == 1:
        await ctx.send("disconnecting because only one item in queue")
        await disconnect_from_vc(ctx, *args)
        return
    if len(queues[server_id]) > 2:
        await ctx.send(f"{ctx.message.author.mention} " +
                       f"removing {queues[server_id][len(queues[server_id])-1].title} from queue")
        queues[server_id].pop()
        return


@bot.command(name="skrunkl", aliases=["skrunk", "skrunkly", "theme"])
async def skrunkly_theme(ctx: commands.Context, *args):
    voice_state = ctx.author.voice
    if not await sense_checks(ctx, voice_state=voice_state):
        return

    if ctx.guild.id not in queues:
        queues[ctx.guild.id] = []

    server_id = ctx.guild.id

    await ctx.send(f"{ctx.message.author.mention} playing skrunkly theme song")

    queues[server_id].append(SkrunklyTheme())

    try:
        conn = await voice_state.channel.connect()
    except discord.ClientException:
        conn = get_voice_client_from_channel_id(voice_state.channel.id)

    if not len(queues[server_id]):
        keep_playing(None, conn, server_id)


@bot.command(name='play', aliases=['p'])
async def play(ctx: commands.Context, *args):
    voice_state = ctx.author.voice
    if not await sense_checks(ctx, voice_state=voice_state):
        return

    query = ' '.join(args)
    # this is how it's determined if the url is valid (i.e. whether to search or not) under the hood of yt-dlp
    will_need_search = not urlparse(query).scheme

    server_id = ctx.guild.id

    if server_id not in cooldowns:
        cooldowns[server_id] = 0
    if cooldowns[server_id] > time():
        await ctx.send(f"{ctx.message.author.mention} stop spamming (there is a cooldown)")
        return
    else:
        cooldowns[server_id] = time()+COOLDOWN

    # source address as 0.0.0.0 to force ipv4 because ipv6 breaks it for some reason
    # this is equivalent to --force-ipv4 (line 312 of https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/options.py)
    await ctx.send(f'looking for `{query}`...')
    with yt_dlp.YoutubeDL({'format': 'worstaudio',
                           'source_address': '0.0.0.0',
                           'default_search': 'ytsearch',
                           'outtmpl': '%(id)s.%(ext)s',
                           'noplaylist': True,
                           'allow_playlist_files': False,
                           'paths': {'home': f'./dl/{server_id}'}}) as ydl:
        info = ydl.extract_info(query, download=False)
        if 'entries' in info:
            info = info['entries'][0]

        # send link if it was a search, otherwise send title as sending link again would clutter chat with previews
        await ctx.send('downloading '
                       + (f'https://youtu.be/{info["id"]}' if will_need_search else f'`{info["title"]}`'))
        ydl.download([query])

    path = f'./dl/{server_id}/{info["id"]}.{info["ext"]}'

    if server_id not in queues:
        queues[server_id] = []

    if len(queues[server_id]):
        await ctx.send(f"{ctx.message.author.mention} adding {info['title']} to queue")

    queues[server_id].append(YoutubeTrack(path, info))

    try:
        conn = await voice_state.channel.connect()
    except discord.ClientException:
        conn = get_voice_client_from_channel_id(voice_state.channel.id)

    await ctx.send(f"playing `{info['title']}`")

    conn.play(
        discord.FFmpegOpusAudio(path),
        after=keep_playing
    )


def get_voice_client_from_channel_id(channel_id: int):
    for voice_client in bot.voice_clients:
        if voice_client.channel.id == channel_id:
            return voice_client


async def safe_disconnect(connection):
    if not connection.is_playing():
        logger.debug("disconnected safely")
        await connection.disconnect()


async def sense_checks(ctx: commands.Context, voice_state=None) -> bool:
    if voice_state is None:
        voice_state = ctx.author.voice

    if voice_state is None:
        logger.warning("user needs to be in vc")
        await ctx.send(f'{ctx.message.author.mention} you have to be in a vc to use this command (try s!dc if broken)')
        return False

    if bot.user.id not in [member.id for member in ctx.author.voice.channel.members] and ctx.guild.id in queues.keys():
        logger.warning("user needs to be in same vc as bot")
        await ctx.send(f'{ctx.message.author.mention} you have to be in the same vc as the bot to use this command (' +
                       f'try s!dc if broken)')
        return False

    logger.debug("passed sense checks")
    return True


@bot.event
async def on_voice_state_update(member: discord.User, before: discord.VoiceState, after: discord.VoiceState):
    if member != bot.user:
        return

    if before.channel is None and after.channel is not None:  # joined vc
        logger.debug("joined channel")
        return
    if before.channel is not None and after.channel is None:  # disconnected from vc
        logger.debug("left channel")

        # clean up
        server_id = before.channel.guild.id

        try:
            queues.pop(server_id)
            logger.debug("successfully removed server id from queues")
        except KeyError:
            logger.warning("server id not found in queues while cleaning up")

        try:
            shutil.rmtree(f'./dl/{server_id}/')
            logger.debug("successfully removed cached downloads")
        except FileNotFoundError:
            logger.error("could not remove cached files")


@bot.event
async def on_command_error(event: str, *args, **kwargs):
    type_, value, traceback = sys.exc_info()
    logger.critical(f"error\ntraceback={traceback}\ntype={type_}\nvalue={value}\nevent={event}")


@bot.event
async def on_ready():
    logger.debug(f'logged in successfully as {bot.user.name}')


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemError as err_:
        print(err_)
