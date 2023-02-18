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
from random import shuffle
from track import *
from queue import Queue
from data import SkrunklData, ServerID, Playlist

load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
COOLDOWN = int(os.getenv('COOLDOWN', '5'))

PREFIX = 's!'
COLOR = 0x01a8f4

bot = commands.Bot(
    command_prefix=PREFIX,
    intents=discord.Intents(
        voice_states=True,
        guilds=True,
        guild_messages=True,
        message_content=True
    )
)

data = SkrunklData()


async def mention(ctx: commands.Context, message: str):
    await ctx.send(f"{ctx.message.author.mention} {message}")


def main():
    if TOKEN is None:
        return ("No token provided. Please create a .env file containing the token.\n" +
                "For more information view the README.md")
    try:
        bot.run(TOKEN)
    except discord.PrivilegedIntentsRequired as err:
        return err


def keep_playing_gen(conn, server_id: ServerID):
    return lambda _: keep_playing(_, conn, server_id)


def keep_playing(error: Any, connection, server_id: ServerID):
    queue = data.get_queue(server_id)

    if error is not None:
        data.logger.error(f"{error}")

    first = queue.first
    if first is None:
        asyncio.run_coroutine_threadsafe(safe_disconnect(connection), bot.loop).result()
        data.logger.info("left vc because nothing in queue")
        return
    file_path = first.file_path

    queue.remove_first()

    if file_path not in [track.file_path for track in queue.tracks]:
        if "dl" in file_path:
            try:
                os.remove(file_path)
                data.logger.info(f"successfully removed file {file_path}")
            except FileNotFoundError:
                data.logger.error(f"couldn't delete {file_path}")

    connection.play(
        discord.FFmpegOpusAudio(queue.first.file_path),
        after=keep_playing_gen(connection, server_id)
    )
    data.logger.info(f"started playing {queue.first.title}")


@bot.command(name="addlist", aliases=["al"])
async def add_to_a_list(ctx: commands.Context, *args):
    server_id = ServerID(ctx.guild.id)

    playlists = data.get_playlists(server_id)
    if len(args) < 2:
        await ctx.send(f"you are using incorrectly")
        return

    list_name = args[0]
    query = ' '.join(args[1:])

    if list_name not in playlists:
        await ctx.send(f"created new list {list_name}")
        playlists.append(Playlist(list_name, [query]))

    await ctx.send(f"added {query} to {list_name}")
    data.save_playlists()


@bot.command(name="dellist", aliases=["dl", "delist"])
async def delete_a_list(ctx: commands.Context, *args):
    server_id = ServerID(ctx.guild.id)

    list_name = args[0] if len(args) else None

    if list_name in data.get_playlists(server_id):
        data.get_playlists(server_id).pop(list_name)
        await ctx.send(f"deleted playlist {data}")
        return

    await ctx.send("you are an idiot")


@bot.command(name="playlist", aliases=['pl'])
async def play_a_list(ctx: commands.Context, *args):
    server_id = ServerID(ctx.guild.id)

    playlists = data.get_playlists(server_id)

    if not len(args):
        await mention(ctx, "you need to specificy a list to play")
        return

    playlist_name = args[0]

    if playlist_name not in playlists:
        await mention(ctx, "this list no exist")
        return

    if data.get_cooldown(server_id) > time():
        await mention(ctx,  "stop spamming (there is a cooldown)")
        return
    else:
        data.set_cooldown(server_id, time()+COOLDOWN)

    playlist: Playlist = playlists[playlist_name]

    tracks = playlist.tracks.copy()
    shuffle(tracks)

    queue = data.get_queue(server_id)

    for track in tracks:

        data.logger.info(f"adding {track} to queue")
        await ctx.send(f"adding `{track}` to queue")

        queue.add_youtube(track)

        data.try_play()


@bot.command(name='queue', aliases=['q'])
async def show_queue(ctx: commands.Context, *args):

    if not await sense_checks(ctx):
        return

    server_id = ServerID(ctx.guild.id)
    queue = data.get_queue(server_id)

    if not len(queue):
        await ctx.send(f'{ctx.message.author.mention} the bot isn\'t playing anything')
        return

    queue_text = ""

    for position, track in enumerate(queue):
        if position == 0:
            queue_text += f"{track.title}\n\n"
            continue
        queue_text += f"**{position}:**{track.title}\n"

    embed_ = discord.Embed(color=COLOR)
    embed_.add_field(name='currently playing:', value=queue_text)
    await ctx.send(embed=embed_)


