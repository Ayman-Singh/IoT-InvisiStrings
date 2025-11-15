#!/usr/bin/env python3
"""
Guitar chord visualizer + UDP-triggered audio playback with sustain+fade.
Put audio files (1.mp3..10.mp3) in same folder as this script.
"""

import socket
import json
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.patches import FancyArrow, Circle
from collections import deque
import time
import threading
import os
import sys
import numpy as np

# ---------------------------
# Audio playback dependencies
# ---------------------------
try:
    import pygame
    import pygame.mixer
except ImportError as e:
    print("Missing pygame. Install with: pip install pygame")
    sys.exit(1)

# ---------------------------
# UDP Configuration (shared)
# ---------------------------
UDP_IP = "0.0.0.0"
UDP_PORT = 5005

# Create UDP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))
sock.settimeout(0.01)

print(f"Listening for touch and strum events on {UDP_IP}:{UDP_PORT}")

# ---------------------------
# Chord / strum state
# ---------------------------
current_chord = 1  # Default chord is 1 (sensor 1)

# Chord name mapping
CHORD_NAMES = {
    1: 'A',
    2: 'C',
    3: 'D',
    4: 'Em',
    5: 'G'
}

up_strum_count = 0
down_strum_count = 0
total_strums = 0
total_plays = 0

recent_strums = deque(maxlen=10)
recent_plays = deque(maxlen=20)

current_strum_display = None
strum_display_until = 0
STRUM_DISPLAY_DURATION = 0.5

last_played_chord = None
last_play_time = 0

packet_count = 0

# ---------------------------
# Audio playback configuration
# ---------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Extended mapping for all 5 sensors (1.mp3 to 10.mp3)
# Sensor 1: UP=1.mp3, DOWN=2.mp3
# Sensor 2: UP=3.mp3, DOWN=4.mp3
# Sensor 3: UP=5.mp3, DOWN=6.mp3
# Sensor 4: UP=7.mp3, DOWN=8.mp3
# Sensor 5: UP=9.mp3, DOWN=10.mp3
STRUM_AUDIO_MAP = {
    (1, 'UP'):   os.path.join(BASE_DIR, "1.mp3"), #A
    (1, 'DOWN'): os.path.join(BASE_DIR, "2.mp3"),
    (2, 'UP'):   os.path.join(BASE_DIR, "3.mp3"), #C
    (2, 'DOWN'): os.path.join(BASE_DIR, "4.mp3"),
    (3, 'UP'):   os.path.join(BASE_DIR, "5.mp3"), #D
    (3, 'DOWN'): os.path.join(BASE_DIR, "6.mp3"),
    (4, 'UP'):   os.path.join(BASE_DIR, "7.mp3"), #Em
    (4, 'DOWN'): os.path.join(BASE_DIR, "8.mp3"),
    (5, 'UP'):   os.path.join(BASE_DIR, "9.mp3"), # G
    (5, 'DOWN'): os.path.join(BASE_DIR, "10.mp3"),
}

# Initialize pygame mixer
pygame.mixer.pre_init(44100, -16, 2, 512)  # frequency, size, channels, buffer
pygame.init()
pygame.mixer.init()
pygame.mixer.set_num_channels(16)  # Allow up to 16 overlapping sounds

# Pre-load all sounds for better performance
print("Loading audio files...")
sound_cache = {}
for key, path in STRUM_AUDIO_MAP.items():
    if os.path.isfile(path):
        try:
            sound_cache[key] = pygame.mixer.Sound(path)
            print(f"  ✓ Loaded: {os.path.basename(path)} for chord={key[0]} direction={key[1]}")
        except Exception as e:
            print(f"  ✗ Error loading {os.path.basename(path)}: {e}")
    else:
        print(f"  ✗ File not found: {os.path.basename(path)}")

if not sound_cache:
    print("\n⚠ WARNING: No audio files loaded! Please ensure 1.mp3 through 10.mp3 are in the script directory.")
else:
    print(f"\n✓ Successfully loaded {len(sound_cache)} audio files")

# Audio fade configuration
FADE_OUT_MS = 900  # Fade out duration in milliseconds

