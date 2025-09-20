#!/usr/bin/env python3
import argparse
import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup

# Global sleep time (in seconds) used after each download attempt.
SLEEP_TIME = 0.5

# Base URLs for different providers
TWITCH_BASE_DOMAIN = "https://twitchemotes.com"
BTTV_BASE_API = "https://api.betterttv.net/3"
SEVENTV_BASE_API = "https://7tv.io/v3"
FFZ_BASE_API = "https://api.frankerfacez.com/v1"

# BTTV zero-width emotes (based on the emotes-api-dev implementation)
BTTV_ZERO_WIDTH = [
    "SoSnowy", "IceCold", "SantaHat", "TopHat",
    "ReinDeer", "CandyCane", "cvMask", "cvHazmat"
]

# Base path for all emotes
EMOTES_BASE_DIR = "emotes"

# Manual FFZ emotes
MANUAL_FFZ_EMOTES = [
    "https://www.frankerfacez.com/emoticon/587063-LULE",
    "https://www.frankerfacez.com/emoticon/532634-LULWIGuess",
    "https://www.frankerfacez.com/emoticon/381875-KEKW",
    "https://www.frankerfacez.com/emoticon/454560-forsenGa",
    
]

# Manual 7TV emotes
MANUAL_7TV_EMOTES = [
    "https://7tv.app/emotes/6446d232649f94e97473d7e3",
    "https://7tv.app/emotes/01F7H836GR000EMPHK5YSK0K1F",
    "https://7tv.app/emotes/60bd0ebfea5a332fb3304c2f"
]

# Manual BTTV emotes
MANUAL_BTTV_EMOTES = [
]

def valid_emote_name(name):
    # Only allow names with letters, numbers, or underscores.
    return re.match(r'^[A-Za-z0-9_]+$', name) is not None

def extract_emote_name(img_tag):
    tooltip = img_tag.get("data-tooltip", "")
    name = re.sub(r"<[^>]+>", "", tooltip).strip()
    if not name:
        name = img_tag.get("alt", "").strip()
    return name

def save_emote_image(image_url, filepath, emote_name):
    """Downloads and saves an emote image."""
    if os.path.exists(filepath):
        print(f"File {filepath} already exists, skipping download.")
        return True
    
    try:
        img_resp = requests.get(image_url, timeout=2)
        if img_resp.status_code != 200:
            print(f"Failed to download image for {emote_name} from {image_url}")
            time.sleep(SLEEP_TIME)
            return False
    except Exception as e:
        print(f"Error downloading image for {emote_name}: {e}")
        time.sleep(SLEEP_TIME)
        return False

    with open(filepath, "wb") as f:
        f.write(img_resp.content)
    print(f"Downloaded '{emote_name}' to {filepath}")
    time.sleep(SLEEP_TIME)
    return True

# Twitch emote scraping functions
def scrape_twitch_emotes(url_path, folder, subscriber=False):
    """
    Scrapes Twitch emote links from TWITCH_BASE_DOMAIN + url_path.
    Downloads images based on mode:
      - Global: constructs the large version URL (.png)
      - Subscriber: uses the img src attribute.
    If the URL contains "animated" (case-insensitive), the image is saved as a .gif in a subfolder "gif".
    The relative file path stored in the mapping always includes the folder name.
    A global sleep delay (SLEEP_TIME) is added only after download attempts.
    Returns a tuple (mapping, soup) where mapping is {emote_name: relative_filepath}.
    """
    full_url = TWITCH_BASE_DOMAIN + url_path
    print(f"Fetching Twitch emotes from: {full_url}")
    response = requests.get(full_url, timeout=2)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    mapping = {}
    if subscriber:
        link_pattern = re.compile(r"^/channels/\d+/emotes/")
    else:
        link_pattern = re.compile(r"^/global/emotes/\d+")

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if not link_pattern.search(href):
            continue

        img_tag = a_tag.find("img")
        if not img_tag:
            continue

        emote_name = extract_emote_name(img_tag)
        if not valid_emote_name(emote_name):
            print(f"Skipping emote '{emote_name}' (contains special characters)")
            continue

        if subscriber:
            image_url = img_tag.get("src")
        else:
            emote_id = href.rstrip("/").split("/")[-1]
            image_url = f"https://static-cdn.jtvnw.net/emoticons/v2/{emote_id}/static/light/3.0"

        if "animated" in image_url.lower():
            ext = "gif"
            subfolder = os.path.join(folder, "gif")
            if not os.path.exists(subfolder):
                os.makedirs(subfolder)
            save_folder = subfolder
            rel_filepath = os.path.join(os.path.basename(folder), "gif", f"{emote_name}.{ext}")
        else:
            ext = "png"
            save_folder = folder
            rel_filepath = os.path.join(os.path.basename(folder), f"{emote_name}.{ext}")

        filepath = os.path.join(save_folder, f"{emote_name}.{ext}")
        if save_emote_image(image_url, filepath, emote_name):
            mapping[emote_name] = rel_filepath

    return mapping, soup

