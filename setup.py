import distutils.core

distutils.core.setup(name="multitools",
        version="0.9.2a",
        package_dir={'multitools': 'src'},
        packages=['multitools','multitools.ipc']
)
