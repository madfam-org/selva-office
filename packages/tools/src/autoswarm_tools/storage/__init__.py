"""Artifact storage backends."""

from .base import ArtifactStorage
from .local import LocalFSStorage

__all__ = ["ArtifactStorage", "LocalFSStorage"]
