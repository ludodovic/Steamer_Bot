import json
import locale
import asyncio
import discord
from rapidfuzz import fuzz
from pymongo import MongoClient
from discord.ext import commands
from datetime import datetime, timedelta
from Classes import GestionnaireReservations as GR

locale.setlocale(locale.LC_ALL, 'fr_FR.UTF-8')

def get_date_in_french_format(date):
    return date.strftime("%d %b - %H:%M")

def connect_to_mongodb_db(connexion_string):
    db = None
    try:
        client = MongoClient(connexion_string)
        db = client["SCTV"]
        print("Connected to MongoDB")
    except Exception as e:
        print(f"Error connecting to MongoDB: {e}")
    
    return db


config_file = "./config.json"

config_data = {}
with open(config_file, "r", encoding="utf-8") as f:
    config_data = json.load(f)


my_database = connect_to_mongodb_db(config_data["db_connString"])
gestionnaire_resa = GR.GestionnaireReservations(my_database)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True
client = commands.Bot(command_prefix='/', intents = intents)

with open("./master_message_template.json", "r", encoding="utf-8") as f:
    master_message_template = json.load(f)
    client.master_message_embed_list = []
    for emb in master_message_template["embeds"]:
        embed = discord.Embed.from_dict(emb)
        client.master_message_embed_list.append(embed)
    
client.master_message = None
client.initialized = False
client.master_channel = None


def get_content_for_master_message():
    table_string = gestionnaire_resa.get_table_string()
    return str(f"Voici la liste des réservations au {get_date_in_french_format(datetime.now())}:\n```\n{table_string}\n```")

async def update_master_message():
    await client.master_message.edit(content=get_content_for_master_message(), embeds = client.master_message_embed_list)

async def update_users_about_reservations(deleted_reservation = None):
    print("updating users about reservations...")
    expired_info = gestionnaire_resa.purge_expired_reservations(deleted_reservation = deleted_reservation)
    for info in expired_info["to_notify"]:
        user_id = int(info["user_id"])
        zone = info["zone"]
        print(f"notifying user {user_id} about expired reservation for zone {zone}")
        await send_user_message(user_id, f"[SCTV] Ta réservation pour la zone '{zone}' a expiré. N'hésite pas à en réserver une nouvelle !")
    
    for info in expired_info["next_turn"]:
        if info is not None:
            user_id = int(info["user_id"])
            zone = info["zone"]
            print(f"notifying user {user_id} about expired reservation for zone {zone}")
            await send_user_message(user_id, f"[SCTV] C'est à ton tour ! La réservation pour la zone '{zone}' est maintenant active pour toi. Profites-en !")

async def send_user_message(user_id, content):
    try:
        user = client.get_user(user_id) 
        await user.send(content)
    except Exception as e:
        print(f"Error sending message to user : {e}")

@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')    

@client.command(pass_context=True)
async def initialize(context, channel_id: int = None):
    message = context.message
    if client.initialized:
        print("Bot already initialized.")
        await message.channel.send("Le bot a déjà été initialisé.", delete_after=20.0)
        return
    else:
        def is_me(m):
            return m.author == client.user
        await message.channel.purge(limit=10, check=is_me)
        if channel_id is not None:
            try:
                client.master_channel = client.get_channel(channel_id)  
            except Exception as e:
                print(f"Error accessing channel: {e}")
                await message.channel.send("Erreur lors de l'accès au canal spécifié. Assurez-vous que l'ID est correct et que le bot a accès à ce canal.", delete_after=20.0)
                return
        else:
            return
        client.master_message = await client.master_channel.send(content=get_content_for_master_message(), embeds = client.master_message_embed_list)
        client.initialized = True
    await update_users_about_reservations()

