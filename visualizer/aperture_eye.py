#!/usr/bin/env python3
"""
GLaDOS Aperture Eye Visualizer

A mechanical iris/aperture animation that reacts to audio,
styled after the Portal aesthetic with orange glow effects.

Usage:
    python aperture_eye.py [audio_file.wav]

    Or run without arguments to watch for glados-tts/output.wav
"""

import pygame
import numpy as np
import math
import sys
import os
import time
from pathlib import Path

# Optional: scipy for better audio loading
try:
    from scipy.io import wavfile
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

# Configuration
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 800
FPS = 60

# Portal color palette
PORTAL_ORANGE = (255, 160, 50)
PORTAL_ORANGE_GLOW = (255, 180, 80)
PORTAL_ORANGE_DIM = (180, 100, 30)
PORTAL_BLUE = (100, 180, 255)
APERTURE_GRAY = (60, 60, 65)
APERTURE_DARK = (30, 30, 35)
APERTURE_LIGHT = (90, 90, 95)
BACKGROUND = (15, 15, 18)

# Iris configuration
NUM_BLADES = 8
BLADE_OVERLAP = 0.15  # How much blades overlap when closed


class AudioAnalyzer:
    """Analyzes audio file and provides amplitude data for visualization."""

    def __init__(self, audio_path: str = None):
        self.audio_path = audio_path
        self.samples = None
        self.sample_rate = 22050
        self.duration = 0
        self.amplitude_envelope = None
        self.current_position = 0
        self.is_playing = False
        self.start_time = 0

        if audio_path and os.path.exists(audio_path):
            self.load_audio(audio_path)

    def load_audio(self, audio_path: str):
        """Load audio file and compute amplitude envelope."""
        self.audio_path = audio_path

        if HAS_SCIPY:
            self.sample_rate, samples = wavfile.read(audio_path)
            # Convert to float and normalize
            if samples.dtype == np.int16:
                self.samples = samples.astype(np.float32) / 32768.0
            elif samples.dtype == np.int32:
                self.samples = samples.astype(np.float32) / 2147483648.0
            else:
                self.samples = samples.astype(np.float32)
        else:
            # Fallback: use pygame's audio loading
            pygame.mixer.init(frequency=22050)
            sound = pygame.mixer.Sound(audio_path)
            # Get raw samples (this is a workaround)
            self.samples = pygame.sndarray.array(sound).astype(np.float32) / 32768.0
            self.sample_rate = 22050

        # Handle stereo
        if len(self.samples.shape) > 1:
            self.samples = self.samples.mean(axis=1)

        self.duration = len(self.samples) / self.sample_rate

        # Compute amplitude envelope (RMS over windows)
        window_size = int(self.sample_rate / FPS)  # One window per frame
        num_windows = len(self.samples) // window_size

        self.amplitude_envelope = np.zeros(num_windows)
        for i in range(num_windows):
            start = i * window_size
            end = start + window_size
            window = self.samples[start:end]
            self.amplitude_envelope[i] = np.sqrt(np.mean(window ** 2))

        # Normalize envelope
        max_amp = self.amplitude_envelope.max()
        if max_amp > 0:
            self.amplitude_envelope = self.amplitude_envelope / max_amp

        print(f"Loaded audio: {self.duration:.2f}s, {self.sample_rate}Hz, {num_windows} frames")

    def play(self):
        """Start audio playback."""
        if self.audio_path and os.path.exists(self.audio_path):
            pygame.mixer.music.load(self.audio_path)
            pygame.mixer.music.play()
            self.is_playing = True
            self.start_time = time.time()

    def stop(self):
        """Stop audio playback."""
        pygame.mixer.music.stop()
        self.is_playing = False

    def get_current_amplitude(self) -> float:
        """Get amplitude at current playback position."""
        if not self.is_playing or self.amplitude_envelope is None:
            return 0.0

        elapsed = time.time() - self.start_time
        if elapsed >= self.duration:
            self.is_playing = False
            return 0.0

        frame_idx = int((elapsed / self.duration) * len(self.amplitude_envelope))
        frame_idx = min(frame_idx, len(self.amplitude_envelope) - 1)

        return self.amplitude_envelope[frame_idx]

    def is_finished(self) -> bool:
        """Check if playback is finished."""
        if not self.is_playing:
            return True
        elapsed = time.time() - self.start_time
        return elapsed >= self.duration