def scrape_twitch_loyalty_badges(soup, folder, subid):
    """
    Scans the BeautifulSoup object for loyalty badge images.
    Loyalty badges are detected by an img src containing '/badges/v1/'.
    Extracts the badge number from text (e.g. "0-Month Subscriber").
    Downloads each badge image (as .png) into a subfolder "loyalty" within folder.
    Returns a mapping {number: relative_filepath}.
    """
    badge_mapping = {}
    loyalty_folder = os.path.join(folder, "loyalty")
    if not os.path.exists(loyalty_folder):
        os.makedirs(loyalty_folder)
    for div in soup.find_all("div", class_="col-md-2"):
        img = div.find("img")
        if img and "badges/v1/" in img.get("src", ""):
            image_url = img.get("src")
            text = div.get_text(separator=" ", strip=True)
            m = re.search(r"(\d+)-Month Subscriber", text)
            if not m:
                print(f"Could not decode badge number from text: '{text}'")
                continue
            number = m.group(1)
            filename = f"{number}.png"
            filepath = os.path.join(loyalty_folder, filename)
            rel_filepath = os.path.join(os.path.basename(folder), "loyalty", filename)
            
            if save_emote_image(image_url, filepath, f"loyalty badge {number}"):
                badge_mapping[number] = rel_filepath
                
    return badge_mapping

# BTTV emote scraping function
def scrape_bttv_emotes(channel_id, folder):
    """
    Scrapes BTTV emotes for a given channel ID or global emotes.
    Downloads images in 1x, 2x, and 3x sizes.
    Returns a mapping {emote_name: relative_filepath}.
    """
    print(f"Fetching BTTV emotes for: {channel_id if channel_id != '_global' else 'global'}")
    mapping = {}
    
    if channel_id == '_global':
        url = f'{BTTV_BASE_API}/cached/emotes/global'
        response = requests.get(url, timeout=2)
        if response.status_code != 200:
            print(f"Failed to fetch BTTV global emotes: {response.status_code}")
            return mapping
        emotes = response.json()
    else:
        url = f'{BTTV_BASE_API}/cached/users/twitch/{channel_id}'
        response = requests.get(url, timeout=2)
        if response.status_code != 200:
            print(f"Failed to fetch BTTV channel emotes: {response.status_code}")
            return mapping
        data = response.json()
        emotes = []
        emotes.extend(data.get('channelEmotes', []))
        emotes.extend(data.get('sharedEmotes', []))
    
    bttv_folder = os.path.join(folder, "bttv")
    if not os.path.exists(bttv_folder):
        os.makedirs(bttv_folder)
    
    for emote in emotes:
        emote_name = emote['code']
        if not valid_emote_name(emote_name):
            print(f"Skipping BTTV emote '{emote_name}' (contains special characters)")
            continue
        
        emote_id = emote['id']
        is_animated = emote.get('animated', False)
        ext = "gif" if is_animated else "png"
        
        # Download 3x version
        image_url = f"https://cdn.betterttv.net/emote/{emote_id}/3x"
        filepath = os.path.join(bttv_folder, f"{emote_name}.{ext}")
        rel_filepath = os.path.join(os.path.basename(folder), "bttv", f"{emote_name}.{ext}")
        
        if save_emote_image(image_url, filepath, emote_name):
            mapping[emote_name] = rel_filepath
    
    print(f"Downloaded {len(mapping)} BTTV emotes")
    return mapping

