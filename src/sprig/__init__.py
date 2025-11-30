from importlib import metadata

__all__ = ["__version__"]

try:
    __version__ = metadata.version("sprig")
except metadata.PackageNotFoundError:
    __version__ = "0.0.0"
