import distutils.core

distutils.core.setup(name="multitools",
        version="0.9.3",
        package_dir={'multitools': 'src'},
        packages=['multitools','multitools.ipc','multitools.ipc.client']
)
