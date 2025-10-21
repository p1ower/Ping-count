#!/usr/bin/env python3
# role_ping_csvbot.py
# Discord.py v2.3+ — ohne SQL, nutzt CSV
# pip install -U discord.py

import discord
from discord import app_commands
from discord.ext import commands
import csv
import os
from datetime import datetime
from collections import Counter, defaultdict

TOKEN = os.environ['PING_COUNT_TOKEN']  # <-- hier Token eintragen
CSV_PATH = "role_pings.csv"

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ---------- CSV Handling ----------
def ensure_csv_exists():
    """Erstellt die CSV-Datei, falls sie fehlt."""
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
    """Fügt einen neuen Eintrag hinzu."""
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
    """Liest alle Einträge in eine Liste von Dicts."""
    ensure_csv_exists()
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def write_all_pings(rows):
    """Schreibt eine komplette Liste von Dicts zurück in die CSV."""
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f,
                                fieldnames=[
                                    "guild_id", "role_id", "user_id",
                                    "channel_id", "timestamp"
                                ])
        writer.writeheader()
        writer.writerows(rows)


# ---------- Datenabfragen ----------
def get_top_for_role(guild_id, role_id, limit=10):
    rows = read_all_pings()
    counts = Counter()
    for row in rows:
        if row["guild_id"] == str(guild_id) and row["role_id"] == str(role_id):
            counts[row["user_id"]] += 1
    return counts.most_common(limit)


def get_counts_for_user(guild_id, user_id):
    rows = read_all_pings()
    counts = Counter()
    for row in rows:
        if row["guild_id"] == str(guild_id) and row["user_id"] == str(user_id):
            counts[row["role_id"]] += 1
    return counts.most_common()


def reset_role_counts(guild_id, role_id):
    rows = read_all_pings()
    new_rows = [
        r for r in rows if not (
            r["guild_id"] == str(guild_id) and r["role_id"] == str(role_id))
    ]
    write_all_pings(new_rows)


def reset_user_counts(guild_id, user_id):
    rows = read_all_pings()
    new_rows = [
        r for r in rows if not (
            r["guild_id"] == str(guild_id) and r["user_id"] == str(user_id))
    ]
    write_all_pings(new_rows)


# ---------- Events ----------
@bot.event
async def on_ready():
    ensure_csv_exists()
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user} — Slash Commands synced.")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    for role in message.role_mentions:
        if not role.mentionable:
            continue  # Nur pingbare Rollen
        append_ping(guild_id=message.guild.id,
                    role_id=role.id,
                    user_id=message.author.id,
                    channel_id=message.channel.id)


# ---------- Slash Commands ----------
@bot.tree.command(name="help", description="Show available commands")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="📘 Role Ping Counter — Help",
                          color=discord.Color.blurple())
    embed.description = (
        "/rolecounts @Role — Show top users who pinged that role.\n"
        "/leaderboard @Role — Alias for /rolecounts.\n"
        "/mycounts — Show your personal role ping stats.\n"
        "/resetcounts @Role — Reset counts for that role (Admin only).\n"
        "/resetmycounts — Delete all your counts.\n")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="rolecounts",
                  description="Show top users who pinged a specific role")
@app_commands.describe(role="Select a role to view stats for")
async def rolecounts(interaction: discord.Interaction, role: discord.Role):
    top_users = get_top_for_role(interaction.guild.id, role.id)
    if not top_users:
        await interaction.response.send_message(
            f"No data yet for {role.mention}.", ephemeral=True)
        return

    lines = []
    for user_id, total in top_users:
        member = interaction.guild.get_member(int(user_id))
        name = member.display_name if member else f"<User {user_id}>"
        lines.append(f"**{total}x** — {name}")

    embed = discord.Embed(title=f"🏆 Top Role Pingers — {role.name}",
                          color=discord.Color.blurple())
    embed.description = "\n".join(lines)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="leaderboard", description="Alias for /rolecounts")
async def leaderboard(interaction: discord.Interaction, role: discord.Role):
    await rolecounts(interaction, role)


@bot.tree.command(name="mycounts", description="Show your personal ping stats")
async def mycounts(interaction: discord.Interaction):
    counts = get_counts_for_user(interaction.guild.id, interaction.user.id)
    if not counts:
        await interaction.response.send_message(
            "You haven't pinged any roles yet.", ephemeral=True)
        return

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
@app_commands.checks.has_permissions(manage_guild=True)
async def resetcounts(interaction: discord.Interaction, role: discord.Role):
    reset_role_counts(interaction.guild.id, role.id)
    await interaction.response.send_message(
        f"✅ Counts for {role.mention} have been reset.", ephemeral=True)


@bot.tree.command(name="resetmycounts",
                  description="Reset your personal counts")
async def resetmycounts(interaction: discord.Interaction):
    reset_user_counts(interaction.guild.id, interaction.user.id)
    await interaction.response.send_message("✅ Your counts have been reset.",
                                            ephemeral=True)


# ---------- Run ----------
if __name__ == "__main__":
    ensure_csv_exists()
    bot.run(TOKEN)
