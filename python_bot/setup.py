#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VisualPilot 2.0 - Python Bot Setup & Package Configuration
"""
from setuptools import setup, find_packages

setup(
    name="visualpilot_bot",
    version="2.0.0",
    description="Automated Poker Agent for Liga Evolution & Clube do Carecas (PPPoker)",
    packages=find_packages(),
    install_requires=[
        "numpy>=1.25.0",
        "opencv-python>=4.8.0",
        "mss>=9.0.1",
        "psutil>=5.9.0",
        "pyautogui>=0.9.54",
        "pytesseract>=0.3.10",
        "pywin32>=306",
        "pillow>=10.0.0",
        "requests>=2.31.0",
        "dotenv>=1.0.0"
    ],
    python_requires=">=3.10",
)
