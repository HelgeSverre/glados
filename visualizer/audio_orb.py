#!/usr/bin/env python3
"""
GLaDOS Audio-Reactive Orb Visualizer

A pulsing energy orb that reacts to audio amplitude and frequency,
styled after Portal/HAL 9000 aesthetics.

Usage:
    python audio_orb.py [audio_file.wav]

    Or run without arguments to watch for glados-tts/output.wav
"""

import pygame
import numpy as np
import math
import sys
import os
import time
from pathlib import Path

try:
    from scipy.io import wavfile
    from scipy.fft import rfft, rfftfreq
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

# Configuration
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 800
FPS = 60

# Portal color palette
PORTAL_ORANGE = (255, 160, 50)
PORTAL_ORANGE_BRIGHT = (255, 200, 100)
PORTAL_ORANGE_DIM = (180, 100, 30)
PORTAL_BLUE = (100, 180, 255)
PORTAL_BLUE_BRIGHT = (150, 210, 255)
BACKGROUND = (10, 10, 15)
RING_COLOR = (40, 40, 45)


class AudioAnalyzer:
    """Analyzes audio file and provides amplitude/frequency data."""

    def __init__(self, audio_path: str = None):
        self.audio_path = audio_path
        self.samples = None
        self.sample_rate = 22050
        self.duration = 0
        self.amplitude_envelope = None
        self.frequency_bands = None  # Low, mid, high frequency energy per frame
        self.is_playing = False
        self.start_time = 0

        if audio_path and os.path.exists(audio_path):
            self.load_audio(audio_path)

    def load_audio(self, audio_path: str):
        """Load audio file and compute amplitude/frequency envelopes."""
        self.audio_path = audio_path

        if HAS_SCIPY:
            self.sample_rate, samples = wavfile.read(audio_path)
            if samples.dtype == np.int16:
                self.samples = samples.astype(np.float32) / 32768.0
            elif samples.dtype == np.int32:
                self.samples = samples.astype(np.float32) / 2147483648.0
            else:
                self.samples = samples.astype(np.float32)
        else:
            pygame.mixer.init(frequency=22050)
            sound = pygame.mixer.Sound(audio_path)
            self.samples = pygame.sndarray.array(sound).astype(np.float32) / 32768.0
            self.sample_rate = 22050

        # Handle stereo
        if len(self.samples.shape) > 1:
            self.samples = self.samples.mean(axis=1)

        self.duration = len(self.samples) / self.sample_rate

        # Compute per-frame data
        window_size = int(self.sample_rate / FPS)
        num_windows = len(self.samples) // window_size

        self.amplitude_envelope = np.zeros(num_windows)
        self.frequency_bands = np.zeros((num_windows, 3))  # low, mid, high

        for i in range(num_windows):
            start = i * window_size
            end = start + window_size
            window = self.samples[start:end]

            # RMS amplitude
            self.amplitude_envelope[i] = np.sqrt(np.mean(window ** 2))

            # FFT for frequency bands (if scipy available)
            if HAS_SCIPY and len(window) > 0:
                fft_result = np.abs(rfft(window))
                freqs = rfftfreq(len(window), 1 / self.sample_rate)

                # Split into bands: low (0-300Hz), mid (300-2000Hz), high (2000Hz+)
                low_mask = freqs < 300
                mid_mask = (freqs >= 300) & (freqs < 2000)
                high_mask = freqs >= 2000

                self.frequency_bands[i, 0] = np.mean(fft_result[low_mask]) if low_mask.any() else 0
                self.frequency_bands[i, 1] = np.mean(fft_result[mid_mask]) if mid_mask.any() else 0
                self.frequency_bands[i, 2] = np.mean(fft_result[high_mask]) if high_mask.any() else 0

        # Normalize
        max_amp = self.amplitude_envelope.max()
        if max_amp > 0:
            self.amplitude_envelope /= max_amp

        for band in range(3):
            max_band = self.frequency_bands[:, band].max()
            if max_band > 0:
                self.frequency_bands[:, band] /= max_band

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

    def get_current_frame(self) -> int:
        """Get current frame index."""
        if not self.is_playing or self.amplitude_envelope is None:
            return -1
        elapsed = time.time() - self.start_time
        if elapsed >= self.duration:
            self.is_playing = False
            return -1
        return min(int((elapsed / self.duration) * len(self.amplitude_envelope)),
                   len(self.amplitude_envelope) - 1)

    def get_current_amplitude(self) -> float:
        """Get amplitude at current playback position."""
        frame = self.get_current_frame()
        return self.amplitude_envelope[frame] if frame >= 0 else 0.0

    def get_current_bands(self) -> tuple:
        """Get frequency bands at current position (low, mid, high)."""
        frame = self.get_current_frame()
        if frame >= 0:
            return tuple(self.frequency_bands[frame])
        return (0.0, 0.0, 0.0)

    def is_finished(self) -> bool:
        return not self.is_playing


