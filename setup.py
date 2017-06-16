#!/usr/bin/env python
from setuptools import setup
setup(name = 'tangods-magnetcircuit',
      version = '2.2.4',
      description = 'Tango device for magnet circuits and magnets',
      package_dir = {'MagnetCircuit':'src', 'MagnetCircuit.MagnetCycling':'src/cycling_statemachine'},
      packages = ['MagnetCircuit', 'MagnetCircuit.cycling_statemachine'],
      author='Paul Bell',
      scripts = ['scripts/MagnetCircuit','scripts/Magnet'],
      )