@bot.command(name='skip', aliases=['s'])
async def skip(ctx: commands.Context, *args):

    if not await sense_checks(ctx):
        return

    server_id = ServerID(ctx.guild.id)
    queue = data.get_queue(server_id)

    if len(queue) == 0:
        await ctx.send(f'{ctx.message.author.mention} the bot isn\'t playing anything')
        return

    n_skips = 1
    if args[0] in ('all', 'a'):
        n_skips = len(queue)

    if n_skips == 1:
        message = f'{ctx.message.author.mention} skipping track'
    elif n_skips < len(queue):
        message = f'{ctx.message.author.mention} skipping `{n_skips}` of `{len(queue)}` tracks'
    else:
        message = f'{ctx.message.author.mention} skipping all tracks'
        n_skips = len(queue)

    await ctx.send(message)

    data.stop_playing()

    for _ in range(n_skips):
        data.logger.info(f"skipping track, there's {len(queue)} left")
        queue.pop(0)

    data.logger.info("tracks skips finished")

    data.try_play()


@bot.command(name='disconnect', aliases=['dc'])
async def disconnect_from_vc(ctx: commands.Context, *args):
    server_id = ServerID(ctx.guild.id)

    data.stop_playing()
    data.get_queue(server_id).clear()


@bot.command(name="unplay", aliases=["mistake"])
async def unplay_a_song(ctx: commands.Context, *args):
    server_id = ServerID(ctx.guild.id)
    queue = data.get_queue(server_id)

    if not await sense_checks(ctx):
        return

    if not len(queue):
        await ctx.send("there is nothing playing, idiot")
        return
    if len(queue) == 1:
        await ctx.send("use disconnect command instead")
        return
    if len(queue) >= 2:
        await mention(ctx, f"removing {queue.last.title} from queue")
        queue.pop()
        return


# this is a reference
@bot.command(name="skrunkl", aliases=["skrunk", "skrunkly", "theme", "falco"])
async def skrunkly_theme(ctx: commands.Context, *args):
    if not await sense_checks(ctx):
        return

    server_id = ServerID(ctx.guild.id)
    queue = data.get_queue(server_id)

    queue.add(SkrunklyTheme())

    if len(queue):
        await mention(ctx, "queuing skrunkly theme song")
    else:
        await mention(ctx, "playing skrunkly theme song")

    data.try_play()


@bot.command(name='play', aliases=['p'])
async def play(ctx: commands.Context, *args):
    if not await sense_checks(ctx):
        return

    server_id = ServerID(ctx.guild.id)
    queue = data.get_queue(server_id)

    query = ' '.join(args)

    if data.get_cooldown(server_id) > time():
        await mention(ctx, "stop spamming (there's a cooldown)")
        return
    else:
        data.set_cooldown(server_id, time()+COOLDOWN)

    if len(queue):
        await mention(ctx, f"adding `{query}` to queue")
    else:
        await mention(ctx, f"playing `{query}`")

    queue.add_youtube(query)

    data.try_play()


def get_voice_client_from_channel_id(channel_id: int):
    for voice_client in bot.voice_clients:
        if voice_client.channel.id == channel_id:
            return voice_client


async def safe_disconnect(connection):
    if not connection.is_playing():
        data.logger.info("disconnected safely")
        await connection.disconnect()


async def sense_checks(ctx: commands.Context) -> bool:
    voice_state = ctx.author.voice
    server_id = ServerID(ctx.guild.id)
    queue = data.get_queue(server_id)

    if voice_state is None:
        data.logger.warning("user needs to be in vc")
        await mention(ctx, 'you have to be in a vc to use this command (try s!dc if broken)')
        return False

    if bot.user.id not in [member.id for member in ctx.author.voice.channel.members] and len(queue):
        data.logger.warning("user needs to be in same vc as bot")
        await mention(ctx, 'you have to be in the same vc as the bot to use this command (try s!dc if broken)')
        return False

    data.logger.debug("passed sense checks")
    return True


@bot.event
async def on_voice_state_update(member: discord.User, before: discord.VoiceState, after: discord.VoiceState):
    if member != bot.user:
        return

    if before.channel is None and after.channel is not None:  # joined vc
        data.logger.debug("joined channel")
        return

    if before.channel is not None and after.channel is None:  # disconnected from vc
        data.logger.debug("left channel")

        # clean up
        server_id = ServerID(before.channel.guild.id)

        try:
            shutil.rmtree(f'./dl/{server_id}/')
            data.logger.info("successfully removed cached downloads")
        except FileNotFoundError:
            data.logger.error("could not remove cached files")


@bot.event
async def on_command_error(event: str, *args, **kwargs):
    data.logger.critical(f"command error, event={event}")


@bot.event
async def on_ready():
    data.logger.debug(f'logged in successfully as {bot.user.name}')


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemError as err_:
        print(err_)
