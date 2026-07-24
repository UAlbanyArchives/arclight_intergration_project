# /usr/bin/env python3
import setuptools

requirements = [
    "PyYAML==6.0.2",
    "pypdf==3.14.0",
    "warcio==1.7.4",
    "requests==2.32.3",
    "pycryptodome==3.15.0",
    "iiif-prezi3==2.0.1",
    "openai-whisper==20250625",
    "mutagen==1.47.0",
    "ffmpeg-python==0.2.0",
    "pyvips==2.2.3",
    "pandas==2.2.3",
    "beautifulsoup4==4.12.3",
    "lxml>=5.3.0",
    "pysolr==3.10.0",
    "pytest",
]

setuptools.setup(
    name="iiiflow",
    version="1.3.2",
    author="Gregory Wiedeman",
    author_email="gwiedeman@albany.edu",
    description="An IIIF pipeline tool using the Digital Object Discovery Storage Specification.",
    long_description_content_type="text/markdown",
    url="https://github.com/UAlbanyArchives/arclight_integration_project",
    packages=setuptools.find_packages(exclude=("tests")),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    install_requires=requirements,
    entry_points={
        'console_scripts': [
            'rebuild-manifests=iiiflow.update_manifests:main',
            'index-collection=iiiflow.index_collection:main'
        ],
    },
    python_requires=">=3.8",
)
