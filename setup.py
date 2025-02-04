from setuptools import find_packages, setup

setup(
    name="eventwatcher",
    version="0.3.0",
    description="A file/directory event monitoring tool with daemon support",
    author="Araray Velho",
    packages=find_packages(),
    install_requires=[
        "click",
        "toml",
        "pyyaml",
        "python-daemon",
        "rich",
        "tabulate",
        "psutil"
    ],
    entry_points={
        "console_scripts": [
            "eventwatcher=eventwatcher.cli:main"
        ]
    },
)