# 7TV emote scraping function
def scrape_seventv_emotes(channel_id, folder):
    """
    Scrapes 7TV emotes for a given channel ID or global emotes.
    Downloads images in 4x size.
    Returns a mapping {emote_name: relative_filepath}.
    """
    print(f"Fetching 7TV emotes for: {channel_id if channel_id != '_global' else 'global'}")
    mapping = {}
    
    if channel_id == '_global':
        url = f'{SEVENTV_BASE_API}/emote-sets/global'
        set_id_key = 'id'
    else:
        url = f'{SEVENTV_BASE_API}/users/twitch/{channel_id}'
        set_id_key = 'emote_set'
        
    response = requests.get(url, timeout=2)
    if response.status_code != 200:
        print(f"Failed to fetch 7TV emotes: {response.status_code}")
        return mapping
        
    data = response.json()
    set_id = data.get(set_id_key)
    
    if not set_id:
        print(f"No 7TV emote set found for {channel_id}")
        return mapping
        
    # If we're getting user emotes, we need to fetch the emote set
    if channel_id != '_global':
        url = f'{SEVENTV_BASE_API}/emote-sets/{set_id}'
        response = requests.get(url, timeout=2)
        if response.status_code != 200:
            print(f"Failed to fetch 7TV emote set: {response.status_code}")
            return mapping
        data = response.json()
    
    seventv_folder = os.path.join(folder, "7tv")
    if not os.path.exists(seventv_folder):
        os.makedirs(seventv_folder)
    
    emotes = data.get('emotes', [])
    for emote in emotes:
        emote_name = emote.get('name')
        if not valid_emote_name(emote_name):
            print(f"Skipping 7TV emote '{emote_name}' (contains special characters)")
            continue
        
        emote_id = emote.get('id')
        if not emote_id:
            continue
            
        # Check if animated by looking at the available files
        files = emote.get('data', {}).get('host', {}).get('files', [])
        is_animated = any(f.get('format') == 'WEBP' or f.get('format') == 'GIF' for f in files)
        
        # Try primary extension first based on animation status
        primary_ext = "gif" if is_animated else "png"
        secondary_ext = "png" if is_animated else "gif"  # Fallback extension

        # Prepare filepaths for both potential file types
        primary_url = f"https://cdn.7tv.app/emote/{emote_id}/4x.{primary_ext}"
        primary_filepath = os.path.join(seventv_folder, f"{emote_name}.{primary_ext}")
        primary_rel_filepath = os.path.join(os.path.basename(folder), "7tv", f"{emote_name}.{primary_ext}")
        
        # Try to download with primary extension
        if save_emote_image(primary_url, primary_filepath, emote_name):
            mapping[emote_name] = primary_rel_filepath
            continue  # Success, move to next emote
            
        # If primary fails, try secondary extension
        print(f"Failed to download {primary_ext} version for {emote_name}, trying {secondary_ext} instead")
        secondary_url = f"https://cdn.7tv.app/emote/{emote_id}/4x.{secondary_ext}"
        secondary_filepath = os.path.join(seventv_folder, f"{emote_name}.{secondary_ext}")
        secondary_rel_filepath = os.path.join(os.path.basename(folder), "7tv", f"{emote_name}.{secondary_ext}")
        
        if save_emote_image(secondary_url, secondary_filepath, emote_name):
            mapping[emote_name] = secondary_rel_filepath
    
    print(f"Downloaded {len(mapping)} 7TV emotes")
    return mapping

# FFZ emote scraping function
def scrape_ffz_emotes(channel_id, folder):
    """
    Scrapes FFZ emotes for a given channel ID or global emotes.
    Downloads images in 4 size (largest available).
    Returns a mapping {emote_name: relative_filepath}.
    """
    print(f"Fetching FFZ emotes for: {channel_id if channel_id != '_global' else 'global'}")
    mapping = {}
    
    if channel_id == '_global':
        url = f'{FFZ_BASE_API}/set/global'
    else:
        url = f'{FFZ_BASE_API}/room/id/{channel_id}'
        
    response = requests.get(url, timeout=2)
    if response.status_code != 200:
        print(f"Failed to fetch FFZ emotes: {response.status_code}")
        return mapping
    
    data = response.json()
    
    # Extract set IDs
    set_ids = []
    if channel_id == '_global':
        default_sets = data.get('default_sets', [])
        set_ids.extend(default_sets)
    else:
        room_sets = data.get('room', {}).get('set', None)
        if room_sets:
            set_ids.append(room_sets)
        user_sets = data.get('sets', {})
    
    ffz_folder = os.path.join(folder, "ffz")
    if not os.path.exists(ffz_folder):
        os.makedirs(ffz_folder)
    
    # Process each set
    for set_id in set_ids:
        if channel_id == '_global':
            set_data = data.get('sets', {}).get(str(set_id), {})
        else:
            set_data = user_sets.get(str(set_id), {})
        
        emotes = set_data.get('emoticons', [])
        for emote in emotes:
            emote_name = emote.get('name')
            if not valid_emote_name(emote_name):
                print(f"Skipping FFZ emote '{emote_name}' (contains special characters)")
                continue
            
            # Get largest available size
            urls = emote.get('urls', {})
            largest_size = sorted(urls.keys(), key=lambda x: int(x))[-1] if urls else None
            if not largest_size:
                continue
                
            image_url = urls[largest_size]
            if not image_url.startswith('http'):
                image_url = 'https:' + image_url
                
            ext = "png"  # FFZ typically uses PNG
            filepath = os.path.join(ffz_folder, f"{emote_name}.{ext}")
            rel_filepath = os.path.join(os.path.basename(folder), "ffz", f"{emote_name}.{ext}")
            
            if save_emote_image(image_url, filepath, emote_name):
                mapping[emote_name] = rel_filepath
    
    print(f"Downloaded {len(mapping)} FFZ emotes")
    return mapping