def play_strum_sound(chord, direction):
    """
    Play the mapped audio for (chord, direction) with automatic overlap handling.
    pygame.mixer automatically handles overlapping sounds across multiple channels.
    """
    key = (int(chord), direction.upper())
    sound = sound_cache.get(key)
    
    if sound:
        try:
            # Find an available channel and play
            # pygame automatically handles channel allocation
            channel = sound.play(fade_ms=FADE_OUT_MS)
            if channel is None:
                # All channels busy, force play on channel 0
                pygame.mixer.Channel(0).play(sound, fade_ms=FADE_OUT_MS)
                print(f"[{time.strftime('%H:%M:%S')}] Playing {os.path.basename(STRUM_AUDIO_MAP[key])} (forced)")
            else:
                print(f"[{time.strftime('%H:%M:%S')}] Playing {os.path.basename(STRUM_AUDIO_MAP[key])} on channel {channel}")
        except Exception as e:
            print(f"Error playing sound: {e}")
    else:
        print(f"No audio mapping or file for chord={chord}, direction={direction}")

# ---------------------------
# Visualization setup
# ---------------------------
fig = plt.figure(figsize=(16, 10))
gs = fig.add_gridspec(3, 2, hspace=0.3, wspace=0.3)

# Subplot 1: Current Chord Fingering
ax_chord = fig.add_subplot(gs[0, 0])
ax_chord.set_xlim(-0.5, 5.5)
ax_chord.set_ylim(-0.5, 1.5)
ax_chord.set_aspect('equal')
ax_chord.axis('off')
ax_chord.set_title('Current Chord Fingering', fontsize=14, fontweight='bold')

# Draw 5 strings
for i in range(5):
    ax_chord.plot([i, i], [0, 1], 'gray', linewidth=3, alpha=0.6)
    chord_name = CHORD_NAMES.get(i+1, str(i+1))
    ax_chord.text(i, -0.3, f'{chord_name}', ha='center', fontsize=12, fontweight='bold', color='blue')

# Finger indicators
finger_circles = []
for i in range(5):
    circle = ax_chord.add_patch(Circle((i, 0.5), 0.15, color='lightgray', alpha=0.3))
    finger_circles.append(circle)

chord_status_text = ax_chord.text(2.5, 1.3, 'Chord: 1', ha='center', fontsize=14,
                                  fontweight='bold', color='blue')

# Subplot 2: Strum visualization
ax_strum = fig.add_subplot(gs[0, 1])
ax_strum.set_xlim(-1, 1)
ax_strum.set_ylim(-1.5, 1.5)
ax_strum.set_aspect('equal')
ax_strum.axis('off')
ax_strum.set_title('Strum Direction', fontsize=14, fontweight='bold')

# Draw guitar strings
string_y_positions = np.linspace(-0.8, 0.8, 5)
for y in string_y_positions:
    ax_strum.plot([-0.6, 0.6], [y, y], 'gray', linewidth=2, alpha=0.6)

# Pick visualization
pick_artist = ax_strum.add_patch(Circle((0, 0), 0.15, color='orange', alpha=0.8))
pick_arrow = ax_strum.add_patch(FancyArrow(0, 0, 0, 0.0, width=0.2, head_width=0.3,
                                          head_length=0.2, color='red', alpha=0))
strum_text = ax_strum.text(0, -1.2, 'Waiting...', ha='center', fontsize=16,
                           fontweight='bold', color='gray')

# Subplot 3: Statistics
ax_stats = fig.add_subplot(gs[1, 0])
ax_stats.set_xlim(0, 10)
ax_stats.set_ylim(0, 10)
ax_stats.axis('off')
ax_stats.set_title('Statistics', fontsize=14, fontweight='bold')

stats_text = ax_stats.text(5, 5, '', ha='center', va='center', fontsize=11,
                           family='monospace',
                           bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8))

# Subplot 4: Last Played
ax_last_played = fig.add_subplot(gs[1, 1])
ax_last_played.set_xlim(0, 10)
ax_last_played.set_ylim(0, 10)
ax_last_played.axis('off')
ax_last_played.set_title('Last Played Chord', fontsize=14, fontweight='bold')

last_played_text = ax_last_played.text(5, 5, 'No chord played yet', ha='center',
                                       va='center', fontsize=12,
                                       bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.8))

# Subplot 5: Recent plays timeline
ax_timeline = fig.add_subplot(gs[2, :])
ax_timeline.set_xlim(0, 20)
ax_timeline.set_ylim(-1, 1)
ax_timeline.set_xlabel('Recent Chord Plays (newest on right)', fontsize=10)
ax_timeline.set_title('Play History (Last 20)', fontsize=14, fontweight='bold')
ax_timeline.set_yticks([])
ax_timeline.grid(True, axis='x', alpha=0.3)

