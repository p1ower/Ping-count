#!/usr/bin/env python3
"""
Discord Role Ping Counter Bot
Tracks when users mention/ping roles and provides statistics.
Uses CSV for data storage (no database required).
Discord.py v2.3+
"""

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
    await interaction.response.send_message(embed=embed)


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

        await interaction.response.send_message(embed=embed)
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


@bot.tree.command(
    name="timeline",
    description="Zeigt einen Zeitverlaufsgraphen der Role-Pings.")
@app_commands.describe(
    role="Optional: Zeigt nur die Timeline für diese Rolle.")
async def timeline(interaction: discord.Interaction,
                   role: discord.Role | None = None):
    await interaction.response.defer()

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


@bot.tree.command(name="reactionstats",
                  description="Zeigt Reaction-Leaderboard")
async def reactionstats(interaction: discord.Interaction):
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

    await interaction.response.send_message(embed=embed)


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
    stats["reactions"] = [
        r for r in stats["reactions"]
        if datetime.fromisoformat(r["timestamp"]) >= cutoff
    ]
    after = len(stats["reactions"])

    save_reaction_stats(guild_id, stats)

    await interaction.response.send_message(
        f"🧹 {before-after} Einträge gelöscht, {after} verbleiben.",
        ephemeral=True)


# ========== Run the Bot ==========

if __name__ == "__main__":
    ensure_csv_exists()
    bot.run(TOKEN)
