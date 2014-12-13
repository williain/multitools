import distutils.core

distutils.core.setup(name="multitools",
        version="0.9.2",
        package_dir={'multitools': 'src'},
        packages=['multitools','multitools.ipc']
)