class ApertureIris:
    """Mechanical aperture iris with blades that open/close."""

    def __init__(self, center_x: int, center_y: int, radius: int):
        self.center_x = center_x
        self.center_y = center_y
        self.radius = radius
        self.inner_radius = radius * 0.15  # Minimum opening
        self.current_opening = 0.0  # 0 = closed, 1 = fully open
        self.target_opening = 0.0
        self.rotation = 0.0  # Slow rotation of the whole iris

        # Smoothing
        self.opening_velocity = 0.0
        self.spring_stiffness = 15.0
        self.damping = 0.7

    def set_target_opening(self, target: float):
        """Set target opening (0-1)."""
        self.target_opening = max(0.0, min(1.0, target))

    def update(self, dt: float):
        """Update iris animation with spring physics."""
        # Spring physics for smooth opening/closing
        force = (self.target_opening - self.current_opening) * self.spring_stiffness
        self.opening_velocity += force * dt
        self.opening_velocity *= (1.0 - self.damping * dt * 10)
        self.current_opening += self.opening_velocity * dt
        self.current_opening = max(0.0, min(1.0, self.current_opening))

        # Slow rotation
        self.rotation += dt * 0.1

    def draw(self, surface: pygame.Surface, glow_intensity: float = 0.5):
        """Draw the mechanical aperture iris."""
        # Calculate current aperture size
        opening_radius = self.inner_radius + (self.radius * 0.6 - self.inner_radius) * self.current_opening

        # Draw outer ring
        pygame.draw.circle(surface, APERTURE_LIGHT,
                          (self.center_x, self.center_y),
                          self.radius + 10, 8)
        pygame.draw.circle(surface, APERTURE_DARK,
                          (self.center_x, self.center_y),
                          self.radius + 5, 3)

        # Draw blades
        for i in range(NUM_BLADES):
            self._draw_blade(surface, i, opening_radius)

        # Draw center glow
        self._draw_center_glow(surface, opening_radius, glow_intensity)

        # Draw mechanical details
        self._draw_mechanical_details(surface)

    def _draw_blade(self, surface: pygame.Surface, blade_index: int, opening_radius: float):
        """Draw a single iris blade."""
        angle_step = 2 * math.pi / NUM_BLADES
        base_angle = blade_index * angle_step + self.rotation

        # Blade shape - curved trapezoid
        # The blade rotates to open/close
        blade_rotation = (1.0 - self.current_opening) * angle_step * 0.4

        # Outer points
        outer_angle1 = base_angle - angle_step * (0.5 + BLADE_OVERLAP) + blade_rotation
        outer_angle2 = base_angle + angle_step * (0.5 + BLADE_OVERLAP) + blade_rotation

        # Inner points (these determine the aperture opening)
        inner_angle1 = base_angle - angle_step * 0.3 + blade_rotation * 2
        inner_angle2 = base_angle + angle_step * 0.3 + blade_rotation * 2

        outer_r = self.radius
        inner_r = opening_radius

        points = [
            (self.center_x + outer_r * math.cos(outer_angle1),
             self.center_y + outer_r * math.sin(outer_angle1)),
            (self.center_x + outer_r * math.cos(outer_angle2),
             self.center_y + outer_r * math.sin(outer_angle2)),
            (self.center_x + inner_r * math.cos(inner_angle2),
             self.center_y + inner_r * math.sin(inner_angle2)),
            (self.center_x + inner_r * math.cos(inner_angle1),
             self.center_y + inner_r * math.sin(inner_angle1)),
        ]

        # Draw blade with gradient effect (lighter edge)
        pygame.draw.polygon(surface, APERTURE_GRAY, points)
        pygame.draw.polygon(surface, APERTURE_LIGHT, points, 2)

        # Add highlight line on blade
        mid_angle = base_angle + blade_rotation * 1.5
        highlight_start = (
            self.center_x + (inner_r + 10) * math.cos(mid_angle),
            self.center_y + (inner_r + 10) * math.sin(mid_angle)
        )
        highlight_end = (
            self.center_x + (outer_r - 20) * math.cos(mid_angle),
            self.center_y + (outer_r - 20) * math.sin(mid_angle)
        )
        pygame.draw.line(surface, APERTURE_LIGHT, highlight_start, highlight_end, 1)

    def _draw_center_glow(self, surface: pygame.Surface, opening_radius: float, intensity: float):
        """Draw the glowing center eye."""
        # Create glow layers
        glow_color = (
            int(PORTAL_ORANGE[0] * intensity),
            int(PORTAL_ORANGE[1] * intensity),
            int(PORTAL_ORANGE[2] * intensity)
        )

        # Multiple layers for glow effect
        for i in range(5, 0, -1):
            glow_radius = int(opening_radius * (0.5 + i * 0.15))
            alpha = int(50 * intensity * (6 - i) / 5)
            glow_surf = pygame.Surface((glow_radius * 2, glow_radius * 2), pygame.SRCALPHA)

            glow_col = (*PORTAL_ORANGE_GLOW, alpha)
            pygame.draw.circle(glow_surf, glow_col,
                             (glow_radius, glow_radius), glow_radius)

            surface.blit(glow_surf,
                        (self.center_x - glow_radius, self.center_y - glow_radius),
                        special_flags=pygame.BLEND_RGBA_ADD)

        # Core bright center
        core_radius = int(opening_radius * 0.4)
        if core_radius > 2:
            core_intensity = 0.3 + intensity * 0.7
            core_color = (
                int(255 * core_intensity),
                int(200 * core_intensity),
                int(150 * core_intensity)
            )
            pygame.draw.circle(surface, core_color,
                             (self.center_x, self.center_y), core_radius)

    def _draw_mechanical_details(self, surface: pygame.Surface):
        """Draw mechanical screws and details."""
        # Screws around the outer ring
        num_screws = 12
        screw_radius = self.radius + 15
        for i in range(num_screws):
            angle = i * 2 * math.pi / num_screws + self.rotation * 0.5
            x = int(self.center_x + screw_radius * math.cos(angle))
            y = int(self.center_y + screw_radius * math.sin(angle))
            pygame.draw.circle(surface, APERTURE_DARK, (x, y), 4)
            pygame.draw.circle(surface, APERTURE_LIGHT, (x, y), 4, 1)
            # Screw slot
            pygame.draw.line(surface, APERTURE_DARK,
                           (x - 2, y), (x + 2, y), 1)


