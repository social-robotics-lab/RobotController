"""Package configuration for the Python RobotController."""

from setuptools import find_packages, setup


setup(
    name="robot-controller",
    version="0.1.0",
    package_dir={"": "src"},
    packages=find_packages("src"),
    python_requires=">=3.6",
)