@client.command(pass_context=True)
async def resa(context):
    await update_users_about_reservations()
    message = context.message
    user_name = str(message.author.nick) if message.author.nick else str(message.author.global_name) if message.author.global_name else str(message.author.name)
    if message.author == client.user:
        return

    zone_query = message.content[6:50]
    matched_zone = gestionnaire_resa.fuzzy_match_zone_by_name(zone_query)
    if matched_zone == "":
        await client.master_channel.send(f"Désolé, je ne reconnais pas '{zone_query}' comme une zone existante ou réservable. Essaie avec une meilleure ortographe ou contacte un lead.", delete_after=20.0)
        return
    
    else:
        react = ["✅", "❌"]
        confirm_message = await client.master_channel.send(f"Réserver pour '{matched_zone}'? {message.author.mention}")
        for r in react:
            await confirm_message.add_reaction(r)
        
        def check(reaction, user):
            return user == message.author and str(reaction.emoji) in react
        try:
            reaction, user = await client.wait_for('reaction_add', timeout=10.0, check=check)
        except asyncio.TimeoutError:
            await confirm_message.delete()
            return
        
        else:
            if str(reaction.emoji) == "❌":
                await confirm_message.delete()
                return
            else: 
                if str(reaction.emoji) == "✅":
                    await confirm_message.delete()
                    user_id = str(message.author.id)
                    reservation = gestionnaire_resa.create_reservation(user_name, user_id, matched_zone)
                    exp_date, result = gestionnaire_resa.try_reservation(reservation)
                    if result == False:
                        await client.master_channel.send(f"[{user_name}] Désolé {message.author.mention}, tu as déjà 3 réservations actives ou la zone '{matched_zone}' a atteint sa capacité maximale de réservations.", delete_after=20.0)
                    else:
                        print(f"Reservation successful for user {user_name} in zone {matched_zone} until {exp_date}")
                        await client.master_channel.send(f"[{user_name}] Réservation confirmée pour la zone '{matched_zone}' ! Ta réservation expirera le {get_date_in_french_format(exp_date)}.", delete_after=20.0)
                        await update_master_message()

@client.command(pass_context=True)
async def clear(context):
    message = context.message
    user_name = str(message.author.nick) if message.author.nick else str(message.author.name)
    if message.author == client.user:
        return

    deleted_copy = None
    zone_query = message.content[6:50]
    matched_zone = gestionnaire_resa.fuzzy_match_zone_by_name(zone_query)
    if matched_zone == "":
        await client.master_channel.send(f"[{user_name}] Désolé, je ne reconnais pas '{zone_query}' comme une zone existante ou réservée.", delete_after=20.0)
        return

    else:
        react = ["✅", "❌"]
        confirm_message = await client.master_channel.send(f"Supprimer la réservation de '{matched_zone}'? {message.author.mention}")
        for r in react:
            await confirm_message.add_reaction(r)
        
        def check(reaction, user):
            return user == message.author and str(reaction.emoji) in react
        try:
            reaction, user = await client.wait_for('reaction_add', timeout=10.0, check=check)
        except asyncio.TimeoutError:
            await confirm_message.delete()
            return
        
        else:
            if str(reaction.emoji) == "❌":
                await confirm_message.delete()
                return
            else: 
                if str(reaction.emoji) == "✅":
                    await confirm_message.delete()
                    user_id = str(message.author.id)
                    result, deleted_copy = gestionnaire_resa.delete_reservation(user_id, matched_zone)
                    if result == False:
                        await client.master_channel.send(f"[{user_name}] Je n'ai pas trouvé de réservation active pour la zone '{matched_zone}' à ton nom. Pas besoin de t'inquiéter, rien n'a été supprimé.", delete_after=20.0)
                    else:
                        print(f"Reservation cleared for user {user_name} in zone {matched_zone}")
                        await client.master_channel.send(f"[{user_name}] Réservation terminée pour la zone '{matched_zone}' ! La place est libérée.", delete_after=20.0)
                        await update_master_message()
    await update_users_about_reservations(deleted_reservation = deleted_copy)

@client.command(pass_context=True)
async def update(context):
    message = context.message
    await update_master_message()
    await update_users_about_reservations()

@client.event
async def on_message(message):
    await client.process_commands(message)
    if client.initialized:
        if message.channel == client.master_channel:
            if message.author != client.user:
                await message.delete()


client.run(config_data["DISCORD_TOKEN"])