class GladosVisualizer:
    """Main visualizer application."""

    def __init__(self, audio_path: str = None):
        pygame.init()
        pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)

        # Try to position on second monitor if available
        # This is a hint - actual behavior depends on OS/window manager
        os.environ['SDL_VIDEO_WINDOW_POS'] = '1920,0'

        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("GLaDOS - Aperture Science Visualization System")

        self.clock = pygame.time.Clock()
        self.running = True

        # Components
        self.iris = ApertureIris(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2, 250)
        self.audio = AudioAnalyzer(audio_path)

        # State
        self.idle_time = 0
        self.last_audio_mtime = 0
        self.watch_path = None

        # Font for status
        self.font = pygame.font.Font(None, 24)

    def watch_audio_file(self, path: str):
        """Watch an audio file for changes and auto-play."""
        self.watch_path = path
        if os.path.exists(path):
            self.last_audio_mtime = os.path.getmtime(path)

    def check_audio_file(self):
        """Check if watched audio file has changed."""
        if not self.watch_path or not os.path.exists(self.watch_path):
            return

        current_mtime = os.path.getmtime(self.watch_path)
        if current_mtime > self.last_audio_mtime:
            self.last_audio_mtime = current_mtime
            # Small delay to ensure file is fully written
            time.sleep(0.1)
            print(f"Audio file updated, loading: {self.watch_path}")
            self.audio.load_audio(self.watch_path)
            self.audio.play()

    def handle_events(self):
        """Handle pygame events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_SPACE:
                    # Replay current audio
                    if self.audio.audio_path:
                        self.audio.play()
                elif event.key == pygame.K_o:
                    # Open file dialog (basic)
                    print("Drop a WAV file onto the window or pass as argument")
            elif event.type == pygame.DROPFILE:
                # Handle drag & drop
                if event.file.endswith('.wav'):
                    print(f"Loading dropped file: {event.file}")
                    self.audio.load_audio(event.file)
                    self.audio.play()

    def update(self, dt: float):
        """Update visualization state."""
        # Check for audio file changes
        self.check_audio_file()

        # Get current audio amplitude
        if self.audio.is_playing:
            amplitude = self.audio.get_current_amplitude()
            # Map amplitude to iris opening (with some boost)
            target_opening = min(1.0, amplitude * 1.5 + 0.1)
            self.idle_time = 0
        else:
            # Idle animation - gentle pulsing
            self.idle_time += dt
            target_opening = 0.15 + 0.05 * math.sin(self.idle_time * 2)

        self.iris.set_target_opening(target_opening)
        self.iris.update(dt)

    def draw(self):
        """Draw the visualization."""
        self.screen.fill(BACKGROUND)

        # Calculate glow intensity
        if self.audio.is_playing:
            glow = 0.3 + self.audio.get_current_amplitude() * 0.7
        else:
            glow = 0.2 + 0.1 * math.sin(self.idle_time * 2)

        # Draw iris
        self.iris.draw(self.screen, glow)

        # Draw status text
        status = "LISTENING" if not self.audio.is_playing else "SPEAKING"
        status_color = PORTAL_ORANGE if self.audio.is_playing else APERTURE_LIGHT
        status_text = self.font.render(f"[ {status} ]", True, status_color)
        status_rect = status_text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT - 50))
        self.screen.blit(status_text, status_rect)

        # Draw Aperture Science logo text
        logo_text = self.font.render("APERTURE SCIENCE", True, APERTURE_LIGHT)
        logo_rect = logo_text.get_rect(center=(WINDOW_WIDTH // 2, 40))
        self.screen.blit(logo_text, logo_rect)

        pygame.display.flip()

    def run(self):
        """Main loop."""
        print("GLaDOS Aperture Eye Visualizer")
        print("=" * 40)
        print("Controls:")
        print("  SPACE - Replay audio")
        print("  ESC   - Quit")
        print("  Drop WAV files onto window to play")
        print("=" * 40)

        if self.audio.audio_path:
            self.audio.play()

        while self.running:
            dt = self.clock.tick(FPS) / 1000.0

            self.handle_events()
            self.update(dt)
            self.draw()

        pygame.quit()


def main():
    # Determine audio path
    audio_path = None
    watch_path = None

    if len(sys.argv) > 1:
        audio_path = sys.argv[1]
        if not os.path.exists(audio_path):
            print(f"Warning: Audio file not found: {audio_path}")
            audio_path = None
    else:
        # Default: watch glados output
        default_output = Path(__file__).parent.parent / "glados-tts" / "output.wav"
        if default_output.exists():
            audio_path = str(default_output)
        watch_path = str(default_output)

    # Create and run visualizer
    viz = GladosVisualizer(audio_path)

    if watch_path:
        print(f"Watching for audio: {watch_path}")
        viz.watch_audio_file(watch_path)

    viz.run()


if __name__ == "__main__":
    main()