timeline_artists = []

def chord_to_string(chord):
    """Convert chord value to readable string"""
    return CHORD_NAMES.get(chord, str(chord))

def update_chord_display():
    """Update the chord fingering visualization"""
    for i in range(5):
        finger_circles[i].set_color('lightgray')
        finger_circles[i].set_alpha(0.3)

    if 1 <= current_chord <= 5:
        finger_circles[current_chord - 1].set_color('red')
        finger_circles[current_chord - 1].set_alpha(0.9)

    chord_status_text.set_text(f'Active Chord: {current_chord}')

def update_strum_visualization(strum_info, current_time):
    """Update the strum direction visualization"""
    global strum_display_until, current_strum_display, pick_arrow

    if strum_info is not None:
        current_strum_display = strum_info
        strum_display_until = current_time + STRUM_DISPLAY_DURATION

    if current_time < strum_display_until and current_strum_display is not None:
        direction = current_strum_display['direction']

        try:
            pick_arrow.remove()
        except Exception:
            pass

        if direction == 'UP':
            pick_arrow = ax_strum.add_patch(FancyArrow(0, -0.4, 0, 0.8, width=0.12,
                                                      head_width=0.25, head_length=0.2,
                                                      color='red', alpha=0.9))
            strum_text.set_text('⬆ UP STRUM! ⬆')
            strum_text.set_color('red')
            pick_artist.set_color('red')
        else:
            pick_arrow = ax_strum.add_patch(FancyArrow(0, 0.4, 0, -0.8, width=0.12,
                                                      head_width=0.25, head_length=0.2,
                                                      color='green', alpha=0.9))
            strum_text.set_text('⬇ DOWN STRUM! ⬇')
            strum_text.set_color('green')
            pick_artist.set_color('green')
    else:
        try:
            pick_arrow.remove()
        except Exception:
            pass
        pick_arrow = ax_strum.add_patch(FancyArrow(0, 0, 0, 0.0, width=0.2, head_width=0.3,
                                                  head_length=0.2, color='red', alpha=0))
        strum_text.set_text('Waiting...')
        strum_text.set_color('gray')
        pick_artist.set_color('orange')

def update_timeline():
    """Update the timeline of recent chord plays"""
    for artist in timeline_artists:
        try:
            artist.remove()
        except Exception:
            pass
    timeline_artists.clear()

    for i, play in enumerate(recent_plays):
        x_pos = i + 0.5
        direction = play['direction']

        if direction == 'UP':
            marker = ax_timeline.add_patch(
                FancyArrow(x_pos, -0.5, 0, 0.4, width=0.2, head_width=0.4,
                           head_length=0.15, color='red', alpha=0.7)
            )
        else:
            marker = ax_timeline.add_patch(
                FancyArrow(x_pos, 0.5, 0, -0.4, width=0.2, head_width=0.4,
                           head_length=0.15, color='green', alpha=0.7)
            )
        timeline_artists.append(marker)

        chord_str = play['chord_str']
        text = ax_timeline.text(x_pos, 0, chord_str, ha='center', va='center',
                                fontsize=8, fontweight='bold')
        timeline_artists.append(text)

