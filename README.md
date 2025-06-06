<a name="readme-top"></a>
[![maintained](https://img.shields.io/maintenance/yes/2025.svg)](#) [![maintainer](https://img.shields.io/badge/maintainer-%20%40fixtse-blue.svg)](https://github.com/fixtse)

<a href='https://ko-fi.com/M4M6P9A5P' target='_blank'><img height='36' style='border:0px;height:36px;' src='https://storage.ko-fi.com/cdn/kofi2.png?v=6' border='0' alt='Buy Me a Coffee at ko-fi.com' /></a>

# Home Assistant Voice SoundSense

## Table of Contents
- [Features](#features)
- [Installation](#installation)
  - [Method 1: Using ESPHome Packages](#method-1-using-esphome-packages-recommended)
  - [Method 2: Manual Installation](#method-2-manual-installation)
- [Technical Details](#technical-details)

## Features

<div align="center">
  <table>
    <tr>
      <td><img src="images/configuration.png" alt="Configuration example" style="border-radius: 30px;"></td>
      <td><img src="images/sensors.png" alt="Sensors example" style="border-radius: 30px;"></td>
    </tr>
  </table>
</div>

The SoundSense package extends the Dynamic Volume Capabilities with Sound detection features.
The system is designed to be resource-efficient and responsive, providing a natural listening experience by keeping your device's volume at an optimal level for the current environment.

### Sound Detection States

SoundSense analyzes the ambient sound and classifies it into five different states:

- **Silence**: Prolonged period (>15s) of very low ambient noise
- **Quieting**: Recent transition to low ambient noise
- **Active**: Normal ambient sound activity
- **Noise**: Sudden spikes in sound levels
- **Presence**: Sustained elevated sound levels, indicating ongoing activity or presence

### Configurable Controls

SoundSense provides three configurable controls:

1. **Dynamic Minimum Volume** (0-100%): Sets the base volume level when ambient noise is minimal
2. **Dynamic Volume Level** (0-10): Controls how aggressively volume scales up with ambient noise
3. **Presence Threshold** (0-100 dB): Sets the sound level that triggers "presence" detection

### Optimized Sound Processing

- Efficient sound level calculation using logarithmic dB conversion
- Smart hysteresis to prevent rapid volume fluctuations
- Volume adjustments occur only when necessary, with smooth transitions
- Processing pauses during media playback to avoid feedback loops

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Installation

### Method 1: Using ESPHome Packages (Recommended)

If you want to use the SoundSense package, add the following to your configuration:

```yaml
packages:
  SoundSense: github://fixtse/ha-voice-sound-sense/sound_sense.yaml
```

Example integration with your existing configuration:

```yaml
substitutions:
  name: your-ha-voice-device-name  # Replace with your device name
  friendly_name: Your HA Voice     # Replace with your friendly name

packages:
  # Official ESPHome Home Assistant Voice PE package
  Nabu Casa.Home Assistant Voice PE: github://esphome/home-assistant-voice-pe/home-assistant-voice.yaml
  # SoundSense package
  SoundSense: github://fixtse/ha-voice-sound-sense/sound_sense.yaml

# Your existing API configuration
api:
  encryption:
    key: YOUR_API_KEY

# Your existing WiFi configuration  
wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
```

### Method 2: Manual Installation

If you prefer not to use packages, you can copy the full configuration from the [sound_sense.yaml](sound_sense.yaml) file and add it to your existing ESPHome configuration.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Technical Details

SoundSense uses an advanced algorithm to:

1. Sample microphone data in small buffers
2. Calculate the average absolute amplitude
3. Convert to decibels using a logarithmic lookup table
4. Apply state detection logic based on configurable thresholds
5. Calculate dynamic volume adjustments based on ambient conditions
6. Apply hysteresis and smoothing for stable volume transitions

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## License

Shield: [![CC BY-NC-SA 4.0][cc-by-nc-sa-shield]][cc-by-nc-sa]

This work is licensed under a
[Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License][cc-by-nc-sa].

[![CC BY-NC-SA 4.0][cc-by-nc-sa-image]][cc-by-nc-sa]

[cc-by-nc-sa]: http://creativecommons.org/licenses/by-nc-sa/4.0/
[cc-by-nc-sa-image]: https://licensebuttons.net/l/by-nc-sa/4.0/88x31.png
[cc-by-nc-sa-shield]: https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg

<p align="right">(<a href="#readme-top">back to top</a>)</p>
