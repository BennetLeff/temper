"""Setup script for building Cython extensions."""

from setuptools import setup, Extension
from Cython.Build import cythonize
import numpy as np
import os

# Get the absolute path to the source directory
src_dir = os.path.join(os.path.dirname(__file__), "src")

extensions = [
    Extension(
        "temper_placer.routing.astar.astar_core",
        [os.path.join(src_dir, "temper_placer/routing/astar/astar_core.pyx")],
        include_dirs=[np.get_include()],
        language="c++",
        extra_compile_args=["-O3", "-std=c++11"],
    )
]

setup(
    name="temper-placer",
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            "language_level": "3",
            "boundscheck": False,
            "wraparound": False,
            "cdivision": True,
        },
        build_dir="build",
    ),
    package_dir={"": "src"},
)
