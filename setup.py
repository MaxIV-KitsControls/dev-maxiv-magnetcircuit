#!/usr/bin/env python
from distutils.core import setup
setup(name = 'tangods-magnetcircuit',
      version = '1.3.5',
      description = 'Tango device for magnet circuits and magnets',
      package_dir = {'MagnetCircuit':'src', 'MagnetCircuit.MagnetCycling':'src/cycling_statemachine'},
      packages = ['MagnetCircuit', 'MagnetCircuit.cycling_statemachine'],
      author='Paul Bell',
      scripts = ['scripts/MagnetCircuit','scripts/Magnet'],
      )
