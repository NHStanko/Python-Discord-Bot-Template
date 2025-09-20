import os
import re
import hashlib
import tempfile
import random
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
    emote_scale=2.0,     # Emotes, badges, and emojis are scaled to emote_scale * text ascent.
    max_content_width=475,
    logger=None
):
    """
    Creates an image that mimics a Twitch chat screenshot with:
      - Bold, rainbow-colored usernames using Inter-Bold.ttf
      - Regular text using InterVariable.ttf, all baseline-aligned.
      - Subscriber loyalty badges, emotes, and emojis scaled to emote_scale * text_ascent and vertically centered.
      - Increased spacing between lines.
      - Automatic wrapping when messages exceed max_content_width so they can span multiple lines.
    
    Parameters:
      chat_data (dict): Contains chats with "username" and "message" keys.
      emote_map (dict): Maps words to image file paths.
      emoji_map (dict): Maps emoji characters to image file paths.
      output_file (str): Path to save the image (PNG). If None, a temporary file is used.
      min_width (int): Minimum image width.
      margin (int): Margin around the text.
      line_spacing (int): Vertical spacing between lines.
      emote_scale (float): Factor to scale the badge/emote/emoji height relative to the text ascent.
      max_content_width (int): Maximum width (in pixels) for a single chat line before wrapping.
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

    def build_italic_font():
        italic_candidate = load_first_available_font(inter_font_paths, size=16)
        if italic_candidate is None:
            return font, False
        italicized = False
        try:
            variation_loaded = False
            if hasattr(italic_candidate, "get_variation_names"):
                try:
                    names = italic_candidate.get_variation_names()
                    if names and "Italic" in names:
                        italic_candidate.set_variation_by_name("Italic")
                        variation_loaded = True
                        italicized = True
                except OSError:
                    pass
            if not variation_loaded and hasattr(italic_candidate, "get_variation_axes"):
                try:
                    axes = italic_candidate.get_variation_axes()
                    coords = []
                    for axis in axes:
                        tag = axis.axisTag
                        if tag == "ital":
                            coords.append(axis.maximum)
                        elif tag == "slnt":
                            coords.append(axis.maximum)
                        else:
                            coords.append(axis.defaultValue)
                    if coords:
                        italic_candidate.set_variation_by_axes(coords)
                        variation_loaded = True
                        italicized = True
                except (AttributeError, OSError):
                    pass
            return italic_candidate, italicized
        except AttributeError:
            return italic_candidate, italicized

    italic_font, italic_font_is_distinct = build_italic_font()

    # Set background and text colors.
    bg_color = "#18181B"
    text_color = "#FFFFFF"
    deleted_text_color = "#9BA3AE"
    content_width_limit = max(max_content_width, max(0, min_width - margin * 2))

    # Create a dummy image to measure text widths.
    dummy_img = Image.new("RGB", (1,1), bg_color)
    measure_draw = ImageDraw.Draw(dummy_img)

    def measure_text(text_str, font_obj):
        bbox = measure_draw.textbbox((0, 0), text_str, font=font_obj)
        return bbox[2] - bbox[0]

    def draw_faux_italic_text(base_img, position, text_str, fill_color):
        x_pos, y_pos = position
        if not text_str:
            return
        bbox = measure_draw.textbbox((0, 0), text_str, font=font)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        if width <= 0 or height <= 0:
            return
        padding = 2
        temp_img = Image.new("RGBA", (width + padding * 2, height + padding * 2), (0, 0, 0, 0))
        temp_draw = ImageDraw.Draw(temp_img)
        temp_draw.text((padding - bbox[0], padding - bbox[1]), text_str, font=font, fill=fill_color)
        shear = 0.3
        transformed_width = int(temp_img.width + abs(shear) * temp_img.height)
        skewed = temp_img.transform(
            (transformed_width, temp_img.height),
            Image.AFFINE,
            (1, shear, 0, 0, 1, 0),
            resample=Image.BICUBIC,
        )
        base_img.paste(skewed, (int(x_pos), int(y_pos)), skewed)

    # Get font metrics for baseline alignment.
    asc_normal, des_normal = font.getmetrics()   # For InterVariable.ttf
    asc_bold, des_bold = bold_font.getmetrics()    # For Inter-Bold.ttf
    asc_italic, des_italic = italic_font.getmetrics()
    # Use the maximum ascent and descent among the two fonts.
    text_line_ascent = max(asc_normal, asc_bold, asc_italic)
    text_line_descent = max(des_normal, des_bold, des_italic)
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
    # Each entry: (username, tokens, line_width, line_height, baseline_offset, is_deleted, is_continuation, indent_width)
    # tokens: list of (token_type, content, width)
    lines_info = []
    max_line_width = 0
    continuation_spacing = max(2, line_spacing // 2)

    # Process each chat line.
    for chat in chat_data.get("chats", []):
        username = chat.get("username", "Unknown")
        message = chat.get("message", "")
        deleted_original = chat.get("deleted_original")

        is_deleted = False
        display_message = message

        if deleted_original:
            display_message = deleted_original
            is_deleted = True
        elif "message deleted" in message.lower():
            is_deleted = True

        timeout_suffix_text = None
        if is_deleted:
            display_message = display_message.strip()
            if not display_message:
                display_message = "message deleted by moderator"
            timeout_suffix_text = "-Permanently Banned" if random.random() < 0.01 else "-Timed out (600s)"

        line_tokens = []
        badge_path = chat.get("subscriber_badge")
        if badge_path:
            line_tokens.append(("badge", badge_path, None))
        # Username token (drawn in bold).
        uname_width = measure_text(username, bold_font)
        line_tokens.append(("username", username, uname_width))
        # Add colon + space (drawn in regular font).
        colon_text = ": "
        colon_width = measure_text(colon_text, font)
        line_tokens.append(("text", colon_text, colon_width))
        
        # Process the message word-by-word.
        # Each word is further split to isolate emojis.
        words = display_message.split()
        for i, word in enumerate(words):
            # If the whole word is a known emote, handle it.
            if not is_deleted and word in emote_map:
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
                    if not is_deleted and emoji_pattern.fullmatch(part):
                        if part in emoji_map:
                            line_tokens.append(("emoji", emoji_map[part], None))
                        else:
                            # Fallback: render the emoji as text.
                            line_tokens.append(("text", part, measure_text(part, font)))
                    else:
                        line_tokens.append(("text", part, measure_text(part, font)))

        if timeout_suffix_text:
            if line_tokens and line_tokens[-1][0] != "space":
                space_width = measure_text(" ", font)
                line_tokens.append(("text", " ", space_width))
            italic_measure = measure_text(timeout_suffix_text, italic_font)
            line_tokens.append(("italic_text", timeout_suffix_text, italic_measure))

        # Determine the scaled badge/emote/emoji size for this line.
        scaled_emote_size = int(text_line_ascent * emote_scale)
        # Badges stay slightly smaller than emotes to mimic Twitch styling.
        scaled_badge_size = max(1, int(round(scaled_emote_size * 0.75)))
        # For each token that is a badge, emote, or emoji, assign its width (badges slightly smaller).
        i = 0
        while i < len(line_tokens):
            token_type, content, width = line_tokens[i]
            if token_type in ("badge", "emote", "emoji"):
                new_width = scaled_badge_size if token_type == "badge" else scaled_emote_size
                line_tokens[i] = (token_type, content, new_width)
                # Add spacing after the image if it's not the last token.
                if i < len(line_tokens) - 1:
                    line_tokens.insert(i + 1, ("space", " ", emote_spacing))
                    i += 1  # Skip the space we just added.
            i += 1

        message_start_index = len(line_tokens)
        for idx, (token_type, content, _) in enumerate(line_tokens):
            if token_type == "text" and content == ": ":
                message_start_index = idx + 1
                break

        # Wrap tokens so long messages can span multiple lines.
        wrapped_lines = []
        current_tokens = []
        current_width = 0
        for original_idx, token in enumerate(line_tokens):
            token_width = token[2]
            message_started = original_idx >= message_start_index
            exceeds_limit = (
                current_tokens
                and current_width + token_width > content_width_limit
                and message_started
            )
            if exceeds_limit:
                is_continuation = len(wrapped_lines) > 0
                wrapped_lines.append((current_tokens, current_width, is_continuation))
                current_tokens = []
                current_width = 0
                if token[0] == "space":
                    continue
            current_tokens.append(token)
            current_width += token_width

        if current_tokens:
            is_continuation = len(wrapped_lines) > 0
            wrapped_lines.append((current_tokens, current_width, is_continuation))

        # Final line height is the maximum of the text height and any image size.
        line_height = max(text_line_height, scaled_emote_size)
        # Compute baseline offset for text tokens:
        # The baseline (for text drawing) will be at:
        #    y_line_top + (line_height - text_line_height) + text_line_ascent
        baseline_offset = (line_height - text_line_height) + text_line_ascent

        for tokens, line_width, is_continuation in wrapped_lines:
            indent_width = 0
            total_line_width = line_width
            lines_info.append((username, tokens, total_line_width, line_height, baseline_offset, is_deleted, is_continuation, indent_width))
            max_line_width = max(max_line_width, total_line_width)
    
    total_height = margin
    if lines_info:
        for idx, line in enumerate(lines_info):
            _, _, _, line_height, _, _, _, _ = line
            total_height += line_height
            if idx < len(lines_info) - 1:
                next_is_continuation = lines_info[idx + 1][6]
                total_height += continuation_spacing if next_is_continuation else line_spacing
        total_height += margin
    else:
        total_height += margin  # Maintain minimal height when no lines.

    final_width = max(min_width, max_line_width + margin * 2)

    # Create the final image.
    img = Image.new("RGB", (final_width, total_height), bg_color)
    draw = ImageDraw.Draw(img)

    y_cursor = margin
    for idx, (username, line_tokens, line_width, line_height, baseline_offset, is_deleted, is_continuation, indent_width) in enumerate(lines_info):
        # Compute the common text baseline for this line.
        text_baseline = y_cursor + baseline_offset
        x_cursor = margin + indent_width
        current_text_color = deleted_text_color if is_deleted else text_color
        for token_type, content, width in line_tokens:
            if token_type == "username":
                # Draw bold text with its baseline aligned.
                y_text = text_baseline - asc_bold
                draw.text((x_cursor, y_text), content, font=bold_font, fill=get_rainbow_color(username))
            elif token_type == "text":
                # Draw normal text with baseline alignment.
                y_text = text_baseline - asc_normal
                draw.text((x_cursor, y_text), content, font=font, fill=current_text_color)
            elif token_type == "badge":
                # Align badge bottom with text baseline for a natural look.
                image_size = width
                baseline_bottom = text_baseline + des_normal
                y_image = baseline_bottom - image_size
                if y_image < y_cursor:
                    y_image = y_cursor
                try:
                    if os.path.exists(content):
                        with Image.open(content) as im:
                            if getattr(im, "is_animated", False):
                                im.seek(im.n_frames - 1)
                            im = im.convert("RGBA")
                            im_scaled = im.resize((image_size, image_size), Image.LANCZOS)
                            img.paste(im_scaled, (x_cursor, y_image), im_scaled)
                    else:
                        if logger:
                            logger.warning(f"Image file not found: {content}")
                        draw.text((x_cursor, text_baseline - asc_normal), "[IMG]", font=font, fill="#FF0000")
                except Exception as e:
                    if logger:
                        logger.error(f"Error processing image {content}: {e}")
                    draw.text((x_cursor, text_baseline - asc_normal), "[IMG?]", font=font, fill="#FF0000")
            elif token_type in ("emote", "emoji"):
                # For emotes/emoji, keep vertical centering.
                image_size = width
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
            elif token_type == "italic_text":
                y_text = text_baseline - asc_italic
                if italic_font_is_distinct:
                    draw.text((x_cursor, y_text), content, font=italic_font, fill=current_text_color)
                else:
                    faux_y = text_baseline - asc_normal
                    draw_faux_italic_text(img, (x_cursor, faux_y), content, current_text_color)
            # For spacing tokens, we just advance the cursor.
            x_cursor += width
        y_cursor += line_height
        if idx < len(lines_info) - 1:
            next_is_continuation = lines_info[idx + 1][6]
            y_cursor += continuation_spacing if next_is_continuation else line_spacing

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
