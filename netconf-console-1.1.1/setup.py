#!/usr/bin/env python

from setuptools import setup

setup(setup_requires=['pbr'],
      pbr=True,
      entry_points={
          "console_scripts": ['netconf-console = ncc.ncc:main']
      })