class EnergyOrb:
    """A pulsing energy orb with layers of glow."""

    def __init__(self, center_x: int, center_y: int, base_radius: int):
        self.center_x = center_x
        self.center_y = center_y
        self.base_radius = base_radius

        # Animation state
        self.current_radius = base_radius
        self.target_radius = base_radius
        self.glow_intensity = 0.3
        self.color_shift = 0.0  # 0 = orange, 1 = blue
        self.rotation = 0.0
        self.pulse_phase = 0.0

        # Particles
        self.particles = []
        self._init_particles()

        # Smoothing
        self.radius_velocity = 0.0

    def _init_particles(self):
        """Initialize orbiting particles."""
        for i in range(12):
            angle = i * (2 * math.pi / 12)
            self.particles.append({
                'angle': angle,
                'radius': self.base_radius * 1.5,
                'speed': 0.5 + (i % 3) * 0.3,
                'size': 3 + (i % 4),
                'phase': i * 0.5
            })

    def set_audio_data(self, amplitude: float, bands: tuple):
        """Update orb based on audio data."""
        low, mid, high = bands

        # Radius responds to overall amplitude
        self.target_radius = self.base_radius * (0.8 + amplitude * 0.6)

        # Glow intensity from amplitude
        self.glow_intensity = 0.2 + amplitude * 0.8

        # Color shift based on frequency balance
        # More high frequencies = more blue, more low = more orange
        if low + high > 0:
            self.color_shift = high / (low + high + 0.001)
        else:
            self.color_shift = 0.0

    def update(self, dt: float):
        """Update orb animation."""
        # Smooth radius changes
        force = (self.target_radius - self.current_radius) * 20
        self.radius_velocity += force * dt
        self.radius_velocity *= 0.85
        self.current_radius += self.radius_velocity * dt

        # Continuous rotation and pulse
        self.rotation += dt * 0.5
        self.pulse_phase += dt * 3

        # Update particles
        for p in self.particles:
            p['angle'] += p['speed'] * dt * (1 + self.glow_intensity)
            p['radius'] = self.base_radius * (1.3 + 0.3 * math.sin(self.pulse_phase + p['phase']))

    def _lerp_color(self, c1: tuple, c2: tuple, t: float) -> tuple:
        """Linear interpolate between two colors."""
        return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))

    def draw(self, surface: pygame.Surface):
        """Draw the energy orb with all effects."""
        center = (self.center_x, self.center_y)

        # Get current color based on shift
        main_color = self._lerp_color(PORTAL_ORANGE, PORTAL_BLUE, self.color_shift)
        bright_color = self._lerp_color(PORTAL_ORANGE_BRIGHT, PORTAL_BLUE_BRIGHT, self.color_shift)

        # Draw outer glow rings
        self._draw_glow_rings(surface, main_color)

        # Draw particles
        self._draw_particles(surface, main_color)

        # Draw main orb layers
        self._draw_orb_layers(surface, main_color, bright_color)

        # Draw inner detail
        self._draw_inner_detail(surface, bright_color)

    def _draw_glow_rings(self, surface: pygame.Surface, color: tuple):
        """Draw expanding glow rings."""
        num_rings = 5
        for i in range(num_rings):
            ring_radius = int(self.current_radius * (1.5 + i * 0.4))
            alpha = int(40 * self.glow_intensity * (num_rings - i) / num_rings)

            # Pulsing effect
            pulse = math.sin(self.pulse_phase + i * 0.5) * 0.3 + 0.7
            ring_radius = int(ring_radius * pulse)

            glow_surf = pygame.Surface((ring_radius * 2 + 20, ring_radius * 2 + 20), pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (*color, alpha),
                             (ring_radius + 10, ring_radius + 10), ring_radius, 3)
            surface.blit(glow_surf,
                        (self.center_x - ring_radius - 10, self.center_y - ring_radius - 10),
                        special_flags=pygame.BLEND_RGBA_ADD)

    def _draw_particles(self, surface: pygame.Surface, color: tuple):
        """Draw orbiting particles."""
        for p in self.particles:
            x = self.center_x + int(p['radius'] * math.cos(p['angle']))
            y = self.center_y + int(p['radius'] * math.sin(p['angle']))
            size = int(p['size'] * (0.5 + self.glow_intensity))

            # Particle glow
            glow_size = size * 3
            glow_surf = pygame.Surface((glow_size * 2, glow_size * 2), pygame.SRCALPHA)
            alpha = int(100 * self.glow_intensity)
            pygame.draw.circle(glow_surf, (*color, alpha), (glow_size, glow_size), glow_size)
            surface.blit(glow_surf, (x - glow_size, y - glow_size),
                        special_flags=pygame.BLEND_RGBA_ADD)

            # Particle core
            pygame.draw.circle(surface, color, (x, y), size)

    def _draw_orb_layers(self, surface: pygame.Surface, color: tuple, bright_color: tuple):
        """Draw the main orb with multiple glow layers."""
        # Outer glow
        for i in range(8, 0, -1):
            glow_radius = int(self.current_radius * (1 + i * 0.15))
            alpha = int(30 * self.glow_intensity * (9 - i) / 8)
            glow_surf = pygame.Surface((glow_radius * 2 + 10, glow_radius * 2 + 10), pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (*color, alpha),
                             (glow_radius + 5, glow_radius + 5), glow_radius)
            surface.blit(glow_surf,
                        (self.center_x - glow_radius - 5, self.center_y - glow_radius - 5),
                        special_flags=pygame.BLEND_RGBA_ADD)

        # Main orb body
        pygame.draw.circle(surface, color, (self.center_x, self.center_y),
                          int(self.current_radius))

        # Inner bright core
        core_radius = int(self.current_radius * 0.6)
        pygame.draw.circle(surface, bright_color, (self.center_x, self.center_y), core_radius)

        # Hot center
        center_radius = int(self.current_radius * 0.3)
        white_intensity = int(200 + 55 * self.glow_intensity)
        pygame.draw.circle(surface, (white_intensity, white_intensity, white_intensity),
                          (self.center_x, self.center_y), center_radius)

    def _draw_inner_detail(self, surface: pygame.Surface, color: tuple):
        """Draw rotating inner pattern."""
        num_rays = 6
        inner_r = self.current_radius * 0.4
        outer_r = self.current_radius * 0.8

        for i in range(num_rays):
            angle = self.rotation + i * (2 * math.pi / num_rays)
            inner_x = self.center_x + int(inner_r * math.cos(angle))
            inner_y = self.center_y + int(inner_r * math.sin(angle))
            outer_x = self.center_x + int(outer_r * math.cos(angle))
            outer_y = self.center_y + int(outer_r * math.sin(angle))

            alpha = int(100 * self.glow_intensity)
            # We'll just draw white lines for simplicity
            pygame.draw.line(surface, (255, 255, 255, alpha),
                           (inner_x, inner_y), (outer_x, outer_y), 2)


