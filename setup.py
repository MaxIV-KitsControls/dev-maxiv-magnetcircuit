#!/usr/bin/env python
from distutils.core import setup
setup(name = 'tangods-magnetcircuit',
      version = '1.0.3',
      description = 'Tango device for magnet circuits and magnets',
      package_dir = {'MagnetCircuit':'src'},
      packages = ['MagnetCircuit'],
      author='Paul Bell',
      scripts = ['scripts/MagnetCircuit','scripts/Magnet'],
      )
