import socket
import json
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.patches import FancyArrow, Circle, Rectangle
from collections import deque
import time

# UDP Configuration
UDP_IP = "0.0.0.0"
UDP_PORT = 5005

# Create UDP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))
sock.settimeout(0.01)

print(f"Listening for MPU6050 data on {UDP_IP}:{UDP_PORT}")

# Strum detection parameters
UP_STRUM_THRESHOLD = 7.5    # m/s² threshold for UP strum
DOWN_STRUM_THRESHOLD = 7.5  # m/s² threshold for DOWN strum
STRUM_COOLDOWN = 0.15       # seconds between strums (reduced for faster response)
MIN_STRUM_DURATION = 0.015  # minimum duration to count as strum (reduced)

# Data storage
MAX_HISTORY = 200  # Keep 1 second of history at 200Hz
time_history = deque(maxlen=MAX_HISTORY)
accel_y_history = deque(maxlen=MAX_HISTORY)  # Y-axis for up/down motion
accel_magnitude_history = deque(maxlen=MAX_HISTORY)

# Strum detection state
last_strum_time = 0
current_strum_direction = None
strum_start_time = None
strum_peak_accel = 0

# Visual feedback state
strum_display_until = 0  # Time until which to display the strum
STRUM_DISPLAY_DURATION = 0.5  # Show strum for 500ms

# Strum counters
up_strum_count = 0
down_strum_count = 0
total_strums = 0

# Recent strums for visualization (keep last 10)
recent_strums = deque(maxlen=10)

# Packet counter
packet_count = 0
start_time = None

# Create figure with multiple subplots
fig = plt.figure(figsize=(16, 10))
gs = fig.add_gridspec(3, 2, hspace=0.3, wspace=0.3)

# Subplot 1: Real-time acceleration (Y-axis for strum detection)
ax_accel = fig.add_subplot(gs[0, :])
line_accel, = ax_accel.plot([], [], 'b-', linewidth=2, label='Y-Axis Accel')
ax_accel.axhline(y=UP_STRUM_THRESHOLD, color='r', linestyle='--', linewidth=2, label=f'Up Threshold (+{UP_STRUM_THRESHOLD})')
ax_accel.axhline(y=-DOWN_STRUM_THRESHOLD, color='g', linestyle='--', linewidth=2, label=f'Down Threshold (-{DOWN_STRUM_THRESHOLD})')
ax_accel.axhline(y=0, color='k', linestyle='-', alpha=0.3, linewidth=0.5)
ax_accel.set_xlabel('Time (s)')
ax_accel.set_ylabel('Acceleration (m/s²)')
ax_accel.set_title('Guitar Strum Detection - Y-Axis Acceleration')
ax_accel.legend(loc='upper right')
ax_accel.grid(True, alpha=0.3)
ax_accel.set_xlim(0, 1)
ax_accel.set_ylim(-50, 50)

# Subplot 2: Strum visualization (guitar with pick)
ax_strum = fig.add_subplot(gs[1, 0])
ax_strum.set_xlim(-1, 1)
ax_strum.set_ylim(-1.5, 1.5)
ax_strum.set_aspect('equal')
ax_strum.axis('off')
ax_strum.set_title('Current Strum Direction', fontsize=14, fontweight='bold')

# Draw guitar strings
string_y_positions = np.linspace(-0.8, 0.8, 6)
for y in string_y_positions:
    ax_strum.plot([-0.6, 0.6], [y, y], 'gray', linewidth=2, alpha=0.6)

# Pick (triangle pointing in strum direction)
pick_artist = ax_strum.add_patch(Circle((0, 0), 0.15, color='orange', alpha=0.8))
pick_arrow = ax_strum.add_patch(FancyArrow(0, 0, 0, 0.5, width=0.2, head_width=0.3, 
                                            head_length=0.2, color='red', alpha=0))

# Strum indicator text
strum_text = ax_strum.text(0, -1.2, 'Waiting...', ha='center', fontsize=16, 
                           fontweight='bold', color='gray')

# Subplot 3: Strum statistics
ax_stats = fig.add_subplot(gs[1, 1])
ax_stats.set_xlim(0, 10)
ax_stats.set_ylim(0, 10)
ax_stats.axis('off')
ax_stats.set_title('Strum Statistics', fontsize=14, fontweight='bold')

stats_text = ax_stats.text(5, 5, '', ha='center', va='center', fontsize=12, 
                           family='monospace',
                           bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8))

# Subplot 4: Recent strums timeline
ax_timeline = fig.add_subplot(gs[2, :])
ax_timeline.set_xlim(0, 10)
ax_timeline.set_ylim(-1, 1)
ax_timeline.set_xlabel('Recent Strums (newest on right)')
ax_timeline.set_title('Strum History (Last 10 Strums)')
ax_timeline.set_yticks([])
ax_timeline.grid(True, axis='x', alpha=0.3)

