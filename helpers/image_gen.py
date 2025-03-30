import os
import re
import hashlib
import tempfile
from PIL import Image, ImageDraw, ImageFont

def get_rainbow_color(username):
    """
    Returns a color from a rainbow palette based on the username.
    This ensures the same username always has the same color.
    """
    rainbow_colors = [
        "#FF0000",  # Red
        "#FF7F00",  # Orange
        "#FFFF00",  # Yellow
        "#00FF00",  # Green
        "#0000FF",  # Blue
        "#4B0082",  # Indigo
        "#8B00FF"   # Violet
    ]
    index = int(hashlib.md5(username.encode("utf-8")).hexdigest(), 16) % len(rainbow_colors)
    return rainbow_colors[index]

def create_twitch_chat_image(
    chat_data, 
    emote_map=None, 
    emoji_map=None,
    output_file=None, 
    min_width=300, 
    margin=15, 
    line_spacing=16,
    emote_scale=2.0,     # Emotes and emojis are scaled to emote_scale * text ascent.
    logger=None
):
    """
    Creates an image that mimics a Twitch chat screenshot with:
      - Bold, rainbow-colored usernames using Inter-Bold.ttf
      - Regular text using InterVariable.ttf, all baseline-aligned.
      - Emotes and emojis scaled to emote_scale * text_ascent and vertically centered.
      - Increased spacing between lines.
    
    Parameters:
      chat_data (dict): Contains chats with "username" and "message" keys.
      emote_map (dict): Maps words to image file paths.
      emoji_map (dict): Maps emoji characters to image file paths.
      output_file (str): Path to save the image (PNG). If None, a temporary file is used.
      min_width (int): Minimum image width.
      margin (int): Margin around the text.
      line_spacing (int): Vertical spacing between lines.
      emote_scale (float): Factor to scale the emote/emoji height relative to the text ascent.
      logger: Optional logger for messages.
    
    Returns:
      PIL.Image: The generated image.
    """
    if emote_map is None:
        emote_map = {}
    if emoji_map is None:
        emoji_map = {}
    if logger:
        logger.info("Creating Twitch chat image")
        
    # If no output file is specified, create a temporary file.
    if output_file is None:
        fd, output_file = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        if logger:
            logger.info(f"No output file specified, using temporary file: {output_file}")

    # Use fonts from your helpers folder.
    inter_font_paths = ["./helpers/InterVariable.ttf"]
    inter_bold_font_paths = ["./helpers/Inter-Bold.ttf"]

    def load_first_available_font(paths, size=16):
        for path in paths:
            if os.path.exists(path):
                return ImageFont.truetype(path, size=size)
        return None

    font = load_first_available_font(inter_font_paths, size=16)
    if font is None:
        font = ImageFont.load_default()
    bold_font = load_first_available_font(inter_bold_font_paths, size=16)
    if bold_font is None:
        bold_font = ImageFont.load_default()

    # Set background and text colors.
    bg_color = "#18181B"
    text_color = "#FFFFFF"

    # Create a dummy image to measure text widths.
    dummy_img = Image.new("RGB", (1,1), bg_color)
    measure_draw = ImageDraw.Draw(dummy_img)

    def measure_text(text_str, font_obj):
        bbox = measure_draw.textbbox((0, 0), text_str, font=font_obj)
        return bbox[2] - bbox[0]

    # Get font metrics for baseline alignment.
    asc_normal, des_normal = font.getmetrics()   # For InterVariable.ttf
    asc_bold, des_bold = bold_font.getmetrics()    # For Inter-Bold.ttf
    # Use the maximum ascent and descent among the two fonts.
    text_line_ascent = max(asc_normal, asc_bold)
    text_line_descent = max(des_normal, des_bold)
    text_line_height = text_line_ascent + text_line_descent

    # Define spacing between elements.
    emote_spacing = 5  # Space between emotes/emojis or between text and images

    # Prepare an emoji regex pattern that matches common emoji ranges.
    emoji_pattern = re.compile(
        "([\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF])",
        flags=re.UNICODE
    )

    # We'll build a list of line information.
    # Each entry: (username, tokens, line_width, line_height, baseline_offset)
    # tokens: list of (token_type, content, width)
    lines_info = []
    max_line_width = 0
    total_height = margin

    # Process each chat line.
    for chat in chat_data.get("chats", []):
        username = chat.get("username", "Unknown")
        message  = chat.get("message", "")
        
        line_tokens = []
        # Username token (drawn in bold).
        uname_width = measure_text(username, bold_font)
        line_tokens.append(("username", username, uname_width))
        # Add colon + space (drawn in regular font).
        colon_text = ": "
        colon_width = measure_text(colon_text, font)
        line_tokens.append(("text", colon_text, colon_width))
        
        # Process the message word-by-word.
        # Each word is further split to isolate emojis.
        words = message.split()
        for i, word in enumerate(words):
            # If the whole word is a known emote, handle it.
            if word in emote_map:
                # Add spacing before emote (except immediately after colon).
                if len(line_tokens) > 2:
                    line_tokens.append(("space", " ", emote_spacing))
                line_tokens.append(("emote", emote_map[word], None))
            else:
                # Add a space before this word if not the first word.
                if i > 0:
                    space_width = measure_text(" ", font)
                    line_tokens.append(("text", " ", space_width))
                # Split the word by emojis.
                parts = emoji_pattern.split(word)
                for part in parts:
                    if not part:
                        continue
                    # If the part is an emoji (matches the emoji pattern exactly)
                    if emoji_pattern.fullmatch(part):
                        if part in emoji_map:
                            line_tokens.append(("emoji", emoji_map[part], None))
                        else:
                            # Fallback: render the emoji as text.
                            line_tokens.append(("text", part, measure_text(part, font)))
                    else:
                        line_tokens.append(("text", part, measure_text(part, font)))
        
        # Determine the scaled emote/emoji size for this line.
        scaled_emote_size = int(text_line_ascent * emote_scale)
        # For each token that is an emote or emoji, assign its width as the scaled_emote_size.
        i = 0
        while i < len(line_tokens):
            token_type, content, width = line_tokens[i]
            if token_type in ("emote", "emoji"):
                line_tokens[i] = (token_type, content, scaled_emote_size)
                # Add spacing after the image if it's not the last token.
                if i < len(line_tokens) - 1:
                    line_tokens.insert(i + 1, ("space", " ", emote_spacing))
                    i += 1  # Skip the space we just added.
            i += 1
        
        # Calculate total line width.
        line_width = sum(token[2] for token in line_tokens)
        # Final line height is the maximum of the text height and any image size.
        line_height = max(text_line_height, scaled_emote_size)
        # Compute baseline offset for text tokens:
        # The baseline (for text drawing) will be at:
        #    y_line_top + (line_height - text_line_height) + text_line_ascent
        baseline_offset = (line_height - text_line_height) + text_line_ascent
        
        lines_info.append((username, line_tokens, line_width, line_height, baseline_offset))
        max_line_width = max(max_line_width, line_width)
        total_height += line_height + line_spacing

    total_height += margin - line_spacing  # Remove extra spacing after last line.
    final_width = max(min_width, max_line_width + margin * 2)

    # Create the final image.
    img = Image.new("RGB", (final_width, total_height), bg_color)
    draw = ImageDraw.Draw(img)

    y_cursor = margin
    for username, line_tokens, line_width, line_height, baseline_offset in lines_info:
        # Compute the common text baseline for this line.
        text_baseline = y_cursor + baseline_offset
        x_cursor = margin
        for token_type, content, width in line_tokens:
            if token_type == "username":
                # Draw bold text with its baseline aligned.
                y_text = text_baseline - asc_bold
                draw.text((x_cursor, y_text), content, font=bold_font, fill=get_rainbow_color(username))
            elif token_type == "text":
                # Draw normal text with baseline alignment.
                y_text = text_baseline - asc_normal
                draw.text((x_cursor, y_text), content, font=font, fill=text_color)
            elif token_type in ("emote", "emoji"):
                # For images, vertically center them within the line.
                image_size = width  # width is set to scaled_emote_size.
                y_image = y_cursor + (line_height - image_size) // 2
                try:
                    if os.path.exists(content):
                        with Image.open(content) as im:
                            # If the image is an animated GIF, use its last frame.
                            if getattr(im, "is_animated", False):
                                im.seek(im.n_frames - 1)
                            im = im.convert("RGBA")
                            im_scaled = im.resize((image_size, image_size), Image.LANCZOS)
                            img.paste(im_scaled, (x_cursor, y_image), im_scaled)
                    else:
                        if logger:
                            logger.warning(f"Image file not found: {content}")
                        # Draw placeholder for missing image.
                        draw.text((x_cursor, text_baseline - asc_normal), "[IMG]", font=font, fill="#FF0000")
                except Exception as e:
                    if logger:
                        logger.error(f"Error processing image {content}: {e}")
                    draw.text((x_cursor, text_baseline - asc_normal), "[IMG?]", font=font, fill="#FF0000")
            # For spacing tokens, we just advance the cursor.
            x_cursor += width
        y_cursor += line_height + line_spacing

    try:
        img.save(output_file)
        if logger:
            logger.info(f"Chat image saved to {output_file}")
        return output_file
    except Exception as e:
        if logger:
            logger.error(f"Failed to save chat image: {e}")
        return None

# ----------------
# Example Usage
# ----------------
if __name__ == "__main__":
    sample_chat_data = {
        "chats": [
            {"username": "RainbowUser", "message": "Hello forsenCD PogChamp 😀"},
            {"username": "StreamerFan", "message": "This is so cool! forsenCD PogChamp 😎"},
            {"username": "ChatBot",     "message": "Automated message incoming... forsenCD forsenCD forsenCD 😂"}
        ]
    }
    
    sample_emote_map = {
        "forsenCD": "./emotes/global/forsenCD.png",
        "PogChamp": "./emotes/global/PogChamp.png"
    }
    
    # Optional: provide a mapping for emojis to image files.
    sample_emoji_map = {
        "😀": "./emotes/emoji/grinning.png",
        "😎": "./emotes/emoji/sunglasses.png",
        "😂": "./emotes/emoji/joy.png"
    }
    
    output_path = create_twitch_chat_image(
        chat_data=sample_chat_data,
        emote_map=sample_emote_map,
        emoji_map=sample_emoji_map,
        output_file="twitch_chat_inter.png",
        min_width=400,
        margin=25,
        line_spacing=5,
        emote_scale=2.0
    )
    print(f"Chat image created: {output_path}")
