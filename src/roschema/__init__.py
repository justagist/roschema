"""roschema: breaking-change detection, linting and formatting for ROS 2 interfaces."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("roschema")
except PackageNotFoundError:  # Uninstalled source checkout.
    __version__ = "0.0.0.dev"
