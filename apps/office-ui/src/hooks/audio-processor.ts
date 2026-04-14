/**
 * WebAudio filter chain for noise suppression.
 * Applies: highpass(80Hz) -> compressor -> output
 */
import { logger } from '../lib/logger';

interface AudioFilterChain {
  /** The processed output stream (use this instead of raw mic) */
  outputStream: MediaStream;
  /** The AudioContext (keep alive while in use) */
  context: AudioContext;
  /** Clean up the filter chain */
  destroy: () => void;
}

export function createNoiseFilter(inputStream: MediaStream): AudioFilterChain | null {
  const audioTracks = inputStream.getAudioTracks();
  if (audioTracks.length === 0) return null;

  try {
    const context = new AudioContext();
    const source = context.createMediaStreamSource(new MediaStream(audioTracks));

    // Highpass filter at 80Hz -- removes low-frequency rumble (AC, fans, etc.)
    const highpass = context.createBiquadFilter();
    highpass.type = 'highpass';
    highpass.frequency.value = 80;
    highpass.Q.value = 0.7;

    // Dynamic compressor -- evens out volume levels, reduces sudden noise spikes
    const compressor = context.createDynamicsCompressor();
    compressor.threshold.value = -24;
    compressor.knee.value = 30;
    compressor.ratio.value = 12;
    compressor.attack.value = 0.003;
    compressor.release.value = 0.25;

    // Connect chain: source -> highpass -> compressor -> destination
    const destination = context.createMediaStreamDestination();
    source.connect(highpass);
    highpass.connect(compressor);
    compressor.connect(destination);

    return {
      outputStream: destination.stream,
      context,
      destroy: () => {
        source.disconnect();
        highpass.disconnect();
        compressor.disconnect();
        context.close().catch(() => {});
      },
    };
  } catch (err) {
    logger.warn('[audio-processor] Failed to create noise filter:', err);
    return null;
  }
}
