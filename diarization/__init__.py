# Speaker diarization module for Parakeet
# This module integrates pyannote.audio for speaker identification

from typing import Dict, List, Optional, Tuple, Union
import os
import logging
import tempfile
import warnings
import numpy as np
import torch
from pydantic import BaseModel

# Suppress various warnings from pyannote and NeMo
warnings.filterwarnings('ignore', category=UserWarning, module='pyannote')
warnings.filterwarnings('ignore', message='.*torchcodec.*')
warnings.filterwarnings('ignore', message='.*TensorFloat-32.*')
warnings.filterwarnings('ignore', message='.*std.*degrees of freedom.*')

logger = logging.getLogger(__name__)

class SpeakerSegment(BaseModel):
    """A segment of speech from a specific speaker"""
    start: float
    end: float
    speaker: str

class DiarizationResult(BaseModel):
    """Result of speaker diarization"""
    segments: List[SpeakerSegment]
    num_speakers: int

class Diarizer:
    """Speaker diarization using pyannote.audio"""

    def __init__(self, access_token: Optional[str] = None, use_gpu: bool = True):
        self.pipeline = None
        self.access_token = access_token
        # Use GPU by default for faster diarization (will be unloaded before transcription)
        self.device = "cuda" if (use_gpu and torch.cuda.is_available()) else "cpu"
        self._initialize()

    def _initialize(self):
        """Initialize the diarization pipeline"""
        try:
            from pyannote.audio import Pipeline

            # Suppress NeMo warnings that come through their logging
            import logging as py_logging
            nemo_logger = py_logging.getLogger('nemo_logger')
            nemo_logger.setLevel(py_logging.ERROR)

            if not self.access_token:
                logger.warning("No access token provided. Using HUGGINGFACE_ACCESS_TOKEN environment variable.")
                self.access_token = os.environ.get("HUGGINGFACE_ACCESS_TOKEN")

            if not self.access_token:
                logger.error("No access token available. Diarization will not work.")
                return

            # Initialize the pipeline
            self.pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                token=self.access_token
            )

            # Move to GPU if available
            self.pipeline.to(torch.device(self.device))
            logger.info(f"Diarization pipeline initialized on {self.device}")

        except ImportError:
            logger.error("Failed to import pyannote.audio. Please install it with 'pip install pyannote.audio'")
        except Exception as e:
            logger.error(f"Failed to initialize diarization pipeline: {str(e)}")

    def diarize(self, audio_path: str, num_speakers: Optional[int] = None) -> DiarizationResult:
        """
        Perform speaker diarization on an audio file

        Args:
            audio_path: Path to the audio file
            num_speakers: Optional number of speakers (if known)

        Returns:
            DiarizationResult with speaker segments
        """
        if self.pipeline is None:
            logger.error("Diarization pipeline not initialized")
            return DiarizationResult(segments=[], num_speakers=0)

        try:
            # Load audio using librosa to avoid torchcodec/AudioDecoder issues
            import librosa
            import soundfile as sf

            logger.info("Loading audio file for diarization...")
            # Load audio and resample to 16kHz (standard for diarization)
            waveform, sample_rate = librosa.load(audio_path, sr=16000, mono=True)
            audio_duration = len(waveform) / 16000
            logger.info(f"Audio loaded: {audio_duration:.2f} seconds ({audio_duration/60:.1f} minutes)")

            # Convert to torch tensor and add channel dimension
            waveform_tensor = torch.from_numpy(waveform).unsqueeze(0)

            # Create audio dictionary for pyannote
            audio_dict = {
                "waveform": waveform_tensor,
                "sample_rate": 16000
            }

            # Run the diarization pipeline with preloaded audio
            import time
            start_time = time.time()
            logger.info(f"Running speaker diarization on {self.device.upper()} (this may take several minutes for long audio)...")
            diarization_output = self.pipeline(
                audio_dict,
                num_speakers=num_speakers
            )
            elapsed = time.time() - start_time
            logger.info(f"Diarization complete in {elapsed:.1f} seconds, processing results...")

            # Convert to our format
            segments = []
            speakers = set()

            # Handle pyannote.audio 4.x (DiarizeOutput) - the Annotation is at .speaker_diarization
            if hasattr(diarization_output, 'speaker_diarization'):
                # pyannote.audio 4.x - DiarizeOutput object
                annotation = diarization_output.speaker_diarization
                for turn, _, speaker in annotation.itertracks(yield_label=True):
                    # Extract speaker number from label (e.g., "SPEAKER_00" -> "1")
                    try:
                        # Try to extract the numeric part from the speaker label
                        if isinstance(speaker, str) and "_" in speaker:
                            speaker_num = int(speaker.split("_")[-1]) + 1  # 1-indexed
                        else:
                            # If it's already a number or doesn't match expected format
                            speaker_num = int(speaker) + 1 if str(speaker).isdigit() else speaker
                    except (ValueError, IndexError):
                        speaker_num = speaker

                    segments.append(SpeakerSegment(
                        start=turn.start,
                        end=turn.end,
                        speaker=str(speaker_num)
                    ))
                    speakers.add(speaker)
            elif hasattr(diarization_output, 'itertracks'):
                # pyannote.audio 3.x - Annotation object directly
                for turn, _, speaker in diarization_output.itertracks(yield_label=True):
                    # Extract speaker number from label (e.g., "SPEAKER_00" -> "1")
                    try:
                        # Try to extract the numeric part from the speaker label
                        if isinstance(speaker, str) and "_" in speaker:
                            speaker_num = int(speaker.split("_")[-1]) + 1  # 1-indexed
                        else:
                            # If it's already a number or doesn't match expected format
                            speaker_num = int(speaker) + 1 if str(speaker).isdigit() else speaker
                    except (ValueError, IndexError):
                        speaker_num = speaker

                    segments.append(SpeakerSegment(
                        start=turn.start,
                        end=turn.end,
                        speaker=str(speaker_num)
                    ))
                    speakers.add(speaker)
            else:
                logger.error(f"Unknown diarization output format: {type(diarization_output)}")
                return DiarizationResult(segments=[], num_speakers=0)

            # Sort segments by start time
            segments.sort(key=lambda x: x.start)

            logger.info(f"Processed {len(segments)} speaker segments for {len(speakers)} unique speakers")

            return DiarizationResult(
                segments=segments,
                num_speakers=len(speakers)
            )

        except Exception as e:
            logger.error(f"Diarization failed: {str(e)}")
            return DiarizationResult(segments=[], num_speakers=0)

    def merge_with_transcription(self,
                                diarization: DiarizationResult,
                                transcription_segments: list) -> list:
        """
        Merge diarization results with transcription segments

        Args:
            diarization: Speaker diarization result
            transcription_segments: List of transcription segments with start/end times

        Returns:
            Merged list of segments with speaker information
        """
        # If no diarization results, return original transcription
        if not diarization.segments:
            return transcription_segments

        # For each transcription segment, find the dominant speaker
        for segment in transcription_segments:
            # Get segment time bounds
            start = segment.start
            end = segment.end

            # Find overlapping diarization segments
            overlapping = []
            for spk_segment in diarization.segments:
                # Calculate overlap
                overlap_start = max(start, spk_segment.start)
                overlap_end = min(end, spk_segment.end)

                if overlap_end > overlap_start:
                    # There is an overlap
                    duration = overlap_end - overlap_start
                    overlapping.append((spk_segment.speaker, duration))

            # Assign the speaker with most overlap
            if overlapping:
                # Sort by duration (descending)
                overlapping.sort(key=lambda x: x[1], reverse=True)
                # Assign the dominant speaker
                setattr(segment, "speaker", overlapping[0][0])
            else:
                # No overlap found, assign unknown
                setattr(segment, "speaker", "unknown")

        return transcription_segments

    def cleanup(self):
        """Unload the pipeline from GPU memory"""
        if self.pipeline is not None:
            # Move pipeline to CPU and delete it
            if self.device == "cuda":
                try:
                    self.pipeline.to(torch.device("cpu"))
                except:
                    pass
            del self.pipeline
            self.pipeline = None

            # Clear GPU cache
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("Diarization pipeline unloaded and GPU cache cleared")