# Timeline markers (will be updated)
timeline_artists = []

def detect_strum(accel_y, current_time):
    """Detect strum based on Y-axis acceleration (both positive and negative values trigger detection)"""
    global last_strum_time, current_strum_direction, strum_start_time, strum_peak_accel
    global up_strum_count, down_strum_count, total_strums
    
    # Check cooldown
    if current_time - last_strum_time < STRUM_COOLDOWN:
        return None
    
    strum_detected = None
    
    # Detect UP strum (positive Y acceleration - moving up with quick snap motion)
    if accel_y > UP_STRUM_THRESHOLD:
        if current_strum_direction != 'UP':
            current_strum_direction = 'UP'
            strum_start_time = current_time
            strum_peak_accel = accel_y
        else:
            strum_peak_accel = max(strum_peak_accel, accel_y)
    
    # Detect DOWN strum (negative Y acceleration - moving down)
    elif accel_y < -DOWN_STRUM_THRESHOLD:
        if current_strum_direction != 'DOWN':
            current_strum_direction = 'DOWN'
            strum_start_time = current_time
            strum_peak_accel = abs(accel_y)
        else:
            strum_peak_accel = max(strum_peak_accel, abs(accel_y))
    
    # Strum ended (acceleration below threshold)
    else:
        if current_strum_direction is not None and strum_start_time is not None:
            strum_duration = current_time - strum_start_time
            
            # Valid strum if duration is sufficient
            if strum_duration >= MIN_STRUM_DURATION:
                strum_detected = {
                    'direction': current_strum_direction,
                    'time': current_time,
                    'peak_accel': strum_peak_accel,
                    'duration': strum_duration
                }
                
                # Update counters
                if current_strum_direction == 'UP':
                    up_strum_count += 1
                else:
                    down_strum_count += 1
                total_strums += 1
                
                # Update last strum time
                last_strum_time = current_time
                
                # Add to recent strums
                recent_strums.append(strum_detected)
                
                # Debug output
                print(f"🎸 {strum_detected['direction']} STRUM! Peak: {strum_detected['peak_accel']:.1f} m/s², Duration: {strum_duration*1000:.1f}ms")
        
        # Reset state
        current_strum_direction = None
        strum_start_time = None
        strum_peak_accel = 0
    
    return strum_detected

def update_strum_visualization(strum_info, current_time):
    """Update the visual representation of current strum with extended display"""
    global strum_display_until
    
    # Check if we should still display a previous strum
    if current_time < strum_display_until:
        # Continue displaying the last strum
        return
    
    if strum_info is None:
        # No active strum
        pick_arrow.set_alpha(0)
        strum_text.set_text('Waiting...')
        strum_text.set_color('gray')
        pick_artist.set_color('orange')
    else:
        direction = strum_info['direction']
        peak = strum_info['peak_accel']
        
        # Set display duration - show the strum for longer
        strum_display_until = current_time + STRUM_DISPLAY_DURATION
        
        # Update arrow
        if direction == 'UP':
            pick_arrow.set_data(x=0, y=0, dx=0, dy=0.5)
            pick_arrow.set_color('red')
            strum_text.set_text('⬆ UP STRUM! ⬆')
            strum_text.set_color('red')
            pick_artist.set_color('red')
        else:
            pick_arrow.set_data(x=0, y=0, dx=0, dy=-0.5)
            pick_arrow.set_color('green')
            strum_text.set_text('⬇ DOWN STRUM! ⬇')
            strum_text.set_color('green')
            pick_artist.set_color('green')
        
        pick_arrow.set_alpha(0.8)

def update_timeline():
    """Update the timeline of recent strums"""
    # Clear previous timeline artists
    for artist in timeline_artists:
        artist.remove()
    timeline_artists.clear()
    
    # Draw recent strums
    num_strums = len(recent_strums)
    for i, strum in enumerate(recent_strums):
        x_pos = i + 0.5
        if strum['direction'] == 'UP':
            marker = ax_timeline.add_patch(
                FancyArrow(x_pos, -0.5, 0, 0.4, width=0.3, head_width=0.5, 
                          head_length=0.2, color='red', alpha=0.7)
            )
            timeline_artists.append(marker)
        else:
            marker = ax_timeline.add_patch(
                FancyArrow(x_pos, 0.5, 0, -0.4, width=0.3, head_width=0.5, 
                          head_length=0.2, color='green', alpha=0.7)
            )
            timeline_artists.append(marker)