def process_manual_ffz_emotes(folder):
    """
    Processes manually specified FFZ emote URLs and downloads them.
    Returns a mapping {emote_name: relative_filepath}.
    """
    print(f"Processing {len(MANUAL_FFZ_EMOTES)} manual FFZ emotes")
    mapping = {}
    
    ffz_folder = os.path.join(folder, "ffz")
    if not os.path.exists(ffz_folder):
        os.makedirs(ffz_folder)
    
    for emote_url in MANUAL_FFZ_EMOTES:
        # Extract emote ID and name from the URL - handle both full URLs and path-only formats
        emote_id_match = re.search(r'/emoticon/(\d+)(?:-([A-Za-z0-9_]+))?', emote_url)
        if not emote_id_match:
            print(f"Could not parse emote ID and name from URL: {emote_url}")
            continue
            
        emote_id = emote_id_match.group(1)
        emote_name = emote_id_match.group(2) if emote_id_match.group(2) else None
        
        # If name wasn't in URL, get it from the API
        if not emote_name:
            # Get the emote data from FFZ API
            api_url = f"{FFZ_BASE_API}/emote/{emote_id}"
            try:
                response = requests.get(api_url, timeout=2)
                if response.status_code != 200:
                    print(f"Failed to fetch FFZ emote data: {response.status_code} for {emote_url}")
                    continue
                    
                emote_data = response.json()
                emote_name = emote_data.get('name')
            except Exception as e:
                print(f"Error fetching emote name from API: {e}")
                continue
        
        if not emote_name or not valid_emote_name(emote_name):
            print(f"Skipping manual FFZ emote '{emote_name}' (invalid or missing name)")
            continue
        
        # Construct direct CDN URL for the largest version (4)
        image_url = f"https://cdn.frankerfacez.com/emoticon/{emote_id}/4"
        ext = "png"  # FFZ typically uses PNG
        filepath = os.path.join(ffz_folder, f"{emote_name}.{ext}")
        rel_filepath = os.path.join(os.path.basename(folder), "ffz", f"{emote_name}.{ext}")
        
        if save_emote_image(image_url, filepath, emote_name):
            mapping[emote_name] = rel_filepath
                
    print(f"Downloaded {len(mapping)} manual FFZ emotes")
    return mapping

def update_json(emotes_data, json_path="emotes/emotes.json"):
    """
    Updates the emotes.json file with the given emotes data.
    """
    # Ensure the directory exists
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    
    if os.path.exists(json_path):
        with open(json_path, "r") as f:
            data = json.load(f)
    else:
        data = {
            "global": {},
            "subscriber_emotes": {}
        }
    
    # Update with new data
    for provider, mapping in emotes_data.get("global", {}).items():
        if "global" not in data:
            data["global"] = {}
        data["global"][provider] = mapping
    
    for channel_id, channel_data in emotes_data.get("subscriber_emotes", {}).items():
        if "subscriber_emotes" not in data:
            data["subscriber_emotes"] = {}
        if channel_id not in data["subscriber_emotes"]:
            data["subscriber_emotes"][channel_id] = {}
        
        for provider, mapping in channel_data.items():
            data["subscriber_emotes"][channel_id][provider] = mapping
    
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Updated JSON file: {json_path}")

