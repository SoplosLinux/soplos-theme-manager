from setuptools import setup, find_packages

setup(
    name="soplos-theme-manager",
    version="2.0.0-1",
    author="Sergi Perich",
    author_email="info@soploslinux.com",
    description="Desktop theme manager for Soplos Linux Tyron (XFCE)",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/SoplosLinux/soplos-theme-manager",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "PyGObject>=3.0.0",
    ],
    entry_points={
        "console_scripts": [
            "soplos-theme-manager=main:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: POSIX :: Linux",
        "Environment :: X11 Applications :: GTK",
    ],
    python_requires=">=3.6",
)
