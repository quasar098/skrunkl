import os
import shutil
import sys
from random import shuffle
from time import time

import discord
from discord.ext import commands
from dotenv import load_dotenv

from data import SkrunklData, ServerID, Playlist
from track import *

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

data = SkrunklData(bot)


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

        await data.try_play(ctx)


@bot.command(name='queue', aliases=['q'])
async def show_queue(ctx: commands.Context, *args):

    if not await sense_checks(ctx):
        return

    server_id = ServerID(ctx.guild.id)
    queue = data.get_queue(server_id)

    if len(queue) == 0:
        await mention(ctx, f'the bot isn\'t playing anything')
        return

    queue_text = ""

    for position, track in enumerate(queue):
        if position == 0:
            queue_text += f"{queue.first.title}\n\n"
            continue
        queue_text += f"**{position}:** {track.title}\n"

    embed_ = discord.Embed(color=COLOR)
    embed_.add_field(name='currently playing:', value=queue_text)
    await ctx.send(embed=embed_)


@bot.command(name='skip', aliases=['s'])
async def skip(ctx: commands.Context, *args: str):

    if not await sense_checks(ctx):
        return

    server_id = ServerID(ctx.guild.id)
    queue = data.get_queue(server_id)

    if len(queue) == 0:
        await ctx.send(f'{ctx.message.author.mention} the bot isn\'t playing anything')
        return

    n_skips = 1
    if len(args):
        try:
            if args[0].isnumeric():
                n_skips = int(args[0])
        except ValueError:
            await mention(ctx, "invalid number")
            return

    if n_skips == 1:
        message = f'skipping track'
    elif n_skips < len(queue):
        message = f'skipping `{n_skips}` of `{len(queue)}` tracks'
    else:
        await mention(ctx, "just use the disconnect command instead")
        return

    await mention(ctx, message)

    await data.stop_playing(ctx)

    for _ in range(n_skips-1):
        data.logger.info(f"skipping track, there's {len(queue)} left")
        if len(queue):
            queue.pop(0)

    data.logger.info("tracks skips finished")

    await data.try_play(ctx)


@bot.command(name='disconnect', aliases=['dc'])
async def disconnect_from_vc(ctx: commands.Context, *args):
    await data.disconnect(ctx)
    await ctx.send("disconnected from vc")


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

    if len(queue):
        await mention(ctx, "queuing skrunkly theme song")
    else:
        await mention(ctx, "playing skrunkly theme song")

    queue.add(SkrunklyTheme())

    await data.try_play(ctx)


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

    yt_track = queue.add_youtube(query)

    if len(queue):
        await mention(ctx, f"adding `{yt_track.title}` to queue")
    else:
        await mention(ctx, f"playing {yt_track.title}")

    await data.try_play(ctx)


def get_voice_client_from_channel_id(channel_id: int):
    for voice_client in bot.voice_clients:
        if voice_client.channel.id == channel_id:
            return voice_client


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
        data.clear_connection(server_id)

        if os.path.exists(f'./dl/{server_id}/'):
            try:
                shutil.rmtree(f'./dl/{server_id}/')
                data.logger.info("successfully removed cached downloads")
            except FileNotFoundError:
                data.logger.error("could not remove cached files")


@bot.event
async def on_command_error(context, exception):
    data.logger.critical(f"command error, exception={exception}")


@bot.event
async def on_ready():
    data.logger.debug(f'logged in successfully as {bot.user.name}')


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemError as err_:
        print(err_)