def update(frame):
    global packet_count, current_chord
    global up_strum_count, down_strum_count, total_strums, total_plays
    global last_played_chord, last_play_time

    packets_this_frame = 0
    new_strum = None
    current_time_val = time.time()
    chord_updated = False

    while packets_this_frame < 10:
        try:
            data, addr = sock.recvfrom(1024)
            packet_count += 1
            packets_this_frame += 1

            json_data = json.loads(data.decode('utf-8'))

            # Check if it's a touch sensor event
            if json_data.get('device') == 'touch_esp' or 'sensor' in json_data:
                sensor_idx = None
                try:
                    sensor_idx = int(json_data.get('sensor', json_data.get('s', json_data.get('value', None))))
                except Exception:
                    sensor_idx = None

                if sensor_idx is not None and 1 <= sensor_idx <= 5:
                    current_chord = sensor_idx
                    chord_updated = True
                    print(f"🎵 Chord changed to: {current_chord} (Sensor {sensor_idx} pressed)")

            # Check if it's a strum event
            elif json_data.get('type') == 'strum' or ('direction' in json_data and json_data.get('type') is None):
                direction = json_data.get('direction', '').upper()
                if direction not in ('UP', 'DOWN'):
                    direction = 'UP' if json_data.get('delta', 0) > 0 else 'DOWN'
                
                try:
                    peak = float(json_data.get('peak', 0))
                except Exception:
                    peak = 0.0
                duration = json_data.get('duration', 0)

                if direction == 'UP':
                    up_strum_count += 1
                else:
                    down_strum_count += 1
                total_strums += 1

                # PLAY THE CHORD!
                total_plays += 1
                chord_str = chord_to_string(current_chord)

                play_info = {
                    'direction': direction,
                    'chord': current_chord,
                    'chord_str': chord_str,
                    'time': current_time_val
                }
                recent_plays.append(play_info)

                strum_info = {
                    'direction': direction,
                    'peak': peak,
                    'duration': duration
                }
                recent_strums.append(strum_info)
                new_strum = strum_info

                # Update last played
                last_played_chord = current_chord
                last_play_time = current_time_val

                # Console output
                print(f"🎸 {direction} STRUM! Playing chord: {chord_str} (Peak: {peak:.1f})")

                # AUDIO PLAYBACK - direct call (no threading needed with pygame)
                play_strum_sound(current_chord, direction)

        except socket.timeout:
            break
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            break
        except Exception as e:
            print("Unexpected recv/parse error:", e)
            break

    # Update visualizations
    if chord_updated:
        update_chord_display()

    update_strum_visualization(new_strum, current_time_val)

    # Update statistics
    if total_strums > 0:
        up_pct = (up_strum_count / total_strums) * 100
        down_pct = (down_strum_count / total_strums) * 100
    else:
        up_pct = down_pct = 0

    stats_text.set_text(
        f'┌──────────────────┐\n'
        f'│   STATISTICS     │\n'
        f'├──────────────────┤\n'
        f'│ ⬆ UP:    {up_strum_count:4d}   │\n'
        f'│ ⬇ DOWN:  {down_strum_count:4d}   │\n'
        f'│ STRUMS:  {total_strums:4d}   │\n'
        f'│ PLAYS:   {total_plays:4d}   │\n'
        f'├──────────────────┤\n'
        f'│ UP:    {up_pct:5.1f}%  │\n'
        f'│ DOWN:  {down_pct:5.1f}%  │\n'
        f'├──────────────────┤\n'
        f'│ Packets: {packet_count:5d} │\n'
        f'└──────────────────┘'
    )

    # Update last played display
    if last_played_chord is not None:
        time_since = current_time_val - last_play_time
        chord_str = chord_to_string(last_played_chord)

        visual = ""
        for i in range(1, 6):
            if i == last_played_chord:
                visual += "█ "
            else:
                visual += "○ "

        last_played_text.set_text(
            f'Chord: {chord_str}\n'
            f'{visual}\n'
            f'{time_since:.1f}s ago'
        )

    update_timeline()

    return ([pick_artist, strum_text, chord_status_text, stats_text, last_played_text] + 
            finger_circles + timeline_artists)

# Animation
ani = FuncAnimation(fig, update, interval=50, blit=False, cache_frame_data=False)

# Print help
print("=" * 70)
print("🎸 GUITAR CHORD PLAYER VISUALIZER + AUDIO 🎸")
print("=" * 70)
print("Listening for:")
print("  1. Touch sensor events (ESP #1) → Updates chord (1-5)")
print("  2. Strum events (ESP #2) → Plays mapped audio")
print("")
print("Audio mapping (files 1.mp3 to 10.mp3):")
for k, v in STRUM_AUDIO_MAP.items():
    status = "✓" if k in sound_cache else "✗"
    print(f"  {status} chord={k[0]} direction={k[1]} -> {os.path.basename(v)}")
print("")
print(f"Active audio channels: {pygame.mixer.get_num_channels()}")
print("Ready to rock! 🎸")
print("=" * 70)

# Show the visualization window
try:
    plt.show()
except KeyboardInterrupt:
    pass
finally:
    print("\nStopping audio...")
    pygame.mixer.stop()
    pygame.quit()
    try:
        sock.close()
    except Exception:
        pass
    print("Exited cleanly.")
