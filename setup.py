from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="leax-ai",
    version="1.0.0",
    author="American Power LLC",
    author_email="dev@americanpower.us",
    description="AI Business Automation - Answer calls, close sales, auto-bid on jobs",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/leax-ai/app",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Office/Business",
        "License :: Other/Proprietary License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.11",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "leax=leax_desktop_launcher:main",
        ],
    },
    include_package_data=True,
    package_data={
        "": ["templates/*", "static/*"],
    },
)