class OrbVisualizer:
    """Main orb visualizer application."""

    def __init__(self, audio_path: str = None):
        pygame.init()
        pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)

        # Position on second monitor if available
        os.environ['SDL_VIDEO_WINDOW_POS'] = '1920,0'

        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("GLaDOS - Energy Core Visualization")

        self.clock = pygame.time.Clock()
        self.running = True

        # Components
        self.orb = EnergyOrb(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2, 120)
        self.audio = AudioAnalyzer(audio_path)

        # State
        self.idle_time = 0
        self.last_audio_mtime = 0
        self.watch_path = None

        # Font
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
                    if self.audio.audio_path:
                        self.audio.play()
            elif event.type == pygame.DROPFILE:
                if event.file.endswith('.wav'):
                    print(f"Loading dropped file: {event.file}")
                    self.audio.load_audio(event.file)
                    self.audio.play()

    def update(self, dt: float):
        """Update visualization state."""
        self.check_audio_file()

        if self.audio.is_playing:
            amplitude = self.audio.get_current_amplitude()
            bands = self.audio.get_current_bands()
            self.orb.set_audio_data(amplitude, bands)
            self.idle_time = 0
        else:
            # Idle animation
            self.idle_time += dt
            idle_amp = 0.2 + 0.1 * math.sin(self.idle_time * 1.5)
            idle_bands = (0.3, 0.3, 0.3)
            self.orb.set_audio_data(idle_amp, idle_bands)

        self.orb.update(dt)

    def draw(self):
        """Draw the visualization."""
        self.screen.fill(BACKGROUND)

        # Draw decorative outer ring
        pygame.draw.circle(self.screen, RING_COLOR,
                          (WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2), 300, 4)
        pygame.draw.circle(self.screen, RING_COLOR,
                          (WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2), 350, 2)

        # Draw orb
        self.orb.draw(self.screen)

        # Status text
        status = "STANDBY" if not self.audio.is_playing else "ACTIVE"
        color = PORTAL_ORANGE if self.audio.is_playing else (100, 100, 100)
        status_text = self.font.render(f"[ {status} ]", True, color)
        status_rect = status_text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT - 50))
        self.screen.blit(status_text, status_rect)

        # Title
        title = self.font.render("APERTURE SCIENCE ENERGY CORE", True, (80, 80, 85))
        title_rect = title.get_rect(center=(WINDOW_WIDTH // 2, 40))
        self.screen.blit(title, title_rect)

        pygame.display.flip()

    def run(self):
        """Main loop."""
        print("GLaDOS Audio-Reactive Orb Visualizer")
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
    audio_path = None
    watch_path = None

    if len(sys.argv) > 1:
        audio_path = sys.argv[1]
        if not os.path.exists(audio_path):
            print(f"Warning: Audio file not found: {audio_path}")
            audio_path = None
    else:
        default_output = Path(__file__).parent.parent / "glados-tts" / "output.wav"
        if default_output.exists():
            audio_path = str(default_output)
        watch_path = str(default_output)

    viz = OrbVisualizer(audio_path)

    if watch_path:
        print(f"Watching for audio: {watch_path}")
        viz.watch_audio_file(watch_path)

    viz.run()


if __name__ == "__main__":
    main()
