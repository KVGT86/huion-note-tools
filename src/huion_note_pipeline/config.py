"""Pipeline configuration.

Spec source: huion-note-pipeline.allium
  config {
      output_directory: String             -- mandatory
      max_conversion_attempts: Integer = 2
  }
"""
from dataclasses import dataclass


@dataclass
class PipelineConfig:
    """Configurable parameters for the pipeline.

    output_directory is mandatory (no default).
    max_conversion_attempts defaults to 2 per spec.
    """
    output_directory: str
    max_conversion_attempts: int = 2
