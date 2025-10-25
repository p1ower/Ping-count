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
from datetime import datetime, timedelta
from collections import Counter, defaultdict

# Configuration
CLEANUP_DAYS = 30  # Remove entries older than this many days
TOKEN = os.environ['PING_COUNT_TOKEN']
CSV_PATH = "role_pings.csv"

# Configure bot intents (permissions for what the bot can see/do)
intents = discord.Intents.default()
intents.message_content = True  # Required to read message content
intents.guilds = True           # Required to access guild information
intents.members = True          # Required to get member information

# Daily cleanup task - runs every 24 hours
@tasks.loop(hours=24)
async def daily_cleanup():
    """Automatically clean up old entries every 24 hours."""
    cleanup_old_entries()

# Initialize the bot
bot = commands.Bot(command_prefix="!", intents=intents)


# ========== CSV File Management ==========

def ensure_csv_exists():
    """Create the CSV file with headers if it doesn't exist."""
    print("Ensuring CSV exists...")
    if not os.path.exists(CSV_PATH):
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
                datetime.utcnow().isoformat()
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
    """
    Remove entries older than the specified number of days from the CSV.
    
    Args:
        days: Remove entries older than this many days (default: CLEANUP_DAYS)
    """
    if not os.path.exists(CSV_PATH):
        return

    cutoff = datetime.utcnow() - timedelta(days=days)
    kept_rows = []
    removed = 0

    # Read and filter entries
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                ts = datetime.fromisoformat(row["timestamp"])
                if ts >= cutoff:
                    kept_rows.append(row)
                else:
                    removed += 1
            except Exception:
                # Skip rows with malformed timestamps
                continue

    # Write back the filtered entries
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f,
                                fieldnames=[
                                    "guild_id", "role_id", "user_id",
                                    "channel_id", "timestamp"
                                ])
        writer.writeheader()
        writer.writerows(kept_rows)

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
    cleanup_old_entries()  # Clean up old entries on startup
    daily_cleanup.start()  # Start the daily cleanup task
    await bot.tree.sync()  # Sync slash commands with Discord
    print(f"✅ Logged in as {bot.user} — Slash Commands synced.")


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
            continue
        
        # Record the ping
        append_ping(
            guild_id=message.guild.id,
            role_id=role.id,
            user_id=message.author.id,
            channel_id=message.channel.id
        )


# ========== Slash Commands ==========

@bot.tree.command(name="help", description="Show available commands")
async def help_cmd(interaction: discord.Interaction):
    """Display a help message with all available commands."""
    embed = discord.Embed(
        title="📘 Role Ping Counter — Help",
        color=discord.Color.blurple()
    )
    embed.description = (
        "/rolecounts @Role — Show top users who pinged that role.\n"
        "/leaderboard @Role — Show leaderboard for a role (or all roles if none specified).\n"
        "/mycounts — Show your personal role ping stats.\n"
        "/resetcounts @Role — Reset counts for that role (Admin only).\n"
        "/resetmycounts — Delete all your counts.\n"
        "/cleanup [days] — Remove old ping records (Admin only).\n"
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


async def _show_role_counts(interaction: discord.Interaction, role: discord.Role):
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

    embed = discord.Embed(
        title=f"🏆 Top Role Pingers — {role.name}",
        color=discord.Color.blurple()
    )
    embed.description = "\n".join(lines)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="rolecounts", description="Show top users who pinged a specific role")
@app_commands.describe(role="Select a role to view stats for")
async def rolecounts(interaction: discord.Interaction, role: discord.Role):
    """Display the top users who have pinged a specific role."""
    await _show_role_counts(interaction, role)


@bot.tree.command(name="leaderboard", description="Show role ping leaderboard")
@app_commands.describe(role="Select a role to view stats for (optional - shows all roles if not specified)")
async def leaderboard(interaction: discord.Interaction, role: discord.Role | None = None):
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
        sorted_roles = sorted(
            grouped.items(),
            key=lambda x: sum(x[1].values()),
            reverse=True
        )

        # Build embed with top roles
        embed = discord.Embed(
            title=f"🌍 Server Leaderboard — All Roles",
            color=discord.Color.gold(),
            description=""
        )

        max_roles = 5  # Show top 5 roles
        for idx, (role_id, counter) in enumerate(sorted_roles[:max_roles], start=1):
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
                inline=False
            )

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
        color=discord.Color.green()
    )
    embed.description = "\n".join(lines)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="resetcounts", description="Reset all counts for a role (Admin only)")
@app_commands.describe(role="Select a role to reset counts for")
@app_commands.checks.has_permissions(administrator=True)
async def resetcounts(interaction: discord.Interaction, role: discord.Role):
    """Reset all ping counts for a specific role. Requires administrator permission."""
    reset_role_counts(interaction.guild.id, role.id)
    await interaction.response.send_message(
        f"✅ Counts for {role.mention} have been reset.", ephemeral=True)


@bot.tree.command(name="resetmycounts", description="Reset your personal counts")
async def resetmycounts(interaction: discord.Interaction):
    """Reset the user's personal ping counts."""
    reset_user_counts(interaction.guild.id, interaction.user.id)
    await interaction.response.send_message(
        "✅ Your counts have been reset.", ephemeral=True)


@bot.tree.command(name="cleanup", description="Clean up old ping records (Admin only)")
@app_commands.describe(days="Delete entries older than this many days (default: 30)")
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


# ========== Run the Bot ==========

if __name__ == "__main__":
    ensure_csv_exists()
    bot.run(TOKEN)
