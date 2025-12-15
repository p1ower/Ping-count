#!/usr/bin/env python3
"""
Discord Role Ping Counter Bot
Tracks when users mention/ping roles and provides statistics.
Uses CSV for data storage (no database required).
Discord.py v2.3+
"""
from collections import Counter
import discord
from discord import app_commands
from discord.ext import commands, tasks
import csv
import os
import json
from datetime import datetime, timedelta, timezone
from collections import Counter, defaultdict
from discord import File

import matplotlib.pyplot as plt
import io
from utils.timestamped_print import TimestampedPrint

# Logging aktivieren
logger = TimestampedPrint(log_file="bot.log", color=True)

# Configuration
CLEANUP_DAYS = 30  # Remove entries older than this many days
TOKEN = os.environ['PING_COUNT_TOKEN']
CSV_PATH = "role_pings.csv"

# Configure bot intents (permissions for what the bot can see/do)
intents = discord.Intents.default()
intents.message_content = True  # Required to read message content
intents.guilds = True  # Required to access guild information
intents.members = True  # Required to get member information


# Daily cleanup task - runs every 24 hours
@tasks.loop(hours=24)
async def daily_cleanup():
    """Automatically clean up old entries every 24 hours."""
    cleanup_old_entries()


# Initialize the bot
bot = commands.Bot(command_prefix="!", intents=intents)

# ========== Spoiler Reaction JSON Management ==========


def _reaction_json_path(guild_id):
    return f"data/reactions/stats/{guild_id}.json"


def ensure_reaction_json_exists(guild_id):
    """Make sure the JSON file exists for the guild."""
    path = _reaction_json_path(guild_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"reactions": []}, f, indent=4)


def append_spoiler_reaction_json(guild_id, message_id, user_id, emoji):
    """Save a spoiler reaction into <guild>.json"""
    ensure_reaction_json_exists(guild_id)
    path = _reaction_json_path(guild_id)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    entry = {
        "message_id": str(message_id),
        "user_id": str(user_id),
        "emoji": str(emoji),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    data["reactions"].append(entry)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def read_reaction_json(guild_id):
    """Read <guild>.json reactions."""
    ensure_reaction_json_exists(guild_id)
    path = _reaction_json_path(guild_id)

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["reactions"]


def reaction_stats_path(guild_id):
    return f"data/reactions/stats/{guild_id}.json"


def load_reaction_stats(guild_id):
    path = reaction_stats_path(guild_id)
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump({"reactions": []}, f)
        return {"reactions": []}

    with open(path, "r") as f:
        return json.load(f)


def save_reaction_stats(guild_id, data):
    path = reaction_stats_path(guild_id)
    with open(path, "w") as f:
        json.dump(data, f, indent=4)


def record_reaction(guild_id, message_id, user_id, emoji):
    data = load_reaction_stats(guild_id)

    data["reactions"].append({
        "message_id":
        str(message_id),
        "user_id":
        str(user_id),
        "emoji":
        emoji,
        "timestamp":
        datetime.now(timezone.utc).isoformat()
    })

    save_reaction_stats(guild_id, data)


def load_reaction_config(guild_id):
    path = f"data/reactions/configs/{guild_id}.json"
    if not os.path.exists(path):
        return {"rank_roles": []}
    return json.load(open(path))


async def build_role_ranking(guild, reaction_stats, reaction_config):
    # hole die rollen, die für dieses guild konfiguriert sind
    role_ids = reaction_config.get(str(guild.id), [])

    # vorbereiten
    role_totals = {role_id: 0 for role_id in role_ids}

    # Schritt 1: User → Reaktionsanzahl
    user_reaction_count = {}

    for entry in reaction_stats["reactions"]:
        uid = entry["user_id"]
        user_reaction_count[uid] = user_reaction_count.get(uid, 0) + 1

    # Schritt 2: Für jeden User prüfen, welche der konfigurierten Rollen er hat
    for user_id, reaction_count in user_reaction_count.items():
        member = guild.get_member(int(user_id))
        if not member:
            continue

        for role_id in role_ids:
            role = guild.get_role(int(role_id))
            if role and role in member.roles:
                role_totals[str(role_id)] += reaction_count

    # sortieren nach Reaktionen
    sorted_roles = sorted(role_totals.items(),
                          key=lambda x: x[1],
                          reverse=True)

    return sorted_roles


# ========== CSV File Management ==========


def ensure_csv_exists():
    """Create the CSV file with headers if it doesn't exist."""
    print("Ensuring CSV exists...")
    if not os.path.exists(CSV_PATH) or os.path.getsize(CSV_PATH) == 0:
        try:
            with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "guild_id", "role_id", "user_id", "channel_id", "timestamp"
                ])
        except Exception as e:
            print(f"Error creating CSV: {e}")


def append_ping(guild_id, role_id, user_id, channel_id):
    """
    Add a new role ping entry to the CSV file.
    
    Args:
        guild_id: Discord server ID
        role_id: The role that was pinged
        user_id: User who pinged the role
        channel_id: Channel where the ping occurred
    """
    print(f"Appending ping: {guild_id}, {role_id}, {user_id}, {channel_id}")
    ensure_csv_exists()
    try:
        with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                guild_id, role_id, user_id, channel_id,
                datetime.now(timezone.utc).isoformat()
            ])
    except Exception as e:
        print(f"Error appending ping: {e}")