def update(frame):
    global packet_count, start_time
    
    # Read UDP packets
    packets_this_frame = 0
    latest_strum = None
    current_time_val = 0
    
    while packets_this_frame < 10:
        try:
            data, addr = sock.recvfrom(1024)
            packet_count += 1
            packets_this_frame += 1
            
            # Parse JSON
            json_data = json.loads(data.decode('utf-8'))
            
            # Get time
            t = json_data['t'] / 1000.0
            if start_time is None:
                start_time = t
            t_rel = t - start_time
            current_time_val = t_rel
            
            # Get Y-axis acceleration (up/down motion)
            accel_y = json_data['ay']
            
            # Calculate magnitude
            accel_mag = np.sqrt(json_data['ax']**2 + json_data['ay']**2 + json_data['az']**2)
            
            # Store data
            time_history.append(t_rel)
            accel_y_history.append(accel_y)
            accel_magnitude_history.append(accel_mag)
            
            # Detect strum
            strum = detect_strum(accel_y, t_rel)
            if strum is not None:
                latest_strum = strum
            
        except socket.timeout:
            break
        except (json.JSONDecodeError, KeyError) as e:
            break
    
    # Update acceleration plot
    if len(time_history) > 0:
        times = np.array(time_history)
        accels = np.array(accel_y_history)
        
        line_accel.set_data(times, accels)
        
        # Auto-scale x-axis
        if times[-1] > 1:
            ax_accel.set_xlim(times[-1] - 1, times[-1] + 0.1)
    
    # Update strum visualization with extended display
    if latest_strum is not None:
        update_strum_visualization(latest_strum, current_time_val)
    elif current_strum_direction is None:
        update_strum_visualization(None, current_time_val)
    
    # Update statistics
    if total_strums > 0:
        up_pct = (up_strum_count / total_strums) * 100
        down_pct = (down_strum_count / total_strums) * 100
    else:
        up_pct = down_pct = 0
    
    stats_text.set_text(
        f'╔═══════════════════╗\n'
        f'║  STRUM COUNTER    ║\n'
        f'╠═══════════════════╣\n'
        f'║  ⬆ UP:    {up_strum_count:4d}    ║\n'
        f'║  ⬇ DOWN:  {down_strum_count:4d}    ║\n'
        f'║  TOTAL:   {total_strums:4d}    ║\n'
        f'╠═══════════════════╣\n'
        f'║  UP:   {up_pct:5.1f}%    ║\n'
        f'║  DOWN: {down_pct:5.1f}%    ║\n'
        f'╚═══════════════════╝'
    )
    
    # Update timeline
    update_timeline()
    
    return [line_accel, pick_artist, pick_arrow, strum_text, stats_text] + timeline_artists

# Create animation
ani = FuncAnimation(fig, update, interval=50, blit=False, cache_frame_data=False)

print("=" * 70)
print("🎸 GUITAR STRUM DETECTOR 🎸")
print("=" * 70)
print("SENSOR ORIENTATION & MOVEMENT:")
print("")
print("┌─────────────────────────────────────────────────────────────┐")
print("│  MPU6050 Sensor Orientation (looking at component side):    │")
print("│                                                              │")
print("│         ┌─────────────┐                                     │")
print("│         │   MPU6050   │                                     │")
print("│         │             │                                     │")
print("│         │      Y↑     │  ← Y-axis points UP                │")
print("│         │      |      │                                     │")
print("│         │  X←──●      │  ← Dot = center/chip                │")
print("│         │             │                                     │")
print("│         │   (Z out)   │  ← Z-axis points toward you        │")
print("│         └─────────────┘                                     │")
print("│                                                              │")
print("└─────────────────────────────────────────────────────────────┘")
print("")
print("HOW TO STRUM:")
print("")
print("  🔴 UP STRUM:")
print("     → Move sensor UPWARD (along Y-axis) with a QUICK SNAP")
print("     → The faster the upward motion, the better detection")
print("     → Think: flicking upward sharply")
print("     → Need quick acceleration (>7.5 m/s²)")
print("")
print("  🟢 DOWN STRUM:")
print("     → Move sensor DOWNWARD (against Y-axis)")
print("     → Quick downward motion")
print("     → Already working well for you!")
print("")
print("TIPS:")
print("  • Hold sensor firmly but allow wrist movement")
print("  • Use SHARP, QUICK motions (not slow/smooth)")
print("  • Watch the graph - spikes should cross the thresholds")
print("  • If UP isn't detecting, try FASTER upward snaps")
print("  • The motion should feel like a guitar strum - quick & crisp")
print("")
print(f"Thresholds: UP={UP_STRUM_THRESHOLD} m/s², DOWN={DOWN_STRUM_THRESHOLD} m/s²")
print(f"Display Duration: {STRUM_DISPLAY_DURATION}s")
print("=" * 70)

plt.show()

# Cleanup
sock.close()
print(f"\n📊 Session Summary:")
print(f"   Total packets: {packet_count}")
print(f"   Up strums: {up_strum_count}")
print(f"   Down strums: {down_strum_count}")
print(f"   Total strums: {total_strums}")