def main():
    parser = argparse.ArgumentParser(description="Scrape Twitch, BTTV, 7TV, and FFZ emotes and download images.")
    parser.add_argument("--url", type=str, default=None,
                        help="Relative URL to scrape (default: '/' for global or '/channels/<subid>' for subscriber)")
    parser.add_argument("--subscriber", action="store_true",
                        help="If set, scrape subscriber emotes (and loyalty badges)")
    parser.add_argument("--subid", type=str, default="22484632",
                        help="Subscriber ID to use (default: 22484632 for forsen)")
    parser.add_argument("--provider", type=str, choices=["twitch", "bttv", "7tv", "ffz", "all"], default="all",
                        help="Provider to scrape emotes from (default: all)")
    parser.add_argument("--manual_only", action="store_true",
                        help="If set, only process manual emotes without scraping")
    args = parser.parse_args()

    if args.subscriber:
        channel_id = args.subid
        url_path = args.url if args.url is not None else f"/channels/{channel_id}"
        folder_name = channel_id  # folder name is the subscriber id
    else:
        channel_id = "_global"
        url_path = args.url if args.url is not None else "/"
        folder_name = "global"

    # Create base emotes directory if it doesn't exist
    if not os.path.exists(EMOTES_BASE_DIR):
        os.makedirs(EMOTES_BASE_DIR)
    
    # Create full folder path
    folder = os.path.join(EMOTES_BASE_DIR, folder_name)
    if not os.path.exists(folder):
        os.makedirs(folder)
    
    emotes_data = {
        "global": {},
        "subscriber_emotes": {}
    }
    
    # Process manual emotes first
    manual_ffz_emotes = process_manual_ffz_emotes(folder)
    if manual_ffz_emotes:
        if args.subscriber:
            if not channel_id in emotes_data["subscriber_emotes"]:
                emotes_data["subscriber_emotes"][channel_id] = {}
            if "ffz" not in emotes_data["subscriber_emotes"][channel_id]:
                emotes_data["subscriber_emotes"][channel_id]["ffz"] = {}
            # Merge with any existing FFZ emotes
            emotes_data["subscriber_emotes"][channel_id]["ffz"].update(manual_ffz_emotes)
        else:
            if "ffz" not in emotes_data["global"]:
                emotes_data["global"]["ffz"] = {}
            # Merge with any existing FFZ emotes
            emotes_data["global"]["ffz"].update(manual_ffz_emotes)

    # Skip automated scraping if manual_only flag is set
    if not args.manual_only:
        # Process based on selected provider
        if args.provider in ["twitch", "all"]:
            twitch_emotes, soup = scrape_twitch_emotes(url_path, folder, subscriber=args.subscriber)
            if args.subscriber:
                badges_mapping = scrape_twitch_loyalty_badges(soup, folder, channel_id)
                if not channel_id in emotes_data["subscriber_emotes"]:
                    emotes_data["subscriber_emotes"][channel_id] = {}
                emotes_data["subscriber_emotes"][channel_id]["twitch"] = twitch_emotes
                emotes_data["subscriber_emotes"][channel_id]["loyalty_badges"] = badges_mapping
            else:
                emotes_data["global"]["twitch"] = twitch_emotes
        
        if args.provider in ["bttv", "all"]:
            bttv_emotes = scrape_bttv_emotes(channel_id, folder)
            if args.subscriber:
                if not channel_id in emotes_data["subscriber_emotes"]:
                    emotes_data["subscriber_emotes"][channel_id] = {}
                emotes_data["subscriber_emotes"][channel_id]["bttv"] = bttv_emotes
            else:
                emotes_data["global"]["bttv"] = bttv_emotes
        
        if args.provider in ["7tv", "all"]:
            seventv_emotes = scrape_seventv_emotes(channel_id, folder)
            if args.subscriber:
                if not channel_id in emotes_data["subscriber_emotes"]:
                    emotes_data["subscriber_emotes"][channel_id] = {}
                emotes_data["subscriber_emotes"][channel_id]["7tv"] = seventv_emotes
            else:
                emotes_data["global"]["7tv"] = seventv_emotes
        
        if args.provider in ["ffz", "all"]:
            ffz_emotes = scrape_ffz_emotes(channel_id, folder)
            if args.subscriber:
                if not channel_id in emotes_data["subscriber_emotes"]:
                    emotes_data["subscriber_emotes"][channel_id] = {}
                if "ffz" not in emotes_data["subscriber_emotes"][channel_id]:
                    emotes_data["subscriber_emotes"][channel_id]["ffz"] = {}
                # Merge with manual FFZ emotes
                emotes_data["subscriber_emotes"][channel_id]["ffz"].update(ffz_emotes)
            else:
                if "ffz" not in emotes_data["global"]:
                    emotes_data["global"]["ffz"] = {}
                # Merge with manual FFZ emotes
                emotes_data["global"]["ffz"].update(ffz_emotes)
    
    # Update JSON file
    update_json(emotes_data)

if __name__ == "__main__":
    main()