def read_all_pings():
    """
    Read all ping entries from the CSV file.
    
    Returns:
        List of dictionaries containing ping data
    """
    ensure_csv_exists()
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def write_all_pings(rows):
    """
    Write all ping entries back to the CSV file (overwrites existing data).
    
    Args:
        rows: List of dictionaries to write to CSV
    """
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f,
                                fieldnames=[
                                    "guild_id", "role_id", "user_id",
                                    "channel_id", "timestamp"
                                ])
        writer.writeheader()
        writer.writerows(rows)


def cleanup_old_entries(days: int = CLEANUP_DAYS):
    if not os.path.exists(CSV_PATH):
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    kept = []
    removed = 0

    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                ts = datetime.fromisoformat(row["timestamp"])
                # Handle naive timestamps (old data) by assuming UTC
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    kept.append(row)
                else:
                    removed += 1
            except Exception as e:
                print(f"Error parsing timestamp: {e}")
                continue

    # 🚫 Wenn nichts gelöscht wurde: CSV NICHT anfassen
    if removed == 0:
        print("Cleanup: nichts zu löschen.")
        return

    # 🟢 Nur überschreiben, wenn nötig
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f,
                                fieldnames=[
                                    "guild_id", "role_id", "user_id",
                                    "channel_id", "timestamp"
                                ])
        writer.writeheader()
        writer.writerows(kept)

    print(f"✓ Cleaned up {removed} old entries (> {days} days old)")


# ========== Data Query Functions ==========


def get_top_for_role(guild_id, role_id, limit=10):
    """
    Get the top users who pinged a specific role.
    
    Args:
        guild_id: Discord server ID
        role_id: The role to check
        limit: Maximum number of users to return (default: 10)
    
    Returns:
        List of tuples: [(user_id, count), ...]
    """
    rows = read_all_pings()
    counts = Counter()
    for row in rows:
        if row["guild_id"] == str(guild_id) and row["role_id"] == str(role_id):
            counts[row["user_id"]] += 1
    return counts.most_common(limit)


def get_counts_for_user(guild_id, user_id):
    """
    Get all role ping counts for a specific user.
    
    Args:
        guild_id: Discord server ID
        user_id: The user to check
    
    Returns:
        List of tuples: [(role_id, count), ...]
    """
    rows = read_all_pings()
    counts = Counter()
    for row in rows:
        if row["guild_id"] == str(guild_id) and row["user_id"] == str(user_id):
            counts[row["role_id"]] += 1
    return counts.most_common()


def reset_role_counts(guild_id, role_id):
    """
    Reset all ping counts for a specific role.
    
    Args:
        guild_id: Discord server ID
        role_id: The role to reset
    """
    rows = read_all_pings()
    new_rows = [
        r for r in rows if not (
            r["guild_id"] == str(guild_id) and r["role_id"] == str(role_id))
    ]
    write_all_pings(new_rows)


def reset_user_counts(guild_id, user_id):
    """
    Reset all ping counts for a specific user.
    
    Args:
        guild_id: Discord server ID
        user_id: The user to reset
    """
    rows = read_all_pings()
    new_rows = [
        r for r in rows if not (
            r["guild_id"] == str(guild_id) and r["user_id"] == str(user_id))
    ]
    write_all_pings(new_rows)


# ========== general message activity ==========


def parse_ts(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def append_message_activity(guild_id, user_id, channel_id):
    file_exists = os.path.isfile("activity_messages.csv")

    with open("activity_messages.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow(["guild_id", "user_id", "channel_id", "timestamp"])

        writer.writerow(
            [guild_id, user_id, channel_id,
             datetime.utcnow().isoformat()])


# ========== Bot Events ==========


@bot.event
async def on_ready():
    """Called when the bot successfully connects to Discord."""
    ensure_csv_exists()
    for guild in bot.guilds:
        ensure_reaction_json_exists(guild.id)
    cleanup_old_entries()  # Clean up old entries on startup
    daily_cleanup.start()  # Start the daily cleanup task
    await bot.tree.sync()  # Sync slash commands with Discord

    # Loop through all servers (guilds) the bot is connected to
    for guild in bot.guilds:
        print(
            f"✅ Logged in as {bot.user} on {guild.name} — Slash Commands synced."
        )


@bot.event
async def on_message(message: discord.Message):
    """
    Triggered whenever a message is sent in a server the bot can see.
    Records role pings to the CSV file.
    """
    # Ignore messages from bots and DMs
    if message.author.bot or not message.guild:
        return

    append_message_activity(message.guild.id, message.author.id,
                            message.channel.id)

    # Check if any roles were mentioned
    for role in message.role_mentions:
        # Only track mentionable (pingable) roles
        if not role.mentionable:
            #print(f"Skipping unmentionable role: {role.name}")
            continue

        # Record the ping
        append_ping(guild_id=message.guild.id,
                    role_id=role.id,
                    user_id=message.author.id,
                    channel_id=message.channel.id)
    # === Spoiler Image Detection =====================================
    is_spoiler = False

    # Case 1: Attachments with "SPOILER_" prefix
    for attachment in message.attachments:
        if attachment.filename.startswith("SPOILER_"):
            is_spoiler = True
            break

    # Case 2: Text spoiler formatting ||like this||
    if "||" in message.content:
        is_spoiler = True

    # Mark message as spoiler-tracked
    if is_spoiler:
        # We only need to record the message_id,
        # the reactions will populate the data later.
        print(
            f"[SpoilerTracker] Marked message {message.id} as spoiler content."
        )


# ========== Slash Commands ==========


@bot.tree.command(name="help", description="Show available commands")
async def help_cmd(interaction: discord.Interaction):
    """Display a help message with all available commands."""
    embed = discord.Embed(title="📘 Role Ping Counter — Help",
                          color=discord.Color.blurple())
    embed.description = (
        "/rolecounts @Role — Show top users who pinged that role.\n"
        "/leaderboard @Role — Show leaderboard for a role (or all roles if none specified).\n"
        "/mycounts — Show your personal role ping stats.\n"
        "/resetcounts @Role — Reset counts for that role (Admin only).\n"
        "/resetmycounts — Delete all your counts.\n"
        "/cleanup [days] — Remove old ping records (Admin only).\n")
    await interaction.response.send_message(embed=embed, ephemeral=True)


async def _show_role_counts(interaction: discord.Interaction,
                            role: discord.Role):
    """
    Helper function to display role ping statistics.
    
    Args:
        interaction: Discord interaction object
        role: The role to show statistics for
    """

    top_users = get_top_for_role(interaction.guild.id, role.id)
    if not top_users:
        await interaction.response.send_message(
            f"No data yet for {role.mention}.", ephemeral=True)
        return

    # Build the leaderboard
    lines = []
    for user_id, total in top_users:
        member = interaction.guild.get_member(int(user_id))
        name = member.display_name if member else f"<User {user_id}>"
        lines.append(f"**{total}x** — {name}")

    embed = discord.Embed(title=f"🏆 Top Role Pingers — {role.name}",
                          color=discord.Color.blurple())
    embed.description = "\n".join(lines)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="rolecounts",
                  description="Show top users who pinged a specific role")
@app_commands.describe(role="Select a role to view stats for")
async def rolecounts(interaction: discord.Interaction, role: discord.Role):
    """Display the top users who have pinged a specific role."""
    await _show_role_counts(interaction, role)


@bot.tree.command(name="leaderboard", description="Show role ping leaderboard")
@app_commands.describe(
    role=
    "Select a role to view stats for (optional - shows all roles if not specified)"
)
async def leaderboard(interaction: discord.Interaction,
                      role: discord.Role | None = None):
    """
    Display role ping leaderboard.
    If no role is specified, shows overall server leaderboard with top roles.
    """
    if role is None:
        # Show server-wide leaderboard with all roles
        rows = read_all_pings()
        guild_rows = [
            r for r in rows if r["guild_id"] == str(interaction.guild.id)
        ]

        if not guild_rows:
            await interaction.response.send_message(
                "No data found for this server yet.", ephemeral=True)
            return

        # Group pings by role
        grouped = defaultdict(Counter)
        for r in guild_rows:
            grouped[r["role_id"]][r["user_id"]] += 1

        # Sort roles by total ping count
        sorted_roles = sorted(grouped.items(),
                              key=lambda x: sum(x[1].values()),
                              reverse=True)

        # Build embed with top roles
        embed = discord.Embed(title="🌍 Server Leaderboard — All Roles",
                              color=discord.Color.gold(),
                              description="")

        max_roles = 5  # Show top 5 roles
        for idx, (role_id, counter) in enumerate(sorted_roles[:max_roles],
                                                 start=1):
            role_obj = interaction.guild.get_role(int(role_id))
            if role_obj is None:
                continue  # Skip deleted roles

            total_pings = sum(counter.values())
            top_users = counter.most_common(3)

            # Format top users for this role
            user_lines = []
            for user_id, count in top_users:
                member = interaction.guild.get_member(int(user_id))
                name = member.display_name if member else f"<User {user_id}>"
                user_lines.append(f"• **{count}x**: *{name}*")

            embed.add_field(
                name=f"{idx}. {role_obj.name} — {total_pings} total pings",
                value="\n".join(user_lines),
                inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        # Show leaderboard for specific role
        await _show_role_counts(interaction, role)


@bot.tree.command(name="mycounts", description="Show your personal ping stats")
async def mycounts(interaction: discord.Interaction):
    """Display the user's personal role ping statistics."""
    counts = get_counts_for_user(interaction.guild.id, interaction.user.id)

    if not counts:
        await interaction.response.send_message(
            "You haven't pinged any roles yet.", ephemeral=True)
        return

    # Build statistics list
    lines = []
    for role_id, total in counts:
        role = interaction.guild.get_role(int(role_id))
        rname = role.name if role else f"<Deleted Role {role_id}>"
        lines.append(f"**{total}x** — {rname}")

    embed = discord.Embed(
        title=f"📊 Your Ping Stats — {interaction.user.display_name}",
        color=discord.Color.green())
    embed.description = "\n".join(lines)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@app_commands.checks.has_permissions(manage_guild=True)
@bot.tree.command(name="resetcounts",
                  description="Reset all counts for a role (Admin only)")
@app_commands.describe(role="Select a role to reset counts for")
@app_commands.checks.has_permissions(administrator=True)
async def resetcounts(interaction: discord.Interaction, role: discord.Role):
    """Reset all ping counts for a specific role. Requires administrator permission."""
    reset_role_counts(interaction.guild.id, role.id)
    await interaction.response.send_message(
        f"✅ Counts for {role.mention} have been reset.", ephemeral=True)


@bot.tree.command(name="resetmycounts",
                  description="Reset your personal counts")
async def resetmycounts(interaction: discord.Interaction):
    """Reset the user's personal ping counts."""
    reset_user_counts(interaction.guild.id, interaction.user.id)
    await interaction.response.send_message("✅ Your counts have been reset.",
                                            ephemeral=True)


@app_commands.checks.has_permissions(manage_guild=True)
@bot.tree.command(name="cleanup",
                  description="Clean up old ping records (Admin only)")
@app_commands.describe(
    days="Delete entries older than this many days (default: 30)")
@app_commands.checks.has_permissions(manage_guild=True)
async def cleanup(interaction: discord.Interaction, days: int | None = None):
    """
    Manually trigger cleanup of old ping records.
    Requires manage_guild permission.
    """
    days = days or CLEANUP_DAYS
    cleanup_old_entries(days)
    await interaction.response.send_message(
        f"🧹 Cleaned CSV, removed entries older than {days} days.",
        ephemeral=True)


@bot.event
async def on_reaction_add(reaction: discord.Reaction, user: discord.User):
    if user.bot:
        return

    print(f"[SpoilerTracker] Reaction added: {reaction.emoji} by {user}")
    message = reaction.message
    guild = message.guild
    if guild is None:
        return

    # Spoiler detection
    is_spoiler = any(
        att.filename.startswith("SPOILER_") for att in message.attachments)
    if "||" in message.content:
        is_spoiler = True

    if not is_spoiler:
        return

    # Log entry in JSON
    record_reaction(guild_id=guild.id,
                    message_id=message.id,
                    user_id=user.id,
                    emoji=str(reaction.emoji))

    print(f"[SpoilerTracker] {user} reacted with {reaction.emoji} "
          f"to spoiler message {message.id} in {guild.name}")


# ========== ping_timeline Commands ==========


@app_commands.checks.has_permissions(manage_guild=True)
@bot.tree.command(
    name="timeline",
    description="Zeigt einen Zeitverlaufsgraphen der Role-Pings.")
@app_commands.describe(
    role="Optional: Zeigt nur die Timeline für diese Rolle.")
async def timeline(interaction: discord.Interaction,
                   role: discord.Role | None = None):
    await interaction.response.defer()
    print(f"Generating timeline for {role.name if role else 'all roles'}...")

    guild_id = interaction.guild.id
    csv_file = "role_pings.csv"

    if not os.path.exists(csv_file):
        return await interaction.followup.send(
            "Noch keine Ping-Daten vorhanden.")

    # --- CSV einlesen ---
    timestamps = defaultdict(int)
    role_id_filter = str(role.id) if role else None

    with open(csv_file, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        #print(f"Reading CSV {reader}...")
        for row in reader:
            # nur dieses Guild
            #print(f"Reading row {row}...")
            if str(row["guild_id"]) != str(guild_id):
                continue

            # Optional Rolle filtern
            if role_id_filter and row["role_id"] != role_id_filter:
                continue

            ts = datetime.fromisoformat(row["timestamp"])
            # Handle naive timestamps (old data) by assuming UTC
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            day = ts.date()
            timestamps[day] += 1
            #print(f"loop timestamps {timestamps}...")

    if not timestamps:
        return await interaction.followup.send(
            "Keine passenden Ping-Daten gefunden.")

    # --- Daten nach Datum sortieren ---
    days = sorted(timestamps.keys())
    counts = [timestamps[d] for d in days]

    # --- Graph erstellen ---
    plt.figure(figsize=(10, 4))
    plt.plot(days, counts, marker="o")
    plt.xlabel("Datum")
    plt.ylabel("Anzahl der Roll-Pings")
    plt.title(f"Ping-Verlauf{' für ' + role.name if role else ''}")
    plt.grid(True)
    plt.tight_layout()

    # Bild in Bytes speichern
    buffer = io.BytesIO()
    plt.savefig(buffer, format="png")
    buffer.seek(0)
    plt.close()

    # --- Graph senden ---
    try:
        file = File(buffer, filename="ping_timeline.png")
        await interaction.followup.send(file=file)
    except Exception as e:
        await interaction.followup.send(f"Fehler beim Senden des Graphen: {e}")


# ========== Reaction Commands ==========


@app_commands.checks.has_permissions(manage_guild=True)
@bot.tree.command(name="reactionstats",
                  description="Zeigt Reaction-Leaderboard")
async def reactionstats(interaction: discord.Interaction):
    print(f"Generating reaction stats for {interaction.guild.name}...")
    guild_id = str(interaction.guild.id)

    stats = load_reaction_stats(guild_id)
    reactions = stats["reactions"]

    if not reactions:
        return await interaction.response.send_message(
            "Keine Reaktionen gespeichert.", ephemeral=True)

    # Counts total - User Ranking
    counter = Counter()
    for r in reactions:
        counter[r["user_id"]] += 1

    top10 = counter.most_common(10)

    embed = discord.Embed(title="📸 Spoiler Reaction Leaderboard (Top 10)",
                          color=discord.Color.purple())

    # ===== Top 10 User =====
    lines = []
    for user_id, count in top10:
        member = interaction.guild.get_member(int(user_id))
        name = member.display_name if member else f"<User {user_id}>"
        lines.append(f"**{count}x** — {name}")

    embed.description = "\n".join(lines)

    # ===== ACCUMULATED ROLE RANKING =====
    config = load_reaction_config(guild_id)
    rank_roles = config.get("rank_roles", [])

    if rank_roles:
        # Lua Style Divider
        embed.add_field(name="— — — — —", value=" ", inline=False)

        # (1) Count reactions per user
        user_reaction_count = Counter()
        for r in reactions:
            user_reaction_count[r["user_id"]] += 1

        # (2) Prepare role totals
        role_totals = {rid: 0 for rid in rank_roles}

        # (3) Add reactions per user to all roles they have
        for user_id, count in user_reaction_count.items():
            member = interaction.guild.get_member(int(user_id))
            if not member:
                continue

            for rid in rank_roles:
                role = interaction.guild.get_role(int(rid))
                if role and role in member.roles:
                    role_totals[rid] += count

        # (4) Sort roles by total reactions
        sorted_roles = sorted(role_totals.items(),
                              key=lambda x: x[1],
                              reverse=True)

        # (5) Show accumulated ranking
        for rid, total in sorted_roles:
            role = interaction.guild.get_role(int(rid))
            if role is None:
                continue

            embed.add_field(name=f"🎭 {role.name}",
                            value=f"**{total} Reaktionen** insgesamt",
                            inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="reaction_set_roles",
                  description="Setze Ranking-Rollen.")
@app_commands.checks.has_permissions(administrator=True)
async def reaction_set_roles(interaction: discord.Interaction,
                             role1: discord.Role,
                             role2: discord.Role | None = None,
                             role3: discord.Role | None = None,
                             role4: discord.Role | None = None,
                             role5: discord.Role | None = None):
    guild_id = str(interaction.guild.id)

    roles = [r for r in [role1, role2, role3, role4, role5] if r is not None]

    config_path = f"data/reactions/configs/{guild_id}.json"
    os.makedirs(os.path.dirname(config_path), exist_ok=True)

    try:
        config = json.load(open(config_path))
    except Exception as e:
        print(f"Fehler beim Laden der Konfiguration: {e}")
        config = {}

    config["rank_roles"] = [str(r.id) for r in roles]

    with open(config_path, "w") as f:
        json.dump(config, f, indent=4)

    return await interaction.response.send_message(
        "Gespeicherte Ranking-Rollen:\n" +
        "\n".join([f"• {r.mention}" for r in roles]),
        ephemeral=True)


@bot.tree.command(name="reaction_reset",
                  description="Löscht alle Reaction-Daten.")
@app_commands.checks.has_permissions(administrator=True)
async def reaction_reset(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    path = reaction_stats_path(guild_id)

    if os.path.exists(path):
        os.remove(path)

    await interaction.response.send_message(
        "🗑 Alle Reaction-Daten wurden gelöscht.", ephemeral=True)


@bot.tree.command(name="reaction_cleanup",
                  description="Alter Reaction-Einträge löschen")
@app_commands.describe(days="Anzahl Tage (Standard: 30)")
@app_commands.checks.has_permissions(administrator=True)
async def reaction_cleanup(interaction: discord.Interaction, days: int = 30):
    guild_id = str(interaction.guild.id)
    stats = load_reaction_stats(guild_id)

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    before = len(stats["reactions"])

    def parse_timestamp_aware(ts_str):
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts

    stats["reactions"] = [
        r for r in stats["reactions"]
        if parse_timestamp_aware(r["timestamp"]) >= cutoff
    ]
    after = len(stats["reactions"])

    save_reaction_stats(guild_id, stats)

    await interaction.response.send_message(
        f"🧹 {before-after} Einträge gelöscht, {after} verbleiben.",
        ephemeral=True)


@bot.tree.command(name="privacy",
                  description="Information about data collection and privacy")
async def privacy(interaction: discord.Interaction):
    await interaction.response.send_message((
        "🔒 **Privacy & Data Usage**\n\n"
        "This bot collects **server activity metadata** for moderation and analytics purposes.\n\n"
        "**What is collected:**\n"
        "• User IDs\n"
        "• Channel IDs\n"
        "• Role mentions (pingable roles only)\n"
        "• Timestamps\n\n"
        "**What is NOT collected:**\n"
        "• Message content\n"
        "• Private messages (DMs)\n"
        "• Attachments\n\n"
        "Data is automatically cleaned after a configurable retention period (default: 30 days)."
    ),
                                            ephemeral=True)


@bot.tree.command(name="activity_overview",
                  description="Shows general server activity (admin only)")
@app_commands.checks.has_permissions(manage_guild=True)
async def activity_overview(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    now = datetime.now(timezone.utc)

    # Read the CSV data for messages and role pings
    message_rows = []
    role_ping_rows = []

    # Read the message activity log
    try:
        with open("activity_messages.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            message_rows = [
                row for row in reader if row["guild_id"] == guild_id
            ]
    except FileNotFoundError:
        pass  # No data yet, that's fine.

    # Read the role ping activity log
    try:
        with open("role_pings.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            role_ping_rows = [
                row for row in reader if row["guild_id"] == guild_id
            ]
    except FileNotFoundError:
        pass  # No data yet, that's fine.

    # Calculate total messages in the last 7 and 30 days
    def count_messages_in_period(rows, days):
        cutoff = now - timedelta(days=days)
        return sum(1 for row in rows if parse_ts(row["timestamp"]) >= cutoff)

    total_messages_7d = count_messages_in_period(message_rows, 7)
    total_messages_30d = count_messages_in_period(message_rows, 30)

    # Calculate total role pings in the last 7 and 30 days
    total_role_pings_7d = count_messages_in_period(role_ping_rows, 7)
    total_role_pings_30d = count_messages_in_period(role_ping_rows, 30)

    # Find the most active channel
    channel_counter = Counter(row["channel_id"] for row in message_rows)
    most_active_channel = channel_counter.most_common(1)

    # Find the most active user
    user_counter = Counter(row["user_id"] for row in message_rows)
    most_active_user = user_counter.most_common(1)

    # Calculate peak hours (last 7 days)
    hour_counter = Counter(
        parse_ts(row["timestamp"]).hour for row in message_rows
        if parse_ts(row["timestamp"]) >= now - timedelta(days=7))
    peak_hour = hour_counter.most_common(1)

    # Prepare the embed response
    embed = discord.Embed(title="📊 Server Activity Overview",
                          color=discord.Color.blue())

    embed.add_field(
        name="📅 Total Messages",
        value=
        f"Last 7 days: **{total_messages_7d}**\nLast 30 days: **{total_messages_30d}**",
        inline=False)
    embed.add_field(
        name="🔔 Total Role Pings",
        value=
        f"Last 7 days: **{total_role_pings_7d}**\nLast 30 days: **{total_role_pings_30d}**",
        inline=False)

    if most_active_channel:
        channel_id = most_active_channel[0][0]
        channel = interaction.guild.get_channel(int(channel_id))
        embed.add_field(
            name="📈 Most Active Channel",
            value=
            f"**#{channel.name}** with **{most_active_channel[0][1]}** messages",
            inline=False)

    if most_active_user:
        user_id = most_active_user[0][0]
        user = interaction.guild.get_member(int(user_id))
        embed.add_field(
            name="🏆 Most Active User",
            value=
            f"**{user.display_name if user else 'Unknown User'}** with **{most_active_user[0][1]}** messages",
            inline=False)

    if peak_hour:
        embed.add_field(
            name="⏰ Peak Hour",
            value=
            f"**{peak_hour[0][0]}:00** with **{peak_hour[0][1]}** messages",
            inline=False)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="activity_hours",
                  description="Show message activity per hour (admin only)")
@app_commands.describe(days="How many days to analyze (default: 7)")
@app_commands.checks.has_permissions(manage_guild=True)
async def activity_hours(interaction: discord.Interaction, days: int = 7):
    await interaction.response.defer(ephemeral=True)

    guild_id = str(interaction.guild.id)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    rows = []

    # Read CSV safely
    try:
        with open("activity_messages.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("guild_id") == guild_id:
                    rows.append(row)
    except FileNotFoundError:
        pass

    if not rows:
        await interaction.followup.send("ℹ No activity data available.",
                                        ephemeral=True)
        return

    # Count per hour
    hour_counter = Counter()

    for row in rows:
        ts = parse_ts(row["timestamp"])
        if ts >= cutoff:
            hour_counter[ts.hour] += 1

    if not hour_counter:
        await interaction.followup.send(
            f"ℹ No activity in the last {days} days.", ephemeral=True)
        return

    # Build output
    lines = []
    for hour in range(24):
        count = hour_counter.get(hour, 0)
        bar = "█" * min(count // max(1, max(hour_counter.values()) // 10), 10)
        lines.append(f"`{hour:02d}:00` | {count:5d} {bar}")

    description = "\n".join(lines)

    embed = discord.Embed(title="🕒 Activity by Hour (UTC)",
                          description=description,
                          color=discord.Color.green())
    embed.set_footer(text=f"Last {days} days")

    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="activity_channels",
                  description="Show most active channels (admin only)")
@app_commands.describe(days="How many days to analyze (default: 7)",
                       limit="How many channels to show (default: 10)")
@app_commands.checks.has_permissions(manage_guild=True)
async def activity_channels(interaction: discord.Interaction,
                            days: int = 7,
                            limit: int = 10):
    await interaction.response.defer(ephemeral=True)

    guild_id = str(interaction.guild.id)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    rows = []

    # Read CSV
    try:
        with open("activity_messages.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("guild_id") == guild_id:
                    rows.append(row)
    except FileNotFoundError:
        pass

    if not rows:
        await interaction.followup.send("ℹ No activity data available.",
                                        ephemeral=True)
        return

    # Count messages per channel
    channel_counter = Counter()

    for row in rows:
        ts = parse_ts(row["timestamp"])
        if ts >= cutoff:
            channel_counter[row["channel_id"]] += 1

    if not channel_counter:
        await interaction.followup.send(
            f"ℹ No activity in the last {days} days.", ephemeral=True)
        return

    # Build output
    lines = []
    for channel_id, count in channel_counter.most_common(limit):
        channel = interaction.guild.get_channel(int(channel_id))
        name = f"#{channel.name}" if channel else "*deleted-channel*"
        lines.append(f"{name:<25} — **{count}** messages")

    embed = discord.Embed(title="📊 Most Active Channels",
                          description="\n".join(lines),
                          color=discord.Color.blurple())
    embed.set_footer(text=f"Last {days} days • Top {limit} channels")

    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="activity_channel_heatmap",
                  description="Show activity heatmap per channel (admin only)")
@app_commands.describe(days="How many days to analyze (default: 7)")
@app_commands.checks.has_permissions(manage_guild=True)
async def activity_channel_heatmap(interaction: discord.Interaction,
                                   days: int = 7):
    await interaction.response.defer(ephemeral=True)

    guild_id = str(interaction.guild.id)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    rows: list[dict] = []

    # -----------------------------
    # Read CSV
    # -----------------------------
    try:
        with open("activity_messages.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("guild_id") == guild_id:
                    rows.append(row)
    except FileNotFoundError:
        await interaction.followup.send("ℹ No activity data available.",
                                        ephemeral=True)
        return

    if not rows:
        await interaction.followup.send("ℹ No activity data available.",
                                        ephemeral=True)
        return

    # -----------------------------
    # Prepare activity container
    # -----------------------------
    channel_activity: dict[str, list[int]] = {
        str(channel.id): [0] * 24
        for channel in interaction.guild.text_channels
    }

    # -----------------------------
    # Count messages
    # -----------------------------
    for row in rows:
        try:
            ts = parse_ts(row["timestamp"])  # MUST return UTC-aware datetime
        except Exception:
            continue

        if ts < cutoff:
            continue

        channel_id = row.get("channel_id")
        if channel_id not in channel_activity:
            continue

        channel_activity[channel_id][ts.hour] += 1

    # -----------------------------
    # Rank channels by activity
    # -----------------------------
    channel_totals = {
        cid: sum(hours)
        for cid, hours in channel_activity.items() if sum(hours) > 0
    }

    if not channel_totals:
        await interaction.followup.send(
            "ℹ No activity found for the selected time period.",
            ephemeral=True)
        return

    top_channels = sorted(channel_totals.items(),
                          key=lambda x: x[1],
                          reverse=True)[:15]  # HARD LIMIT (embed-safe)

    # -----------------------------
    # Build heatmap
    # -----------------------------
    lines: list[str] = []

    for channel_id, _total in top_channels:
        channel = interaction.guild.get_channel(int(channel_id))
        if not channel:
            continue

        activity = channel_activity[channel_id]
        max_activity = max(activity)

        if max_activity == 0:
            continue

        heatmap = ""
        for count in activity:
            ratio = count / max_activity
            if ratio == 0:
                heatmap += "░"
            elif ratio < 0.33:
                heatmap += "▒"
            elif ratio < 0.66:
                heatmap += "▓"
            else:
                heatmap += "█"

        lines.append(f"**#{channel.name}**\n`{heatmap}`")

    if not lines:
        await interaction.followup.send(
            "ℹ No activity found for the selected time period.",
            ephemeral=True)
        return

    # -----------------------------
    # Send embed
    # -----------------------------
    embed = discord.Embed(title="📊 Channel Activity Heatmap",
                          description="\n\n".join(lines),
                          color=discord.Color.blurple())

    embed.add_field(name="Legend",
                    value=("░ none · ▒ low · ▓ medium · █ high\n"
                           "Left → right = 00:00 → 23:00 (UTC)"),
                    inline=False)

    embed.set_footer(
        text=f"Last {days} days • Top {len(lines)} active channels")

    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="activity_user",
                  description="Show most active users (admin only)")
@app_commands.describe(days="How many days to analyze (default: 7)")
@app_commands.checks.has_permissions(manage_guild=True)
async def activity_user(interaction: discord.Interaction, days: int = 7):
    await interaction.response.defer(ephemeral=True)

    guild_id = str(interaction.guild.id)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    user_counter = Counter()

    # Read CSV
    try:
        with open("activity_messages.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("guild_id") != guild_id:
                    continue

                ts = parse_ts(row["timestamp"])
                if ts >= cutoff:
                    user_counter[row["user_id"]] += 1

    except FileNotFoundError:
        pass

    if not user_counter:
        await interaction.followup.send("ℹ No activity data available.",
                                        ephemeral=True)
        return

    # Top 15 users (safe for embeds)
    top_users = user_counter.most_common(15)

    lines = []
    for user_id, count in top_users:
        member = interaction.guild.get_member(int(user_id))
        name = member.display_name if member else f"User {user_id}"
        lines.append(f"**{name}** — `{count}` messages")

    embed = discord.Embed(title="👤 User Activity",
                          description="\n".join(lines),
                          color=discord.Color.blurple())

    embed.set_footer(text=f"Last {days} days • Top {len(lines)} users")

    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="activity_user_distribution",
                  description="Show activity distribution (admin only)")
@app_commands.describe(days="How many days to analyze (default: 30)")
@app_commands.checks.has_permissions(manage_guild=True)
async def activity_user_distribution(interaction: discord.Interaction,
                                     days: int = 30):
    await interaction.response.defer(ephemeral=True)

    guild_id = str(interaction.guild.id)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    user_counter = Counter()
    total_messages = 0

    # Read CSV
    try:
        with open("activity_messages.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("guild_id") != guild_id:
                    continue

                ts = parse_ts(row["timestamp"])
                if ts >= cutoff:
                    user_counter[row["user_id"]] += 1
                    total_messages += 1
    except FileNotFoundError:
        pass

    if not user_counter:
        await interaction.followup.send("ℹ No activity data available.",
                                        ephemeral=True)
        return

    user_counts = sorted(user_counter.values(), reverse=True)
    total_users = len(user_counts)

    def pct(n: float) -> str:
        return f"{n:.1f}%"

    def share(top_percent: float) -> float:
        cutoff_index = max(1, int(total_users * top_percent))
        return sum(user_counts[:cutoff_index]) / total_messages * 100

    top_10 = share(0.10)
    top_25 = share(0.25)
    top_50 = share(0.50)

    embed = discord.Embed(title="📊 User Activity Distribution",
                          color=discord.Color.blurple())

    embed.add_field(name="Users",
                    value=(f"Total active users: **{total_users}**\n"
                           f"Total messages: **{total_messages}**"),
                    inline=False)

    embed.add_field(name="Message Share",
                    value=(f"Top 10% → **{pct(top_10)}**\n"
                           f"Top 25% → **{pct(top_25)}**\n"
                           f"Top 50% → **{pct(top_50)}**"),
                    inline=False)

    embed.set_footer(text=f"Last {days} days")

    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(
    name="activity_user_role",
    description="Show activity for users with a specific role (admin only)")
@app_commands.describe(role="Role to analyze",
                       days="How many days to analyze (default: 30)")
@app_commands.checks.has_permissions(manage_guild=True)
async def activity_user_role(interaction: discord.Interaction,
                             role: discord.Role,
                             days: int = 30):
    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild
    guild_id = str(guild.id)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    # Users that currently have the role
    role_member_ids = {str(m.id) for m in role.members}
    if not role_member_ids:
        await interaction.followup.send(
            f"ℹ No members currently have the role **{role.name}**.",
            ephemeral=True)
        return

    user_counter = Counter()

    # Read CSV
    try:
        with open("activity_messages.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("guild_id") != guild_id:
                    continue

                if row["user_id"] not in role_member_ids:
                    continue

                ts = parse_ts(row["timestamp"])
                if ts >= cutoff:
                    user_counter[row["user_id"]] += 1
    except FileNotFoundError:
        pass

    if not user_counter:
        await interaction.followup.send(
            "ℹ No activity recorded for this role.", ephemeral=True)
        return

    # Top 15 users
    top_users = user_counter.most_common(15)

    lines = []
    for user_id, count in top_users:
        member = guild.get_member(int(user_id))
        name = member.display_name if member else f"User {user_id}"
        lines.append(f"**{name}** — `{count}` messages")

    embed = discord.Embed(
        title=f"👥 Role Activity — {role.name}",
        description="\n".join(lines),
        color=role.color if role.color.value else discord.Color.blurple())

    embed.set_footer(
        text=f"Last {days} days • {len(role_member_ids)} members in role")

    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="activity_inactive",
                  description="Show inactive users (admin only)")
@app_commands.describe(days="Users inactive for this many days (default: 30)")
@app_commands.checks.has_permissions(manage_guild=True)
async def activity_inactive(interaction: discord.Interaction, days: int = 30):
    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild
    guild_id = str(guild.id)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    # Track last activity per user
    last_seen: dict[str, datetime] = {}

    # Read CSV
    try:
        with open("activity_messages.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("guild_id") != guild_id:
                    continue

                ts = parse_ts(row["timestamp"])
                user_id = row["user_id"]

                if user_id not in last_seen or ts > last_seen[user_id]:
                    last_seen[user_id] = ts
    except FileNotFoundError:
        pass

    inactive_users = []

    for member in guild.members:
        if member.bot:
            continue

        uid = str(member.id)
        last = last_seen.get(uid)

        if last is None or last < cutoff:
            inactive_users.append((member, last))

    if not inactive_users:
        await interaction.followup.send("ℹ No inactive users found.",
                                        ephemeral=True)
        return

    # Sort by longest inactivity first
    inactive_users.sort(
        key=lambda x: x[1] or datetime.min.replace(tzinfo=timezone.utc))

    lines = []
    for member, last in inactive_users[:15]:
        if last:
            days_ago = (now - last).days
            last_text = f"{days_ago} days ago"
        else:
            last_text = "never"

        lines.append(f"**{member.display_name}** — last active: `{last_text}`")

    embed = discord.Embed(title="😴 Inactive Users",
                          description="\n".join(lines),
                          color=discord.Color.orange())

    embed.set_footer(
        text=f"Inactive for ≥ {days} days • Showing top {len(lines)}")

    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(
    name="activity_user_ping_ratio",
    description="Show ping vs message ratio per user (admin only)")
@app_commands.describe(days="How many days to analyze (default: 30)")
@app_commands.checks.has_permissions(manage_guild=True)
async def activity_user_ping_ratio(interaction: discord.Interaction,
                                   days: int = 30):
    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild
    guild_id = str(guild.id)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    message_counter = Counter()
    ping_counter = Counter()

    # Read message activity
    try:
        with open("activity_messages.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("guild_id") != guild_id:
                    continue

                ts = parse_ts(row["timestamp"])
                if ts >= cutoff:
                    message_counter[row["user_id"]] += 1
    except FileNotFoundError:
        pass

    # Read role ping activity
    try:
        with open("role_pings.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("guild_id") != guild_id:
                    continue

                ts = parse_ts(row["timestamp"])
                if ts >= cutoff:
                    ping_counter[row["user_id"]] += 1
    except FileNotFoundError:
        pass

    users = set(message_counter) | set(ping_counter)

    if not users:
        await interaction.followup.send("ℹ No activity data available.",
                                        ephemeral=True)
        return

    rows = []
    for uid in users:
        msgs = message_counter.get(uid, 0)
        pings = ping_counter.get(uid, 0)
        total = msgs + pings
        if total == 0:
            continue

        ratio = pings / total
        rows.append((uid, msgs, pings, ratio))

    # Sort by highest ping ratio first
    rows.sort(key=lambda x: x[3], reverse=True)

    lines = []
    for uid, msgs, pings, ratio in rows[:15]:
        member = guild.get_member(int(uid))
        name = member.display_name if member else f"User {uid}"

        lines.append(f"**{name}** — "
                     f"💬 `{msgs}` | 🔔 `{pings}` | "
                     f"ratio `{ratio:.0%}`")

    embed = discord.Embed(title="🔔 Ping vs Message Ratio",
                          description="\n".join(lines),
                          color=discord.Color.red())

    embed.add_field(name="Interpretation",
                    value=("• `0–20%` healthy\n"
                           "• `20–50%` watch\n"
                           "• `>50%` potential abuse"),
                    inline=False)

    embed.set_footer(text=f"Last {days} days • Top {len(lines)} users")

    await interaction.followup.send(embed=embed, ephemeral=True)


# ========== Run the Bot ==========

if __name__ == "__main__":
    ensure_csv_exists()
    bot.run(TOKEN)
